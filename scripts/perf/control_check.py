"""Timings of M10 on scratch projects: the reports (50 projects), the earned value of all of them, the register of one,
MS Project XML out and back in (2 000 tasks), the dossier of a large project.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=pm.localhost -e PERF_PROJECTS=50 -e PERF_TASKS=200 -e PERF_BIG=2000 \\
        -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/control_check.py
    ... - reset < ../scripts/perf/control_check.py        (removes what it made; seed removes it at the end too)

Each project (code PERF-CT-NN) has PERF_TASKS work items, an approved budget of 8 lines, 6 risks, 4 issues and 3 change
requests; a third of the work is late. One more project has PERF_BIG work items with links (the MS Project checks).
"""

import os
import random
import sys
import time

import frappe
from frappe.utils import add_days, getdate, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
PROJECTS = int(os.environ.get("PERF_PROJECTS", "50"))
TASKS = int(os.environ.get("PERF_TASKS", "200"))
BIG = int(os.environ.get("PERF_BIG", "2000"))
CODE = "PERF-CT-"


def timed(label, fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms")
    return result


def reset():
    from project_manager.project_manager.setup.demo import drop_control

    for project in frappe.get_all("Project", filters={"pm_code": ["like", f"{CODE}%"]}, pluck="name"):
        drop_control(project)
        for doctype in ("PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member",
                        "PM Task Dependency", "PM Alert"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    frappe.db.commit()


def _project(code: str, title: str, tasks: int, today, rng):
    from project_manager.project_manager.services import tree

    doc = frappe.get_doc({"doctype": "Project", "project_name": title, "pm_code": code, "pm_state": "Đang thực hiện",
                          "company": frappe.defaults.get_global_default("company"), "percent_complete": rng.randint(10, 60),
                          "expected_start_date": add_days(today, -45), "expected_end_date": add_days(today, 45),
                          "percent_complete_method": "Manual"})
    doc.insert(ignore_permissions=True)
    nodes, per_phase = [], max(1, tasks // 4)
    for phase in range(1, 5):
        nodes.append({"key": f"{phase}", "parent_key": None, "subject": f"Giai đoạn {phase}", "is_group": 1})
        for t in range(1, per_phase + 1):
            start = -45 + (phase - 1) * 22 + rng.randint(0, 18)
            nodes.append({"key": f"{phase}.{t}", "parent_key": f"{phase}", "subject": f"Công việc {phase}.{t}", "is_group": 0,
                          "exp_start_date": add_days(today, start), "exp_end_date": add_days(today, start + rng.randint(1, 6))})
    names = tree.bulk_insert(doc.name, nodes)
    frappe.db.sql("""update `tabTask` set pm_is_overdue = 1, pm_delay_days = 3
                     where project = %(p)s and is_group = 0 and exp_end_date < %(today)s and mod(pm_sort, 3) = 0""",
                  {"p": doc.name, "today": today})
    return doc.name, [n for n, node in zip(names, nodes) if not node["is_group"]], [n for n, node in zip(names, nodes) if node["is_group"]]


def _controls(project, leaves, groups, rng):
    from project_manager.project_manager.services import budget, control

    lines = [{"category": c, "task": groups[i % len(groups)], "amount": rng.randint(50, 500) * 1_000_000}
             for i, c in enumerate(budget.CATEGORIES)]
    budget.approve(budget.save_draft(project, "Ngân sách", lines)["name"])
    for i in range(6):
        control.save_risk(project, {"title": f"Rủi ro {i}", "probability": rng.randint(1, 5), "impact": rng.randint(1, 5)})
    for i in range(4):
        control.save_issue(project, {"title": f"Vấn đề {i}", "due_date": add_days(nowdate(), rng.randint(-5, 5))})
    for i in range(3):
        change = control.save_change(project, {"title": f"Phát sinh {i}", "cost_impact": rng.randint(1, 50) * 1_000_000})
        if i:
            control.submit_change(change["name"])


def _links(project, leaves):
    for before, after in zip(leaves, leaves[1:]):
        frappe.get_doc({"doctype": "PM Task Dependency", "predecessor": before, "successor": after, "dep_type": "FS",
                        "lag_days": 0}).insert(ignore_permissions=True)


def seed():
    from project_manager.project_manager import policy
    from project_manager.project_manager.services import closing, control, msproject, reports
    from project_manager.project_manager.services.reports import output

    reset()
    rng = random.Random(10)
    today = getdate(nowdate())
    made = timed(f"tạo {PROJECTS} dự án × {TASKS} việc kèm ngân sách, rủi ro, vấn đề, phát sinh", lambda: [
        _project(f"{CODE}{n:02d}", f"Đo kiểm soát {n:02d}", TASKS, today, rng) for n in range(1, PROJECTS + 1)])
    for project, leaves, groups in made:
        _controls(project, leaves, groups, rng)
    big, big_leaves, _groups = _project(f"{CODE}BIG", "Đo MS Project", BIG, today, rng)
    timed(f"tạo {len(big_leaves) - 1} phụ thuộc", _links, big, big_leaves[:-1][:1500] + big_leaves[-1:])
    frappe.db.commit()
    policy.clear_cache()
    for slug in [r.slug for r in reports.visible()]:
        filters = {"project": made[0][0]} if any(f.get("reqd") for f in reports.get(slug).filters) else {}
        result = timed(f"báo cáo {slug} (trang đầu)", reports.run, slug, filters, 1, 50)
        print(f"  dòng: {result['total']}")
    result, applied = output.prepare("ngan-sach-evm", {}, 2000)
    timed(f"EVM: Excel {len(result['rows'])} dự án", output.to_xlsx, result, applied)
    timed(f"EVM: PDF {len(result['rows'])} dự án", output.to_pdf, result, applied)
    timed("sổ rủi ro, vấn đề, phát sinh của một dự án", control.register, made[0][0])
    name, content = timed(f"xuất MS Project ({BIG} việc)", msproject.export, big)
    print(f"  {len(content) // 1024} KB")
    preview = timed("đọc lại tệp MS Project (xem trước)", msproject.parse, big, content)
    print(f"  việc: {preview['total']}, phụ thuộc: {preview['links']}, lỗi: {preview['errors']}")
    target, _l, _g = _project(f"{CODE}IMP", "Đo nhập MS Project", 4, today, rng)
    done = timed("nhập MS Project vào dự án khác", msproject.run, target, content)
    print(f"  việc: {done['tasks']}, phụ thuộc: {done['links']}")
    url = timed(f"lập hồ sơ dự án ({BIG} việc)", closing.build_dossier, big, "Administrator")
    print(f"  mục: {len(closing.manifest_of(url)['entries'])}")
    frappe.db.rollback()
    reset()
    print("đã dọn dữ liệu đo")


frappe.init(SITE)
frappe.connect()
frappe.set_user("Administrator")
(seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
