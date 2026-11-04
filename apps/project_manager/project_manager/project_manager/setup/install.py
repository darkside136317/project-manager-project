"""Everything a site needs to work, created by code (after_install and after_migrate), never by hand.

Every `ensure_*` function is idempotent and never overwrites what an administrator changed afterwards (a built-in
permission group, project role or node type that exists is left alone).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import cint

from project_manager.project_manager import constants as C

ERPNEXT_OVERDUE_JOB = "erpnext.projects.doctype.task.task.set_tasks_as_overdue"


def after_install():
    seed_all()


def after_migrate():
    seed_all()


def seed_all():
    ensure_roles()
    ensure_role_profiles()
    ensure_project_roles()
    ensure_node_types()
    ensure_delay_masters()
    ensure_single_defaults("PM Settings")
    ensure_custom_fields()
    ensure_erpnext_permissions()
    ensure_task_indexes()
    ensure_task_paths()
    stop_erpnext_overdue_job()
    from project_manager.project_manager.policy import clear_cache

    clear_cache()


def ensure_roles():
    for role in C.ASSIGNABLE_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_role_profiles():
    for role, info in C.ROLE_INFO.items():
        if frappe.db.exists("PM Role Profile", role):
            continue
        frappe.get_doc({
            "doctype": "PM Role Profile", "role": role, "label": info["label"], "group_label": info["group"],
            "description": info["description"], "is_builtin": 1,
            "capabilities": [{"capability": code} for code in C.BUILTIN_CAPABILITIES.get(role, ())],
        }).insert(ignore_permissions=True)


def ensure_project_roles():
    for spec in C.DEFAULT_PROJECT_ROLES:
        if frappe.db.exists("PM Project Role", spec["role_name"]):
            continue
        frappe.get_doc({
            "doctype": "PM Project Role", "role_name": spec["role_name"], "task_visibility": spec["task_visibility"],
            "is_builtin": 1, "capabilities": [{"capability": code} for code in spec["capabilities"]],
        }).insert(ignore_permissions=True)


def ensure_node_types():
    for spec in C.DEFAULT_NODE_TYPES:
        if frappe.db.exists("PM Node Type", spec["node_type"]):
            continue
        frappe.get_doc({"doctype": "PM Node Type", "is_builtin": 1, **spec}).insert(ignore_permissions=True)


def ensure_delay_masters():
    for doctype, field, values in (("PM Delay Reason", "reason", C.DEFAULT_DELAY_REASONS),
                                   ("PM Delay Source", "source", C.DEFAULT_DELAY_SOURCES)):
        for order, value in enumerate(values, 1):
            if not frappe.db.exists(doctype, value):
                frappe.get_doc({"doctype": doctype, field: value, "sort_order": order * 10, "is_builtin": 1}).insert(
                    ignore_permissions=True)


def ensure_single_defaults(doctype: str, overrides: dict | None = None):
    """Store the default of every field of a Single that has no saved value yet (a Single read before it was saved
    gives 0/empty, not the defaults of its definition)."""
    meta = frappe.get_meta(doctype)
    for df in meta.fields:
        default = (overrides or {}).get(df.fieldname, df.default)
        if default in (None, "") or df.fieldtype in ("Section Break", "Column Break", "Tab Break", "Table"):
            continue
        # get_single_value of an unsaved Check is 0, not None: look for the stored row itself
        stored = frappe.db.sql("select 1 from `tabSingles` where doctype = %s and field = %s", (doctype, df.fieldname))
        if not stored:
            frappe.db.set_single_value(doctype, df.fieldname, default)


CUSTOM_FIELDS = {
    "Project": [
        {"fieldname": "pm_section", "fieldtype": "Section Break", "label": "Quản lý dự án", "insert_after": "project_name"},
        {"fieldname": "pm_code", "fieldtype": "Data", "label": "Mã dự án", "insert_after": "pm_section",
         "in_standard_filter": 1, "search_index": 1},
        {"fieldname": "pm_state", "fieldtype": "Select", "label": "Tình trạng",
         "options": "Chuẩn bị\nĐang thực hiện\nTạm dừng\nĐóng\nHủy", "default": "Chuẩn bị", "insert_after": "pm_code",
         "in_list_view": 1, "in_standard_filter": 1},
        {"fieldname": "pm_column", "fieldtype": "Column Break", "insert_after": "pm_state"},
        {"fieldname": "pm_manager", "fieldtype": "Link", "options": "User", "label": "Quản lý dự án",
         "insert_after": "pm_column"},
        {"fieldname": "pm_rollup_method", "fieldtype": "Select", "label": "Cách tính tiến độ",
         "options": "\n".join(C.ROLLUP_METHODS), "default": C.ROLLUP_DURATION, "insert_after": "pm_manager"},
        {"fieldname": "pm_is_template", "fieldtype": "Check", "label": "Là dự án mẫu", "insert_after": "pm_rollup_method",
         "in_standard_filter": 1},
    ],
    "Task": [
        {"fieldname": "pm_node_type", "fieldtype": "Link", "options": "PM Node Type", "label": "Loại nút",
         "insert_after": "parent_task"},
        {"fieldname": "pm_wbs_code", "fieldtype": "Data", "label": "Mã WBS", "read_only": 1, "insert_after": "pm_node_type",
         "in_list_view": 1},
        {"fieldname": "pm_path", "fieldtype": "Data", "label": "Đường dẫn cây", "read_only": 1, "hidden": 1,
         "insert_after": "pm_wbs_code", "no_copy": 1},
        {"fieldname": "pm_sort", "fieldtype": "Int", "label": "Thứ tự", "read_only": 1, "hidden": 1,
         "insert_after": "pm_path", "no_copy": 1},
        {"fieldname": "pm_level", "fieldtype": "Int", "label": "Cấp", "read_only": 1, "hidden": 1,
         "insert_after": "pm_sort", "no_copy": 1},
        {"fieldname": "pm_responsibility_section", "fieldtype": "Section Break", "label": "Trách nhiệm",
         "insert_after": "pm_level"},
        {"fieldname": "pm_accountable", "fieldtype": "Link", "options": "User", "label": "Người chịu trách nhiệm chính",
         "read_only": 1, "insert_after": "pm_responsibility_section", "in_standard_filter": 1, "no_copy": 1},
        {"fieldname": "pm_reviewer", "fieldtype": "Link", "options": "User", "label": "Người duyệt", "read_only": 1,
         "insert_after": "pm_accountable", "no_copy": 1},
        {"fieldname": "pm_responsibility_column", "fieldtype": "Column Break", "insert_after": "pm_reviewer"},
        {"fieldname": "pm_is_overdue", "fieldtype": "Check", "label": "Đang trễ hạn", "read_only": 1,
         "insert_after": "pm_responsibility_column", "no_copy": 1},
        {"fieldname": "pm_delay_days", "fieldtype": "Int", "label": "Số ngày trễ", "read_only": 1,
         "insert_after": "pm_is_overdue", "no_copy": 1},
        {"fieldname": "pm_delay_reason", "fieldtype": "Link", "options": "PM Delay Reason", "label": "Lý do chậm",
         "insert_after": "pm_delay_days", "no_copy": 1},
        {"fieldname": "pm_delay_source", "fieldtype": "Link", "options": "PM Delay Source", "label": "Khâu gây chậm",
         "insert_after": "pm_delay_reason", "no_copy": 1},
        {"fieldname": "pm_delay_note", "fieldtype": "Small Text", "label": "Giải trình chậm",
         "insert_after": "pm_delay_source", "no_copy": 1},
        {"fieldname": "pm_rollup_weight", "fieldtype": "Float", "label": "Trọng số tính tiến độ", "read_only": 1,
         "hidden": 1, "insert_after": "pm_delay_note", "no_copy": 1},
        {"fieldname": "pm_last_progress_on", "fieldtype": "Datetime", "label": "Cập nhật tiến độ lần cuối",
         "read_only": 1, "insert_after": "pm_rollup_weight", "no_copy": 1},
    ],
}


def ensure_custom_fields():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True, update=True)
    # Progress roll-up is the app's (incremental, M2): ERPNext's own recount on every task save stays off.
    make_property_setter("Project", "percent_complete_method", "default", "Manual", "Text", validate_fields_for_doctype=False)


# The app's roles on ERPNext's Project and Task (copied next to ERPNext's own rules in Custom DocPerm). The project
# scope and the project roles narrow them further (permissions.py).
ERPNEXT_PERMISSIONS = {
    "Project": {
        C.ADMIN_ROLE: dict(read=1, write=1, create=1, delete=1, report=1, export=1, print=1, email=1, share=1),
        C.DIRECTOR_ROLE: dict(read=1, write=1, create=1, report=1, export=1, print=1),
        C.STAFF_ROLE: dict(read=1, write=1, create=1, report=1, print=1),
    },
    "Task": {
        C.ADMIN_ROLE: dict(read=1, write=1, create=1, delete=1, report=1, export=1, print=1, email=1, share=1),
        C.DIRECTOR_ROLE: dict(read=1, report=1, export=1, print=1),
        C.STAFF_ROLE: dict(read=1, write=1, create=1, delete=1, report=1, print=1),
    },
}


def ensure_erpnext_permissions():
    from frappe.permissions import setup_custom_perms

    from project_manager.project_manager.services import permission_matrix

    for doctype, roles in ERPNEXT_PERMISSIONS.items():
        missing = {role: flags for role, flags in roles.items()
                   if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})}
        if not missing:
            continue
        setup_custom_perms(doctype)
        permission_matrix._sanitise(doctype)
        for role, flags in missing.items():
            if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
                permission_matrix._insert(doctype, role, 0, **flags)
        permission_matrix.clear_now([doctype])


def ensure_task_indexes():
    frappe.db.add_index("Task", ["project", "pm_path"])
    frappe.db.add_index("Task", ["project", "parent_task"])
    frappe.db.add_index("Task", ["pm_accountable", "status"])
    frappe.db.add_index("Task", ["project", "status"])


def ensure_task_paths():
    """Tasks created before the app (or with validation skipped) get their place in the project's tree."""
    from project_manager.project_manager.services.wbs import rebuild

    projects = frappe.db.sql_list("select distinct project from `tabTask` where ifnull(pm_path, '') = '' and project is not null")
    for project in projects:
        rebuild(project)


def stop_erpnext_overdue_job():
    """ERPNext's daily job overwrites Task.status with "Overdue"; lateness is the app's own flag. A stopped job stays
    stopped across migrations (only frequency and cron are synced)."""
    name = frappe.db.get_value("Scheduled Job Type", {"method": ERPNEXT_OVERDUE_JOB}, ["name", "stopped"], as_dict=True)
    if name and not cint(name.stopped):
        frappe.db.set_value("Scheduled Job Type", name.name, "stopped", 1, update_modified=False)
