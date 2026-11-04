"""Điều kiện đóng việc: a task or group that may not close until a form of a given kind has been approved.

The check sits where nothing can go around it: Task.validate (overrides/task.py) refuses the move to Completed, whether
it comes from a progress report, an approval, the Kanban board, the Desk or the REST API. Groups get their status from
roll-up, which keeps a finished group "Đang làm" while it still waits for its form (`blocked`), and recomputes it when
the form is approved.

The requirement names a form's code, not a version: a form filled in on any version of it counts.
"""

import frappe
from frappe import _

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import assert_project_capability
from project_manager.project_manager.services import activity, form_templates

RANK = {C.SUB_APPROVED: 4, C.SUB_SUBMITTED: 3, C.SUB_RETURNED: 2, C.SUB_DRAFT: 1}


def of_task(task: str) -> list[dict]:
    """The requirements of a task, each with the furthest state reached by a form of that code."""
    rows = frappe.get_all("PM Gate Requirement", filters={"task": task},
                          fields=["name", "form_code", "form_title", "gate_type", "blocks", "note"], order_by="name asc")
    if not rows:
        return []
    forms = frappe.get_all("PM Form Submission", filters={"task": task, "template_code": ["in", [r.form_code for r in rows]]},
                           fields=["name", "template_code", "state"])
    for row in rows:
        best = max((f for f in forms if f.template_code == row.form_code), key=lambda f: RANK.get(f.state, 0), default=None)
        row["state"] = best.state if best else None
        row["submission"] = best.name if best else None
        row["met"] = bool(best) and best.state == C.SUB_APPROVED
    return rows


def unmet(task: str, allow_submitted: bool = False) -> list[str]:
    """Titles of the forms still missing. `allow_submitted` also accepts a form waiting for approval."""
    accepted = {C.SUB_APPROVED, C.SUB_SUBMITTED} if allow_submitted else {C.SUB_APPROVED}
    missing = []
    for row in of_task(task):
        if row.state not in accepted:
            missing.append(row.form_title or row.form_code)
    return missing


def assert_ready(task: str, allow_submitted: bool = False) -> None:
    missing = unmet(task, allow_submitted)
    if missing:
        frappe.throw(_("Chưa đóng được công việc: cần biểu mẫu đã duyệt: {0}").format(", ".join(missing)),
                     title=_("Thiếu biểu mẫu"))


def check_close(doc) -> None:
    """Task.validate: only the move into Completed is checked (a task already closed may be saved)."""
    if doc.status != C.COMPLETED or doc.is_new():
        return
    if frappe.db.get_value("Task", doc.name, "status") != C.COMPLETED:
        assert_ready(doc.name)


def blocked(names) -> set:
    """Of these groups, the ones still waiting for an approved form (one query: roll-up calls it per level)."""
    names = tuple(names)
    if not names:
        return set()
    return {row[0] for row in frappe.db.sql(
        f"""select g.task from `tabPM Gate Requirement` g
            where g.task in %(names)s and not exists (
                select 1 from `tabPM Form Submission` s
                where s.task = g.task and s.template_code = g.form_code and s.state = '{C.SUB_APPROVED}')""",
        {"names": names})}


def add(task: str, form_code: str, note: str = "") -> dict:
    project = frappe.db.get_value("Task", task, "project")
    assert_project_capability(project, "plan.edit")
    title = frappe.db.get_value("PM Form Template", {"code": form_code}, "title", order_by="version desc")
    if not title:
        frappe.throw(_("Không có mẫu biểu mẫu mã {0}").format(form_code))
    active = form_templates.active_version(form_code)
    if not active:
        frappe.throw(_("Mẫu {0} không có phiên bản đang dùng nên không ai điền được").format(form_code))
    if frappe.db.exists("PM Gate Requirement", {"task": task, "form_code": form_code}):
        frappe.throw(_("Công việc này đã có điều kiện về mẫu {0}").format(title))
    doc = frappe.get_doc({"doctype": "PM Gate Requirement", "task": task, "form_code": form_code,
                          "form_title": form_templates.spec(active)["title"], "gate_type": C.GATE_FORM_APPROVED,
                          "blocks": C.GATE_BLOCKS_CLOSE, "note": (note or "").strip() or None})
    doc.insert(ignore_permissions=True)
    activity.record("Task", task, "Thay đổi", _("Bắt buộc biểu mẫu đã duyệt để đóng việc: {0}").format(doc.form_title),
                    data={"gate": doc.name, "form_code": form_code})
    return {"name": doc.name, "form_title": doc.form_title}


def remove(name) -> dict:
    doc = frappe.get_doc("PM Gate Requirement", frappe.utils.cint(name))
    assert_project_capability(doc.project, "plan.edit")
    task, title = doc.task, doc.form_title
    frappe.delete_doc("PM Gate Requirement", doc.name, ignore_permissions=True)
    activity.record("Task", task, "Thay đổi", _("Bỏ điều kiện đóng việc: {0}").format(title), data={"form_code": doc.form_code})
    if frappe.db.get_value("Task", task, "is_group"):
        from project_manager.project_manager.services import rollup

        rollup.schedule(doc.project, {task})
    return {"name": doc.name, "deleted": True}


def copy_to(names_by_source: dict) -> int:
    """Project from a template: its requirements come along. {template task: new task}."""
    if not names_by_source:
        return 0
    rows = frappe.get_all("PM Gate Requirement", filters={"task": ["in", list(names_by_source)]},
                          fields=["task", "form_code", "form_title", "gate_type", "blocks", "note"], limit_page_length=0)
    for row in rows:
        frappe.get_doc({"doctype": "PM Gate Requirement", **row, "task": names_by_source[row.task]}).insert(ignore_permissions=True)
    return len(rows)
