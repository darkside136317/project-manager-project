"""Hooks of the core app.

The core is industry neutral: it never imports an industry layer such as pm_construction.
Layers extend it through their own hooks (the `pm_extensions` contract).
"""

from project_manager.project_manager.services.audit import AUDITED_DOCTYPES

app_name = "project_manager"
app_title = "Project Manager"
app_publisher = "Project Manager Team"
app_description = "Quản lý dự án — lõi dùng chung mọi ngành"
app_email = "admin@pm.localhost"
app_license = "MIT"

required_apps = ["erpnext"]

after_install = "project_manager.project_manager.setup.install.after_install"
after_migrate = "project_manager.project_manager.setup.install.after_migrate"

# =============================================================================
# Single-page application: /pm and every /pm/... route is served by www/pm.py
# =============================================================================
website_route_rules = [
    {"from_route": "/pm/<path:app_path>", "to_route": "pm"},
]

# =============================================================================
# ERPNext's Task, adapted (see overrides/task.py)
# =============================================================================
extend_doctype_class = {
    "Task": ["project_manager.project_manager.overrides.task.PMTaskMixin"],
}

# =============================================================================
# Project scope (policy.py, permissions.py). Every DocType of constants.PROJECT_SCOPED is listed here
# (tests/test_hook_coverage.py).
# =============================================================================
_P = "project_manager.project_manager.permissions."
permission_query_conditions = {
    "Project": _P + "project_query",
    "Task": _P + "task_query",
    "PM Project Member": _P + "project_member_query",
    "PM Activity": _P + "activity_query",
}
has_permission = {
    "Project": _P + "has_project_permission",
    "Task": _P + "has_task_permission",
    "PM Project Member": _P + "has_project_member_permission",
    "PM Activity": _P + "has_activity_permission",
}

# =============================================================================
# Document events
# =============================================================================
_AUDIT = "project_manager.project_manager.services.audit.audit_doc_event"
_TASK = "project_manager.project_manager.overrides.task."
doc_events = {
    doctype: {event: _AUDIT for event in ("after_insert", "on_update", "on_update_after_submit", "on_trash")}
    for doctype in AUDITED_DOCTYPES
}
doc_events["Timesheet"] = {
    "before_submit": _TASK + "timesheet_started",
    "before_cancel": _TASK + "timesheet_started",
    "on_submit": _TASK + "timesheet_finished",
    "on_cancel": _TASK + "timesheet_finished",
}

on_login = "project_manager.project_manager.services.audit.on_login"
on_logout = "project_manager.project_manager.services.audit.on_logout"

scheduler_events = {
    "daily": [
        "project_manager.project_manager.services.audit.purge_expired",
    ],
}
