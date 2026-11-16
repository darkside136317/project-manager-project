"""Load test (M11): 200 people report progress at the same moment, through the web server, like phones on a site.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=<site> -e PERF_BASE=http://frontend:8080 -e PERF_USERS=200 -e PERF_ROUNDS=3 \\
        -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - < ../scripts/perf/load_progress.py

It makes a scratch project (PERF-LOAD-...) whose 200 work items share 20 groups and 4 phases (so the roll-up of a
parent is hit by many reports at once), 200 scratch people (random passwords, never printed), each doing one work
item. Every person signs in, then all of them report together, PERF_ROUNDS times (30, 60, 90 %...). Checked: no
error answer, no deadlock, every report kept (one PM Progress Entry each), every work item at its last value, and,
once the roll-up queue is done, the project's figures equal a full recomputation. Everything is removed at the end.
"""

import os
import secrets
import statistics
import threading
import time

import frappe
import requests
from frappe.utils import add_days, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
BASE = os.environ.get("PERF_BASE", "http://frontend:8080").rstrip("/")
USERS = int(os.environ.get("PERF_USERS", "200"))
ROUNDS = int(os.environ.get("PERF_ROUNDS", "3"))
STAMP = frappe.generate_hash(length=6).lower()
CODE = f"PERF-LOAD-{STAMP}"
PERSON = "perf.load.{:03d}." + STAMP + "@example.com"
API = "/api/method/project_manager.project_manager.api"


def seed():
    from project_manager.project_manager import constants as C
    from project_manager.project_manager.services import assignments, projects, tree

    today = nowdate()
    project = projects.create({"project_name": f"Đo tải {STAMP}", "pm_code": CODE, "pm_state": "Đang thực hiện",
                               "expected_start_date": today, "expected_end_date": add_days(today, 60)})["name"]
    nodes, per_group = [], max(1, USERS // 20)
    for phase in range(1, 5):
        nodes.append({"key": f"{phase}", "parent_key": None, "subject": f"Giai đoạn {phase}", "is_group": 1})
        for group in range(1, 6):
            nodes.append({"key": f"{phase}.{group}", "parent_key": f"{phase}", "subject": f"Hạng mục {phase}.{group}",
                          "is_group": 1})
            for t in range(1, per_group + 1):
                nodes.append({"key": f"{phase}.{group}.{t}", "parent_key": f"{phase}.{group}", "is_group": 0,
                              "subject": f"Công tác {phase}.{group}.{t}", "exp_start_date": today,
                              "exp_end_date": add_days(today, 30)})
    names = tree.bulk_insert(project, nodes)
    leaves = [n for n, node in zip(names, nodes) if not node["is_group"]][:USERS]
    people = {}
    frappe.flags.in_import = True
    for n, task in enumerate(leaves, 1):
        email = PERSON.format(n)
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": f"Đo tải {n}", "send_welcome_email": 0, "enabled": 1,
                               "roles": [{"role": C.STAFF_ROLE}]})
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)
        password = secrets.token_urlsafe(18)
        from frappe.utils.password import update_password

        update_password(email, password)
        projects.add_member(project, email, "Kỹ sư")
        people[email] = (password, task)
    frappe.flags.in_import = False
    for email, (_password, task) in people.items():
        given = assignments.assign(task, C.RESPONSIBLE, user=email)
        frappe.db.set_value("PM Task Assignment", given, "state", C.ACCEPTED, update_modified=False)
    frappe.db.commit()
    return project, people


def run(people):
    sessions, ready = {}, threading.Barrier(len(people))
    results, lock = [], threading.Lock()

    def worker(email, password, task):
        session = requests.Session()
        try:
            login = session.post(f"{BASE}/api/method/login", data={"usr": email, "pwd": password}, timeout=120)
            login.raise_for_status()
            token = session.get(f"{BASE}{API}.boot.csrf_token", timeout=120).json()["message"]
        except Exception as e:
            with lock:
                results.append(("login", email, None, 0, repr(e)[:200]))
            ready.abort()
            return
        sessions[email] = session
        try:
            ready.wait(timeout=600)
        except threading.BrokenBarrierError:
            return
        for round_ in range(1, ROUNDS + 1):
            value = min(100, round(round_ * 90 / ROUNDS))
            started = time.perf_counter()
            try:
                answer = session.post(f"{BASE}{API}.tasks.report", timeout=300,
                                      headers={"X-Frappe-CSRF-Token": token, "Accept": "application/json"},
                                      json={"task": task, "progress_value": value, "note": f"vòng {round_}",
                                            "client_uuid": f"{STAMP}-{email}-{round_}"})
                status, error = answer.status_code, "" if answer.ok else answer.text[:300]
            except Exception as e:
                status, error = 0, repr(e)[:200]
            with lock:
                results.append(("report", email, value, status, error, (time.perf_counter() - started) * 1000))

    threads = [threading.Thread(target=worker, args=(email, password, task)) for email, (password, task) in people.items()]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results, time.perf_counter() - started


def wait_for_rollup(project, timeout=180):
    from project_manager.project_manager.services import rollup

    end = time.time() + timeout
    while time.time() < end:  # the queue-pm worker empties the project's set of dirty groups
        if not frappe.cache.smembers(rollup._key(project)):
            break
        time.sleep(1)
    time.sleep(3)  # the last job commits
    frappe.db.rollback()  # see what the workers committed


def check(project, people, results, elapsed):
    from project_manager.project_manager.services import rollup

    frappe.db.rollback()
    reports = [r for r in results if r[0] == "report"]
    failed = [r for r in results if r[0] == "login" or r[3] != 200]
    latencies = sorted(r[5] for r in reports if r[3] == 200)
    print(f"people: {len(people)}, rounds: {ROUNDS}, requests: {len(reports)}, in {elapsed:.1f} s")
    if latencies:
        p95 = latencies[int(len(latencies) * 0.95) - 1]
        print(f"latency ms: median {statistics.median(latencies):.0f}, p95 {p95:.0f}, max {latencies[-1]:.0f}")
    print(f"failed answers: {len(failed)}")
    for row in failed[:5]:
        print("  ", row[:5])
    kept = frappe.db.count("PM Progress Entry", {"project": project})
    print(f"progress entries kept: {kept} (expected {len(people) * ROUNDS})")
    last = min(100, round(ROUNDS * 90 / ROUNDS))
    wrong = frappe.db.count("Task", {"project": project, "is_group": 0, "progress": ["!=", last]})
    print(f"work items not at their last value ({last}%): {wrong}")
    deadlocks = frappe.db.count("Error Log", {"creation": [">", frappe.utils.add_to_date(None, minutes=-30)],
                                              "error": ["like", "%Deadlock%"]})
    print(f"deadlocks logged: {deadlocks}")
    wait_for_rollup(project)
    before = frappe.db.get_value("Project", project, "percent_complete")
    fixed = rollup.reconcile(project)
    frappe.db.commit()
    print(f"project progress {before}% after the queue; full recomputation changed {fixed} node(s)")
    return not failed and kept == len(people) * ROUNDS and not wrong and not deadlocks and not fixed


def clean(project, people):
    from project_manager.tests.helpers import drop_project

    frappe.db.rollback()
    if project:
        drop_project(project)
    for email in people:
        frappe.db.delete("Notification Log", {"for_user": email})
        frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()


def wait_for_frappe_jobs(limit=50, timeout=900):
    """Creating and deleting 200 accounts makes Frappe queue a job for each (create_contact, delete_dynamic_links) on
    the default queue, which drains at a few per second. A run right after another waits for them: past 500 queued
    jobs Frappe refuses new ones (QueueOverloaded). The progress reports themselves queue nothing there."""
    from frappe.utils.background_jobs import get_queue

    end = time.time() + timeout
    while time.time() < end:
        waiting = {name: len(get_queue(name)) for name in ("default", "short")}
        if max(waiting.values()) <= limit:
            return
        print(f"waiting for Frappe's jobs of a previous run: {waiting}", flush=True)
        time.sleep(15)


frappe.init(SITE)
frappe.connect()
frappe.set_user("Administrator")
wait_for_frappe_jobs()
for leftover in frappe.get_all("Project", filters={"pm_code": ["like", "PERF-LOAD-%"]}, pluck="name"):
    clean(leftover, [])  # a run stopped while seeding (Ctrl-C, an error) leaves its project and people
clean(None, frappe.get_all("User", filters={"name": ["like", "perf.load.%@example.com"]}, pluck="name"))
project, people = seed()
try:
    results, elapsed = run(people)
    ok = check(project, people, results, elapsed)
    print("RESULT:", "OK" if ok else "FAILED")
finally:
    clean(project, people)
    print("scratch data removed")
