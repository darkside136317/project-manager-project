"""Volume check: a million tasks on a scratch site, and the timings that matter at that size.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=perfpm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - seed    < ../scripts/perf/volume_check.py
    ... - measure < ...        (timings, best of 3; nothing is kept)
    ... - reset   < ...        (removes the generated data)

Only a site whose name starts with "perf" is accepted: the script writes a million rows with plain SQL.
PERF_SCALE (default 1.0) multiplies the volume: 0.01 gives 10 000 tasks for a quick try.

Volume (scale 1): 500 projects (50 running with 6 000 tasks each, 450 closed with ~1 556 each) = 1 000 000 tasks in
trees of phase > group > task > sub-task, dates and `modified` spread over three years.
"""

import os
import random
import sys
import time
from datetime import datetime, timedelta

import frappe

SITE = os.environ.get("PERF_SITE", "perfpm.localhost")
SCALE = float(os.environ.get("PERF_SCALE", "1"))
PREFIX = "PERF"
RUNNING, CLOSED = 50, 450
RUNNING_TASKS, CLOSED_TASKS = 6000, 1556
CHUNK = 2000
ENGINEER = "perf.engineer@example.com"
DIRECTOR = "perf.director@example.com"
EPOCH = datetime(2023, 11, 1)


def connect():
    if not SITE.startswith("perf"):
        sys.exit(f"Refusing to run on {SITE}: the site name must start with 'perf'")
    frappe.init(SITE)
    frappe.connect()
    frappe.set_user("Administrator")


def seg(n):
    return f"{n:05d}"


def project_names():
    total = max(1, round((RUNNING + CLOSED) * SCALE))
    return [f"{PREFIX}-{i:04d}" for i in range(1, total + 1)]


def task_rows(project, index, count, rng):
    """Rows of one project's tree: 5 phases, groups of ~10 tasks, a sub-task under every fourth task."""
    rows = []
    start = EPOCH + timedelta(days=rng.randint(0, 900))
    phases = 5
    per_phase = max(1, count // phases)
    n = 0

    def add(parent, path, code, level, sort, is_group, subject):
        nonlocal n
        n += 1
        name = f"TASK-{PREFIX}-{index:04d}-{n:05d}"
        begin = start + timedelta(days=rng.randint(0, 600))
        modified = EPOCH + timedelta(seconds=rng.randint(0, 3 * 365 * 86400))
        rows.append((name, subject, project, parent, int(is_group), "Open", path, sort, level, code,
                     begin.date(), (begin + timedelta(days=rng.randint(1, 60))).date(), rng.randint(0, 100),
                     modified, modified))
        return name

    for p in range(1, phases + 1):
        if n >= count:
            break
        phase = add(None, seg(p), str(p), 1, p, 1, f"Giai đoạn {p}")
        budget = per_phase - 1
        g = 0
        while budget > 0 and n < count:
            g += 1
            gpath, gcode = f"{seg(p)}.{seg(g)}", f"{p}.{g}"
            group = add(phase, gpath, gcode, 2, g, 1, f"Hạng mục {p}.{g}")
            budget -= 1
            for t in range(1, 11):
                if budget <= 0 or n >= count:
                    break
                with_sub = t % 4 == 0 and budget > 1
                task = add(group, f"{gpath}.{seg(t)}", f"{gcode}.{t}", 3, t, int(with_sub), f"Công tác {gcode}.{t}")
                budget -= 1
                if with_sub:
                    add(task, f"{gpath}.{seg(t)}.{seg(1)}", f"{gcode}.{t}.1", 4, 1, 0, f"Việc con {gcode}.{t}.1")
                    budget -= 1
    return rows


def insert_tasks(rows):
    columns = ("name", "subject", "project", "parent_task", "is_group", "status", "pm_path", "pm_sort", "pm_level",
               "pm_wbs_code", "exp_start_date", "exp_end_date", "progress", "creation", "modified")
    placeholders = "(" + ", ".join(["%s"] * len(columns)) + ", 'Administrator', 'Administrator', 0, 0, 0, 0, 1, 'Medium')"
    sql = (f"insert into `tabTask` ({', '.join(columns)}, owner, modified_by, docstatus, idx, lft, rgt, "
           f"task_weight, priority) values ")
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        frappe.db.sql(sql + ", ".join([placeholders] * len(chunk)), [v for row in chunk for v in row])


def seed():
    connect()
    from project_manager.project_manager.setup.install import seed_all

    seed_all()
    company = frappe.defaults.get_global_default("company")
    rng = random.Random(42)
    names = project_names()
    running = set(names[:max(1, round(RUNNING * SCALE))])
    started = time.time()
    total = 0
    for index, project in enumerate(names, 1):
        if frappe.db.exists("Project", project):
            continue
        frappe.db.sql(
            """insert into `tabProject` (name, project_name, status, company, percent_complete_method, pm_state,
               creation, modified, owner, modified_by, docstatus, idx, is_active)
               values (%s, %s, %s, %s, 'Manual', %s, %s, %s, 'Administrator', 'Administrator', 0, 0, 'Yes')""",
            (project, f"Công trình {index:04d}", "Open" if project in running else "Completed", company,
             "Đang thực hiện" if project in running else "Đóng", EPOCH, EPOCH))
        rows = task_rows(project, index, RUNNING_TASKS if project in running else CLOSED_TASKS, rng)
        insert_tasks(rows)
        total += len(rows)
        frappe.db.commit()
        if index % 25 == 0:
            print(f"{index} projects, {total} tasks, {time.time() - started:.0f}s", flush=True)
    for email, roles in ((ENGINEER, ["PM Staff"]), (DIRECTOR, ["PM Director"])):
        if not frappe.db.exists("User", email):
            user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                                   "send_welcome_email": 0, "roles": [{"role": r} for r in roles]})
            user.flags.no_welcome_mail = True
            user.insert(ignore_permissions=True)
    for project in sorted(running)[:3]:
        if not frappe.db.exists("PM Project Member", {"project": project, "user": ENGINEER}):
            frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": ENGINEER,
                            "project_role": "Kỹ sư"}).insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"seeded: {frappe.db.count('Project')} projects, {frappe.db.count('Task')} tasks, {time.time() - started:.0f}s")


def best_of(label, operation, runs=3, rollback=True):
    timings = []
    for _ in range(runs):
        frappe.db.savepoint("perf")
        started = time.perf_counter()
        operation()
        timings.append((time.perf_counter() - started) * 1000)
        if rollback:
            frappe.db.rollback(save_point="perf")
    best = min(timings)
    print(f"{label:<62} {best:9.1f} ms   (runs: {', '.join(f'{t:.0f}' for t in timings)})")
    return best


def as_user(user, operation):
    from project_manager.project_manager.policy import clear_cache

    def run():
        frappe.set_user(user)
        clear_cache()
        try:
            return operation()
        finally:
            frappe.set_user("Administrator")
    return run


def measure():
    connect()
    print(f"site {SITE}: {frappe.db.count('Project')} projects, {frappe.db.count('Task')} tasks")
    first = project_names()[0]
    group = frappe.db.get_value("Task", {"project": first, "pm_level": 2}, "name", order_by="pm_path asc")
    leaf_group = frappe.db.get_value("Task", {"project": first, "pm_level": 2}, "name", order_by="pm_path desc")
    other_phase = frappe.db.get_value("Task", {"project": first, "pm_level": 1}, "name", order_by="pm_path desc")

    def new_task(project, parent):
        return lambda: frappe.get_doc({"doctype": "Task", "subject": "Đo hiệu năng", "project": project,
                                       "parent_task": parent}).insert(ignore_permissions=True)

    best_of("insert a task under a group of the OLDEST project", new_task(first, group))
    best_of("insert a root task in the oldest project", new_task(first, None))
    best_of("move a group (with its tasks) to another phase", lambda: _move(leaf_group, other_phase))
    best_of("[ERPNext nested set] UPDATE every Task row once (rgt + 0)",
            lambda: frappe.db.sql("update `tabTask` set rgt = rgt + 0 where creation > '2000-01-01'"))
    best_of("engineer (3 projects): Task list, page 1, newest first",
            as_user(ENGINEER, lambda: frappe.get_list("Task", fields=["name", "subject", "status"],
                                                       order_by="modified desc", page_length=20)), rollback=False)
    best_of("engineer: one project's WBS in tree order (first 2 000)",
            as_user(ENGINEER, lambda: frappe.get_list("Task", filters={"project": project_names()[0]},
                                                       fields=["name", "pm_wbs_code", "subject"],
                                                       order_by="pm_path asc", page_length=2000)), rollback=False)
    best_of("director (all projects): Task list, page 1, newest first",
            as_user(DIRECTOR, lambda: frappe.get_list("Task", fields=["name", "subject"], order_by="modified desc",
                                                       page_length=20)), rollback=False)
    best_of("director: project list, page 1",
            as_user(DIRECTOR, lambda: frappe.get_list("Project", fields=["name", "project_name"],
                                                       order_by="modified desc", page_length=20)), rollback=False)
    best_of("engineer: count of their tasks",
            as_user(ENGINEER, lambda: frappe.db.count("Task") and frappe.get_list(
                "Task", fields=[{"COUNT": "name", "as": "c"}])), rollback=False)


def _move(task, new_parent):
    doc = frappe.get_doc("Task", task)
    doc.parent_task = new_parent
    doc.save(ignore_permissions=True)


def reset():
    connect()
    for name in frappe.get_all("PM Project Member", filters={"user": ["in", [ENGINEER, DIRECTOR]]}, pluck="name"):
        frappe.delete_doc("PM Project Member", name, force=True, ignore_permissions=True)
    frappe.db.sql(f"delete from `tabTask` where name like 'TASK-{PREFIX}-%%'")
    frappe.db.sql(f"delete from `tabProject` where name like '{PREFIX}-%%'")
    for email in (ENGINEER, DIRECTOR):
        frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()
    print("perf data removed")


if __name__ == "__main__":
    {"seed": seed, "measure": measure, "reset": reset}[sys.argv[1] if len(sys.argv) > 1 else "measure"]()
