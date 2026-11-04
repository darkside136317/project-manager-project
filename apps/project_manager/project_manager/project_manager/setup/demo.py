"""Demo data: a template project and a running project built from it, with people, assignments, progress and a month
of history, so every screen of the app has something to show.

    bench --site <site> execute project_manager.project_manager.setup.demo.up
    bench --site <site> execute project_manager.project_manager.setup.demo.down

Everything it creates is marked (project code DEMO-*, accounts demo.*@pm.localhost) and `down` removes exactly that.
Forms: the general checklist is approved on 2.1, waits for approval on 2.3, and is required (not yet filled in) on 2.5.
The demo accounts get no password: an administrator sets one (Người dùng → Gửi liên kết đặt mật khẩu) to log in as them.
"""

import random

import frappe
from frappe.utils import add_days, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.services import assignments, forms, gates, projects, rollup, tree

TEMPLATE_CODE = "DEMO-MAU"
SIGNATURE = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
PROJECT_CODE = "DEMO-NP01"
PEOPLE = (
    ("demo.quanly@pm.localhost", "Trần Quản Lý", "Quản lý dự án"),
    ("demo.chihuy@pm.localhost", "Lê Chỉ Huy", "Chỉ huy trưởng"),
    ("demo.kysu1@pm.localhost", "Nguyễn Kỹ Sư", "Kỹ sư"),
    ("demo.kysu2@pm.localhost", "Phạm Giám Sát", "Kỹ sư"),
    ("demo.totruong@pm.localhost", "Võ Tổ Trưởng", "Tổ trưởng"),
)
# (code, subject, start offset, days) — groups have no dates: they come from their children
WBS = (
    ("1", "Chuẩn bị mặt bằng", None, None),
    ("1.1", "Giải phóng mặt bằng", 0, 4),
    ("1.2", "Định vị công trình", 4, 2),
    ("2", "Phần móng", None, None),
    ("2.1", "Đào đất hố móng", 6, 5),
    ("2.2", "Bê tông lót móng", 11, 2),
    ("2.3", "Cốt thép móng", 13, 6),
    ("2.4", "Cốp pha móng", 15, 5),
    ("2.5", "Đổ bê tông móng", 21, 2),
    ("2.6", "Nghiệm thu móng", 23, 1),
    ("3", "Phần thân", None, None),
    ("3.1", "Tầng 1", None, None),
    ("3.1.1", "Cột tầng 1", 25, 7),
    ("3.1.2", "Dầm sàn tầng 1", 32, 10),
    ("3.2", "Tầng 2", None, None),
    ("3.2.1", "Cột tầng 2", 43, 7),
    ("3.2.2", "Dầm sàn tầng 2", 50, 10),
    ("4", "Hoàn thiện", None, None),
    ("4.1", "Xây tường bao che", 61, 12),
    ("4.2", "Trát, bả, sơn", 74, 15),
    ("4.3", "Lắp điện nước", 70, 20),
    ("4.4", "Bàn giao", 90, 1),
)


def _nodes(start):
    out = []
    groups = {code.rsplit(".", 1)[0] for code, *_ in WBS if "." in code}
    for code, subject, offset, days in WBS:
        out.append({
            "key": code, "parent_key": code.rsplit(".", 1)[0] if "." in code else None, "subject": subject,
            "is_group": 1 if code in groups else 0,
            "pm_node_type": "Giai đoạn" if "." not in code else ("Nhóm việc" if code in groups else "Công việc"),
            "exp_start_date": add_days(start, offset) if offset is not None else None,
            "exp_end_date": add_days(start, offset + days - 1) if offset is not None else None,
        })
    return out


def _people():
    for email, name, _role in PEOPLE:
        if frappe.db.exists("User", email):
            continue
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": name, "send_welcome_email": 0,
                               "user_type": "System User", "roles": [{"role": C.STAFF_ROLE}]})
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)


def up():
    """Create the demo (idempotent: does nothing when it is already there)."""
    if frappe.db.exists("Project", {"pm_code": PROJECT_CODE}):
        print("Demo already present")
        return
    frappe.set_user("Administrator")
    random.seed(16)
    _people()
    today = getdate(nowdate())
    template_start = getdate("2026-01-05")
    template = frappe.get_doc({"doctype": "Project", "project_name": "Mẫu: Nhà phố 3 tầng", "pm_code": TEMPLATE_CODE,
                               "pm_is_template": 1, "company": frappe.defaults.get_global_default("company"),
                               "expected_start_date": template_start, "expected_end_date": add_days(template_start, 90),
                               "percent_complete_method": "Manual"})
    template.insert(ignore_permissions=True)
    tree.bulk_insert(template.name, _nodes(template_start))

    start = add_days(today, -40)
    created = projects.create({"project_name": "Nhà phố anh Minh – Quận 7", "pm_code": PROJECT_CODE,
                               "pm_state": "Đang thực hiện", "expected_start_date": start,
                               "pm_manager": PEOPLE[0][0]}, template.name)
    project = created["name"]
    for email, _name, role in PEOPLE[1:]:  # the manager became a member when the project was created
        projects.add_member(project, email, role)
    tasks = {r.pm_wbs_code: r for r in frappe.get_all("Task", filters={"project": project},
                                                      fields=["name", "pm_wbs_code", "is_group", "exp_end_date"])}
    manager, commander, eng1, eng2, lead = (p[0] for p in PEOPLE)
    reasons = frappe.get_all("PM Delay Reason", pluck="name", order_by="sort_order")
    sources = frappe.get_all("PM Delay Source", pluck="name", order_by="sort_order")
    for code, task in tasks.items():
        if task.is_group:
            continue
        owner = eng1 if code.startswith(("1", "2")) else eng2
        assignments.assign(task.name, C.ACCOUNTABLE, user=owner)
        if code.startswith(("2", "3")):
            assignments.assign(task.name, C.RESPONSIBLE, user=lead)
        if code in ("2.6", "4.4"):
            assignments.assign(task.name, C.REVIEWER, user=commander)
        end = getdate(task.exp_end_date)
        live = frappe.get_all("PM Task Assignment", filters={"task": task.name, "user": ["in", [owner, lead]]}, pluck="name")
        if end <= today and code not in ("2.4", "2.5"):
            _set(task.name, 100, C.COMPLETED, owner)
        elif code == "2.4":  # late, with its reason
            _set(task.name, 70, C.WORKING, owner, reasons[0] if reasons else None, sources[0] if sources else None)
        elif code == "2.5":  # late, not explained yet
            _set(task.name, 20, C.WORKING, owner)
        elif getdate(add_days(end, -10)) <= today:
            _set(task.name, random.choice((20, 35, 50)), C.WORKING, owner)
        if end <= add_days(today, 15):
            for name in live:
                frappe.db.set_value("PM Task Assignment", name, "state", C.ACCEPTED, update_modified=False)
    _forms(project, tasks, eng1, commander)
    rollup.reconcile(project)
    rollup.refresh_overdue_flags()
    _history(project, start, today)
    frappe.db.commit()
    print(f"Demo created: {project} (template {template.name})")


def _forms(project, tasks, engineer, commander):
    """An approved checklist, one waiting for approval, and a task that cannot close until its form is approved."""
    gates.add(tasks["2.5"].name, "CL-CHUNG", "Kiểm tra trước khi đổ bê tông")
    today = nowdate()
    answers = {"ngay_kiem_tra": today, "ket_luan": "Đạt",
               "danh_muc_kiem_tra": [{"ket_qua": "Đạt"} for _ in range(5)]}
    decided = None
    for code in ("2.1", "2.3"):
        frappe.set_user(engineer)
        name = forms.start("CL-CHUNG", project, tasks[code].name)["name"]
        signature = forms.attach(name, SIGNATURE, "chu-ky.png")
        forms.submit(name, {**answers, "nguoi_kiem_tra_ky": [signature]})
        decided = decided or name
    frappe.set_user(commander)
    forms.approve(decided, "Đạt yêu cầu")
    frappe.set_user("Administrator")


def _set(task, progress, status, reporter, reason=None, source=None):
    values = {"progress": progress, "status": status, "pm_last_progress_on": frappe.utils.now_datetime()}
    if reason:
        values.update(pm_delay_reason=reason, pm_delay_source=source, pm_delay_note="Nhà cung cấp giao ván khuôn chậm")
    if status == C.COMPLETED:
        values["act_end_date"] = frappe.db.get_value("Task", task, "exp_end_date")
    frappe.db.set_value("Task", task, values, update_modified=False)
    frappe.get_doc({"doctype": "PM Progress Entry", "task": task, "entry_date": nowdate(), "reporter": reporter,
                    "progress_before": 0, "progress_after": progress, "delay_reason": reason,
                    "delay_source": source}).insert(ignore_permissions=True)
    if status == C.COMPLETED:
        assignments.complete_for(task)


def _history(project, start, today):
    """A month of daily snapshots, so the S-curve has a shape (actual lagging a little behind plan)."""
    end = frappe.db.get_value("Project", project, "expected_end_date")
    final = float(frappe.db.get_value("Project", project, "percent_complete") or 0)
    days = (today - getdate(start)).days
    for i in range(days + 1):
        day = add_days(start, i)
        planned = rollup.planned_progress(start, end, day)
        actual = round(final * i / max(1, days), 2)
        rollup._snapshot(project, None, day, actual, planned, None)


def down():
    """Remove everything `up` created."""
    frappe.set_user("Administrator")
    for code in (PROJECT_CODE, TEMPLATE_CODE):
        for project in frappe.get_all("Project", filters={"pm_code": code}, pluck="name"):
            for doctype in ("PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member",
                            "PM Form Submission", "PM Gate Requirement"):
                frappe.db.delete(doctype, {"project": project})
            frappe.db.delete("Task", {"project": project})
            frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    for email, *_ in PEOPLE:
        frappe.db.delete("Notification Log", {"for_user": email})
        frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()
    print("Demo removed")
