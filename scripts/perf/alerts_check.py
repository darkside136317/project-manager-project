"""Timings of M7 on scratch projects: health, the daily alert run, escalation, the portfolio, the digests.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=pm.localhost -e PERF_PROJECTS=50 -e PERF_TASKS=200 \\
        -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/alerts_check.py
    ... - reset < ../scripts/perf/alerts_check.py        (removes what it made; seed removes it at the end too)

Each project (code PERF-AL-NN) has 4 phases of PERF_TASKS / 4 work items spread over two months around today; a third
of the work that should have started is late and slow, so the rules have something to find. One scratch user manages
them all (the health and risk alerts reach them).
"""

import os
import sys
import time
from datetime import timedelta

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
PROJECTS = int(os.environ.get("PERF_PROJECTS", "50"))
TASKS = int(os.environ.get("PERF_TASKS", "200"))
CODE = "PERF-AL-"
MANAGER = "perf.alerts.manager@example.com"


def timed(label, fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms")
    return result


def reset():
    for project in frappe.get_all("Project", filters={"pm_code": ["like", f"{CODE}%"]}, pluck="name"):
        for doctype in ("PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member",
                        "PM Task Dependency", "PM Alert"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    frappe.db.delete("Notification Log", {"for_user": MANAGER})
    frappe.delete_doc("User", MANAGER, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()


def _project(number: int, today):
    from project_manager.project_manager.services import tree

    doc = frappe.get_doc({"doctype": "Project", "project_name": f"Đo cảnh báo {number:02d}", "pm_code": f"{CODE}{number:02d}",
                          "pm_state": "Đang thực hiện", "company": frappe.defaults.get_global_default("company"),
                          "expected_start_date": add_days(today, -30), "expected_end_date": add_days(today, 40),
                          "percent_complete_method": "Manual", "pm_manager": MANAGER})
    doc.insert(ignore_permissions=True)
    nodes, per_phase = [], max(1, TASKS // 4)
    for phase in range(1, 5):
        nodes.append({"key": f"{phase}", "parent_key": None, "subject": f"Giai đoạn {phase}", "is_group": 1})
        for t in range(1, per_phase + 1):
            start = -30 + (phase - 1) * 15 + (t % 12)
            nodes.append({"key": f"{phase}.{t}", "parent_key": f"{phase}", "subject": f"Công việc {phase}.{t}", "is_group": 0,
                          "exp_start_date": add_days(today, start), "exp_end_date": add_days(today, start + 2 + t % 4)})
    tree.bulk_insert(doc.name, nodes)
    # work that should have started: two thirds on time, a third late and slow (some of it not reported for a week)
    frappe.db.sql("""update `tabTask` set status = 'Completed', progress = 100, act_start_date = exp_start_date,
                     act_end_date = exp_end_date, pm_last_progress_on = exp_end_date
                     where project = %(p)s and is_group = 0 and exp_end_date < %(today)s and mod(pm_sort, 3) != 0""",
                  {"p": doc.name, "today": today})
    frappe.db.sql("""update `tabTask` set status = 'Working', progress = 20, act_start_date = exp_start_date,
                     pm_last_progress_on = %(stale)s
                     where project = %(p)s and is_group = 0 and exp_start_date <= %(today)s and status = 'Open'""",
                  {"p": doc.name, "today": today, "stale": add_days(today, -7)})
    return doc.name


def seed():
    from project_manager.project_manager.services import alerts, digest, phases, portfolio, rollup, schedule

    reset()
    today = getdate(nowdate())
    user = frappe.get_doc({"doctype": "User", "email": MANAGER, "first_name": "Quản lý đo", "send_welcome_email": 0,
                           "roles": [{"role": "PM Staff"}]})
    user.flags.no_welcome_mail = True
    user.insert(ignore_permissions=True)
    projects = timed(f"tạo {PROJECTS} dự án × {TASKS} việc", lambda: [_project(n, today) for n in range(1, PROJECTS + 1)])
    for project in projects:
        frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": MANAGER,
                        "project_role": "Quản lý dự án"}).insert(ignore_permissions=True)
        rollup.reconcile(project)
    frappe.db.commit()
    print(f"việc: {frappe.db.count('Task', {'project': ['in', projects]})}")

    timed("dự báo + sức khỏe, một dự án (lần đầu)", schedule.refresh, projects[0])
    timed("dự báo + sức khỏe, một dự án (không đổi)", schedule.refresh, projects[0])
    started = time.perf_counter()
    for project in projects[1:]:
        schedule.refresh(project)
    frappe.db.commit()
    print(f"dự báo + sức khỏe, {len(projects) - 1} dự án còn lại: {(time.perf_counter() - started) * 1000:.0f} ms")
    timed("kiểm tra chuyển giai đoạn, mọi dự án", lambda: [phases.check(p) for p in projects])

    first = timed("quy tắc hằng ngày, lần đầu (mở cảnh báo, báo người nhận)", alerts.run_daily)
    opened = frappe.db.count("PM Alert", {"project": ["in", projects], "state": alerts.OPEN})
    print(f"cảnh báo mở: {opened}; theo quy tắc: " + ", ".join(f"{k} {v['opened']}" for k, v in first.items()
                                                             if isinstance(v, dict) and v["opened"]))
    timed("quy tắc hằng ngày, lần sau (không có gì mới)", alerts.run_daily)
    frappe.db.sql("update `tabPM Alert` set opened_on = %s where project in %s and state = 'Đang mở'",
                  (now_datetime() - timedelta(days=3), tuple(projects)))
    escalated = timed("leo thang (mọi cảnh báo mở 3 ngày)", alerts.escalate)
    print(f"cảnh báo lên bậc: {escalated}")
    frappe.db.commit()
    timed("danh mục dự án (quản trị)", portfolio.portfolio)
    frappe.set_user(MANAGER)
    from project_manager.project_manager import policy

    policy.clear_cache()
    view = timed(f"danh mục dự án ({MANAGER.split('@')[0]}, {PROJECTS} dự án)", portfolio.portfolio)
    print(f"dòng: {len(view['rows'])}, theo sức khỏe: {view['totals']}")
    timed("cảnh báo của tôi", alerts.mine)
    frappe.set_user("Administrator")
    frappe.db.set_single_value("PM Settings", "daily_reminders", 1)
    timed("tóm tắt hằng ngày (mọi người)", digest.daily)
    timed("tóm tắt tuần", digest.weekly)
    frappe.db.rollback()
    reset()
    print("đã dọn dữ liệu đo")


frappe.init(SITE)
frappe.connect()
frappe.set_user("Administrator")
(seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
