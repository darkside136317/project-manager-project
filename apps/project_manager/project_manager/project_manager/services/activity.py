"""Write path of the project timeline (PM Activity): the only place that inserts entries.

An entry never changes once written (the controller refuses updates). `client_uuid` makes a write idempotent: a phone
that sends the same queued update twice (offline outbox) gets the first entry back instead of a duplicate.
"""

import json

import frappe

from project_manager.project_manager.services.queries import reserve_ids

MANY_FIELDS = ("name", "project", "reference_doctype", "reference_name", "task", "activity_type", "actor", "content", "data", "is_deleted",
               "owner", "modified_by", "creation", "modified", "docstatus", "idx")
TYPES = frozenset({"Bình luận", "Tiến độ", "Thay đổi", "Giao việc", "Đổi hạn", "Trạng thái", "Tệp", "Biểu mẫu", "Hệ thống"})


def record(reference_doctype: str, reference_name: str, activity_type: str, content: str = "", data=None,
           project: str | None = None, task: str | None = None, actor: str | None = None,
           client_uuid: str | None = None) -> int:
    """Append one entry and return its id. The project (and the task, for a task) is filled in when not given."""
    if activity_type not in TYPES:
        frappe.throw(frappe._("Loại hoạt động không hợp lệ: {0}").format(activity_type))
    if client_uuid:
        existing = frappe.db.get_value("PM Activity", {"client_uuid": client_uuid}, "name")
        if existing:
            return existing
    if reference_doctype == "Task":
        task = task or reference_name
        project = project or frappe.db.get_value("Task", reference_name, "project")
    elif reference_doctype == "Project":
        project = project or reference_name
    elif not project:
        project = frappe.db.get_value(reference_doctype, reference_name, "project") if frappe.get_meta(
            reference_doctype).has_field("project") else None
    entry = frappe.get_doc({
        "doctype": "PM Activity", "project": project, "reference_doctype": reference_doctype,
        "reference_name": reference_name, "task": task, "activity_type": activity_type,
        "actor": actor or frappe.session.user, "content": content or "",
        "data": json.dumps(data, ensure_ascii=False, default=str) if data is not None else None,
        "client_uuid": client_uuid or None,
    })
    entry.insert(ignore_permissions=True)
    return entry.name


def record_many(project: str, entries: list) -> int:
    """Many entries of one project in a few statements (a move that pushes hundreds of tasks).
    `entries`: (reference_doctype, reference_name, activity_type, content, data)."""
    if not entries:
        return 0
    now, user = frappe.utils.now_datetime(), frappe.session.user
    rows = []
    for number, (doctype, name, kind, content, data) in zip(reserve_ids("PM Activity", len(entries)), entries):
        rows.append((number, project, doctype, name, name if doctype == "Task" else None, kind, user, content or "",
                     json.dumps(data, ensure_ascii=False, default=str) if data is not None else None, 0, user, user, now, now, 0, 0))
    frappe.db.bulk_insert("PM Activity", MANY_FIELDS, rows, chunk_size=500)
    return len(rows)
