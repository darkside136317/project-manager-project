"""Hooks of the archive layer (lưu trữ hồ sơ dự án).

This app extends project_manager; the core never imports it, and it never imports another layer (the construction
layer gives its categories through the hook pm_archive_categories, read here). It plugs in through the core's `pm_*`
hooks (project_manager/extensions.py): its capabilities and the company archivist's group, its MinIO collection, its
screens, catalogues, reports and alerts, and what happens when a project closes.
"""

app_name = "pm_archive"
app_title = "PM Archive"
app_publisher = "Project Manager Team"
app_description = "Quản lý dự án — lưu trữ hồ sơ dự án"
app_email = "admin@pm.localhost"
app_license = "MIT"

required_apps = ["erpnext", "project_manager"]

before_install = "pm_archive.pm_archive.setup.install.before_install"
after_install = "pm_archive.pm_archive.setup.install.after_install"
after_migrate = "pm_archive.pm_archive.setup.install.after_migrate"

_A = "pm_archive.pm_archive."

# --- what the core reads (project_manager/extensions.py) ------------------------------------------------------------
pm_capabilities = [_A + "setup.install.capabilities"]
pm_project_capabilities = [_A + "setup.install.project_capabilities"]
# the files this layer stores in MinIO: data, discussions and scans of the items, and the archive packages
pm_object_stores = {"archive": [("PM Archive Item", "object_key"), ("PM Archive File", "aip_key")]}
pm_masters = [_A + "setup.install.masters"]
pm_spa_modules = ["archive"]  # frontend/pm-module.js: the project tab, /pm/luu-tru
pm_nav_items = [_A + "services.register.nav_items"]
pm_alert_types = {"Hồ sơ chưa nộp lưu": _A + "services.reminders.not_filed",
                  "Hồ sơ lưu trữ lỗi toàn vẹn": _A + "services.integrity.alert_integrity"}
pm_alert_rules = [_A + "setup.install.alert_rules"]
pm_reports = [_A + "services.catalogue.reports"]  # Mục lục hồ sơ, mục lục văn bản
# a closed project's files wait for the archivist (services/filing.py)
project_close_handlers = [_A + "services.filing.on_project_close"]

# what a filed archive file holds cannot be deleted from the project (services/guards.py)
_G = _A + "services.guards."
doc_events = {
    "PM Document Version": {"on_trash": _G + "document_version"},
    "PM Document": {"on_trash": _G + "document"},
    "PM Media": {"on_trash": _G + "media"},
    "PM Form Submission": {"on_trash": _G + "form_submission"},
    "File": {"on_trash": _G + "file"},
    "Project": {"on_trash": _G + "project"},
}

scheduler_events = {
    "cron": {
        "30 2 * * 0": [_A + "services.integrity.weekly"],  # Sunday night: this week's part of the archive
    },
    "daily_long": [_A + "services.filing.compile_running"],
}

# --- project scope of the layer's DocTypes (constants.PROJECT_SCOPED; tests/test_hook_coverage.py) -------------------
_P = _A + "permissions."
permission_query_conditions = {
    "PM Archive File": _P + "archive_file_query",
    "PM Archive Item": _P + "archive_item_query",
}
has_permission = {
    "PM Archive File": _P + "has_archive_file_permission",
    "PM Archive Item": _P + "has_archive_item_permission",
}
