"""Timings of M9 on scratch projects: the portfolio v2, the workload, performance, the overload alert, the weekly snapshot.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=pm.localhost -e PERF_PROJECTS=50 -e PERF_TASKS=200 -e PERF_PEOPLE=120 \\
        -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/people_check.py
    ... - reset < ../scripts/perf/people_check.py        (removes what it made; seed removes it at the end too)

Each project (code PERF-PP-NN) has PERF_TASKS work items over three months around today, half of the past ones finished
(a third of those late), the rest open (some late). PERF_PEOPLE scratch people work on them: each work item has one
accountable person and one or two doing it, picked so that each person works on several projects (and some are
overloaded). One scratch manager manages every project (perf.view_project in all of them).
"""

import os
import random
import sys
import time

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
PROJECTS = int(os.environ.get("PERF_PROJECTS", "50"))
TASKS = int(os.environ.get("PERF_TASKS", "200"))
PEOPLE = int(os.environ.get("PERF_PEOPLE", "120"))
CODE = "PERF-PP-"
MANAGER = "perf.people.manager@example.com"
WORKER = "perf.people.{:03d}@example.com"


def timed(label, fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms")
    return result


def _people():
    return [MANAGER, *(WORKER.format(n) for n in range(1, PEOPLE + 1))]


def reset():
    projects = frappe.get_all("Project", filters={"pm_code": ["like", f"{CODE}%"]}, pluck="name")
    for project in projects:
        for doctype in ("PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member",
                        "PM Alert", "PM Performance Snapshot"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("PM Performance Snapshot", {"subject": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    people = _people()
    frappe.db.delete("PM Resource Capacity", {"user": ["in", people]})
    frappe.db.delete("PM Performance Snapshot", {"subject": ["in", people]})
    frappe.db.delete("PM Alert", {"reference_doctype": "User", "reference_name": ["in", people]})
    frappe.db.delete("Notification Log", {"for_user": ["in", people]})
    for user in people:
        frappe.delete_doc("User", user, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()


def _user(email, name):
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": name, "send_welcome_email": 0,
                           "roles": [{"role": "PM Staff"}]})
    user.flags.no_welcome_mail = True
    frappe.flags.in_import = True  # Frappe throttles the creation of many users an hour
    try:
        user.insert(ignore_permissions=True)
    finally:
        frappe.flags.in_import = False


def _project(number: int, today, rng):
    from project_manager.project_manager.services import tree

    doc = frappe.get_doc({"doctype": "Project", "project_name": f"Đo hiệu suất {number:02d}", "pm_code": f"{CODE}{number:02d}",
                          "pm_state": "Đang thực hiện", "company": frappe.defaults.get_global_default("company"),
                          "expected_start_date": add_days(today, -45), "expected_end_date": add_days(today, 45),
                          "percent_complete_method": "Manual", "pm_manager": MANAGER})
    doc.insert(ignore_permissions=True)
    nodes, per_phase = [], max(1, TASKS // 4)
    for phase in range(1, 5):
        nodes.append({"key": f"{phase}", "parent_key": None, "subject": f"Giai đoạn {phase}", "is_group": 1})
        for t in range(1, per_phase + 1):
            start = -45 + (phase - 1) * 22 + rng.randint(0, 18)
            nodes.append({"key": f"{phase}.{t}", "parent_key": f"{phase}", "subject": f"Công việc {phase}.{t}", "is_group": 0,
                          "exp_start_date": add_days(today, start), "exp_end_date": add_days(today, start + rng.randint(1, 6))})
    tree.bulk_insert(doc.name, nodes)
    frappe.db.sql("""update `tabTask` set status = 'Completed', progress = 100, act_start_date = exp_start_date,
                     act_end_date = date_add(exp_end_date, interval (case when mod(pm_sort, 3) = 0 then 2 else 0 end) day)
                     where project = %(p)s and is_group = 0 and exp_end_date < %(today)s and mod(pm_sort, 2) = 0""",
                  {"p": doc.name, "today": today})
    frappe.db.sql("""update `tabTask` set status = 'Working', progress = 30, act_start_date = exp_start_date
                     where project = %(p)s and is_group = 0 and exp_start_date <= %(today)s and status = 'Open'""",
                  {"p": doc.name, "today": today})
    return doc.name


def _assign(projects, workers, rng):
    """Members and assignments in bulk: each project gets a crew of 12 people out of the pool (overlapping)."""
    now = now_datetime()
    members, rows = [], []
    for index, project in enumerate(projects):
        crew = [workers[(index * 7 + k) % len(workers)] for k in range(12)]
        members.append((project, MANAGER, "Quản lý dự án"))
        members.extend((project, user, "Kỹ sư") for user in crew)
        for task in frappe.get_all("Task", filters={"project": project, "is_group": 0}, pluck="name"):
            people = rng.sample(crew, 3)
            rows.append((task, project, "Chịu trách nhiệm chính", people[0]))
            for user in people[1:1 + rng.randint(1, 2)]:
                rows.append((task, project, "Thực hiện", user))
    from project_manager.project_manager.services.queries import reserve_ids

    for name, (project, user, role) in zip(reserve_ids("PM Project Member", len(members)), members, strict=True):
        frappe.db.sql("""insert into `tabPM Project Member` (name, project, user, project_role, is_active, creation, modified,
                         owner, modified_by, docstatus) values (%s, %s, %s, %s, 1, %s, %s, 'Administrator', 'Administrator', 0)""",
                      (name, project, user, role, now, now))
    for chunk in range(0, len(rows), 2000):
        values = rows[chunk:chunk + 2000]
        ids = reserve_ids("PM Task Assignment", len(values))
        frappe.db.sql("insert into `tabPM Task Assignment` (name, task, project, raci, user, state, is_active, assigned_by, "
                      "assigned_on, creation, modified, owner, modified_by, docstatus) values "
                      + ", ".join(["(%s, %s, %s, %s, %s, 'Đã nhận', 1, 'Administrator', %s, %s, %s, 'Administrator', "
                                   "'Administrator', 0)"] * len(values)),
                      [v for name, row in zip(ids, values, strict=True) for v in (name, *row, now, now, now)])
    return len(rows)


def seed():
    from project_manager.project_manager import policy
    from project_manager.project_manager.services import alerts, performance, portfolio, workload

    reset()
    rng = random.Random(9)
    today = getdate(nowdate())
    _user(MANAGER, "Quản lý đo")
    workers = [WORKER.format(n) for n in range(1, PEOPLE + 1)]
    timed(f"tạo {PEOPLE} người", lambda: [_user(u, f"Người đo {n:03d}") for n, u in enumerate(workers, 1)])
    projects = timed(f"tạo {PROJECTS} dự án × {TASKS} việc", lambda: [_project(n, today, rng) for n in range(1, PROJECTS + 1)])
    count = timed("giao việc", _assign, projects, workers, rng)
    for user in workers[:10]:  # leave this week for some
        workload.save_capacity(user, workload.monday(today), add_days(workload.monday(today), 1), 0, "Nghỉ phép")
    frappe.db.commit()
    policy.clear_cache()
    print(f"việc: {frappe.db.count('Task', {'project': ['in', projects]})}, lượt giao: {count}")

    view = timed("khối lượng công việc 6 tuần (quản trị, mọi người)", workload.overview, today, 6)
    over = sum(1 for r in view["rows"] if any(w["level"] == "Quá tải" for w in r["weeks"]))
    print(f"người: {len(view['rows'])}, quá tải: {over}, xung đột: {len(view['conflicts'])}")
    timed("khối lượng công việc 12 tuần (quản trị)", workload.overview, today, 12)
    timed("một ô (người × tuần)", workload.cell, workers[0], today)
    rule = frappe.get_doc("PM Alert Rule", {"rule_type": alerts.OVERLOADED})
    hits = timed("cảnh báo quá tải: đánh giá (2 tuần, mọi người)", workload.overloaded, rule, today)
    print(f"người quá tải (tuần này, tuần sau): {len(hits)}")
    timed("hiệu suất 4 tuần (quản trị)", performance.overview, "4w")
    timed("hiệu suất 13 tuần (quản trị)", performance.overview, "quarter")
    timed("hiệu suất một người", performance.person, workers[0], "quarter")
    rows = timed("ảnh chụp tuần trước", performance.snapshot_week)
    print(f"dòng ảnh chụp: {rows}")
    timed("ảnh chụp tuần trước (lần hai, cập nhật)", performance.snapshot_week)
    frappe.db.commit()
    timed(f"danh mục dự án v2 (quản trị, {PROJECTS} dự án)", portfolio.portfolio)
    frappe.set_user(MANAGER)
    policy.clear_cache()
    found = timed(f"danh mục dự án v2 ({MANAGER.split('@')[0]}, {PROJECTS} dự án)", portfolio.portfolio)
    print(f"dòng: {len(found['rows'])}, có người quá tải: {sum(1 for r in found['rows'] if r.overloaded)}")
    timed("khối lượng công việc 6 tuần (quản lý mọi dự án)", workload.overview, today, 6)
    timed("hiệu suất 4 tuần (quản lý mọi dự án)", performance.overview, "4w")
    frappe.set_user(workers[0])
    policy.clear_cache()
    mine = timed("khối lượng công việc 6 tuần (một người, chính mình)", workload.overview, today, 6)
    print(f"dòng: {len(mine['rows'])}")
    frappe.set_user("Administrator")
    policy.clear_cache()
    frappe.db.rollback()
    reset()
    print("đã dọn dữ liệu đo")


frappe.init(SITE)
frappe.connect()
frappe.set_user("Administrator")
(seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
