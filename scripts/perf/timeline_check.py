"""Speed of a discussion page (M5): a temporary project with 200 tasks and 50 000 timeline entries.

Measures one page of 50 entries for a task and for the whole project, as an administrator, as an engineer who sees
every task and as a crew lead who sees only the tasks given to them (the slowest permission condition). The plan's
target is under 500 ms. Run inside the backend container (stdin), then remove the project:

    docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/timeline_check.py
    docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - reset < ../scripts/perf/timeline_check.py
"""

import os
import random
import statistics
import sys
import time

import frappe

SITE = os.environ.get("PERF_SITE", "pm.localhost")
CODE = "PERF-TIMELINE"
TASKS, ENTRIES = 200, 50_000
ENGINEER, LEAD = "perf.timeline.engineer@example.com", "perf.timeline.lead@example.com"


def timed(label, action, rounds=5):
    durations = []
    for _ in range(rounds):
        frappe.local.pm_memo = {}
        started = time.perf_counter()
        action()
        durations.append((time.perf_counter() - started) * 1000)
    print(f"{label}: median {statistics.median(durations):.0f} ms, worst {max(durations):.0f} ms")


def user(email, roles):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
                        "roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)


def seed():
    from project_manager.project_manager import constants as C
    from project_manager.project_manager import policy
    from project_manager.project_manager.services import assignments, timeline, tree
    from project_manager.project_manager.services.queries import reserve_ids

    frappe.set_user("Administrator")
    reset(quiet=True)
    user(ENGINEER, [C.STAFF_ROLE])
    user(LEAD, [C.STAFF_ROLE])
    project = frappe.get_doc({"doctype": "Project", "project_name": "Đo dòng thời gian", "pm_code": CODE,
                              "company": frappe.defaults.get_global_default("company")}).insert(ignore_permissions=True).name
    tree.bulk_insert(project, [{"key": i, "subject": f"Việc {i}"} for i in range(TASKS)])
    tasks = frappe.get_all("Task", filters={"project": project}, pluck="name", order_by="name asc")
    for email, role in ((ENGINEER, "Kỹ sư"), (LEAD, "Tổ trưởng")):
        frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": email,
                        "project_role": role}).insert(ignore_permissions=True)
    for task in tasks[:10]:
        assignments.assign(task, C.RESPONSIBLE, user=LEAD)
    started = time.perf_counter()
    now = frappe.utils.now_datetime()
    fields = ("name", "project", "reference_doctype", "reference_name", "task", "activity_type", "actor", "content",
              "is_deleted", "owner", "modified_by", "creation", "modified", "docstatus", "idx")
    rows = []
    for number in reserve_ids("PM Activity", ENTRIES):
        task = random.choice(tasks)
        kind = random.choice(("Bình luận", "Bình luận", "Tiến độ", "Thay đổi"))
        rows.append((number, project, "Task", task, task, kind, ENGINEER, f"Nội dung {number} về cốp pha, cốt thép", 0,
                     ENGINEER, ENGINEER, now, now, 0, 0))
    frappe.db.bulk_insert("PM Activity", fields, rows, chunk_size=2000)
    frappe.db.commit()
    print(f"{TASKS} tasks, {ENTRIES} entries in {time.perf_counter() - started:.1f} s; project {project}")
    policy.clear_cache()
    busy_task = tasks[0]  # one of the lead's
    for who in ("Administrator", ENGINEER, LEAD):
        frappe.set_user(who)
        policy.clear_cache()
        timed(f"{who.split('@')[0]}: một việc, 50 mục", lambda: timeline.feed("Task", busy_task, None, 50))
        timed(f"{who.split('@')[0]}: cả dự án, 50 mục", lambda: timeline.feed("Project", project, None, 50))
        page = timeline.feed("Project", project, None, 50)
        timed(f"{who.split('@')[0]}: cả dự án, trang thứ hai", lambda: timeline.feed("Project", project, page["next"], 50))
    frappe.set_user("Administrator")


def reset(quiet=False):
    frappe.set_user("Administrator")
    for project in frappe.get_all("Project", filters={"pm_code": CODE}, pluck="name"):
        for doctype in ("PM Activity", "PM Task Assignment", "PM Project Member", "PM Follow", "PM Media"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    for email in (ENGINEER, LEAD):
        frappe.db.delete("Notification Log", {"for_user": email})
        frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()
    if not quiet:
        print("removed")


frappe.init(site=SITE)
frappe.connect()
try:
    (seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
finally:
    frappe.destroy()
