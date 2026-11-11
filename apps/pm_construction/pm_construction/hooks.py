"""Hooks of the construction layer.

This app extends project_manager; the core never imports it. It plugs in through the core's `pm_*` hooks
(project_manager/extensions.py): a roll-up method by estimate value, the site diary as a discussion target, the
acceptance forms, an alert for missing site diaries, a phase condition (every work item accepted in full), and its
screens (frontend/pm-module.js).
"""

app_name = "pm_construction"
app_title = "PM Construction"
app_publisher = "Project Manager Team"
app_description = "Quản lý dự án — lớp nghiệp vụ thi công xây dựng"
app_email = "admin@pm.localhost"
app_license = "MIT"

required_apps = ["erpnext", "project_manager"]

after_install = "pm_construction.pm_construction.setup.install.after_install"
after_migrate = "pm_construction.pm_construction.setup.install.after_migrate"

_K = "pm_construction.pm_construction."

# --- what the core reads (project_manager/extensions.py) ------------------------------------------------------------
pm_rollup_methods = {"Theo giá trị dự toán": "pmc_estimate_value"}
pm_discussion_targets = {"PMC Site Diary": _K + "services.diary.target"}
pm_form_packs = [_K + "setup.form_pack.acceptance_forms"]
pm_form_events = {"approved": [_K + "services.acceptance.on_form_approved"]}
pm_spa_modules = ["construction"]
pm_alert_types = {"Thiếu nhật ký thi công": _K + "services.alerts.missing_diary",
                  "Vượt định mức vật tư": _K + "services.materials.over_norm",
                  "Máy đến hạn bảo dưỡng": _K + "services.machines.maintenance_due"}
pm_masters = [_K + "setup.install.masters"]
pm_alert_rules = [_K + "setup.install.alert_rules"]
pm_gate_checks = [_K + "services.acceptance.gate_check"]

# --- project scope of the layer's DocTypes (constants.PROJECT_SCOPED; tests/test_hook_coverage.py) -------------------
_P = _K + "permissions."
permission_query_conditions = {
    "PMC BOQ": _P + "boq_query",
    "PMC BOQ Item": _P + "boq_item_query",
    "PMC Site Diary": _P + "diary_query",
    "PMC Diary Quantity": _P + "diary_quantity_query",
    "PMC Material Plan": _P + "material_plan_query",
    "PMC Machine Transfer": _P + "machine_transfer_query",
    "PMC Machine Shift": _P + "machine_shift_query",
    "PMC Crew Attendance": _P + "attendance_query",
}
has_permission = {
    "PMC BOQ": _P + "has_boq_permission",
    "PMC BOQ Item": _P + "has_boq_item_permission",
    "PMC Site Diary": _P + "has_diary_permission",
    "PMC Diary Quantity": _P + "has_diary_quantity_permission",
    "PMC Material Plan": _P + "has_material_plan_permission",
    "PMC Machine Transfer": _P + "has_machine_transfer_permission",
    "PMC Machine Shift": _P + "has_machine_shift_permission",
    "PMC Crew Attendance": _P + "has_attendance_permission",
}

# a work item with quantities in a diary keeps its history: it is cancelled, never deleted
doc_events = {
    "Task": {"on_trash": _K + "services.quantities.guard_task_delete"},
    # the cost of the work items follows the stock entries made on them (desk ones included)
    "Stock Entry": {"on_submit": _K + "services.costs.on_stock_entry", "on_cancel": _K + "services.costs.on_stock_entry"},
}
