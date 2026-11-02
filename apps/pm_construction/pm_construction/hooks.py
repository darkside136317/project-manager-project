"""Hooks of the construction layer.

This app extends project_manager; the core never imports it. From M1 it registers its
extensions (rollup methods, gate checks, alert types, screens) under `pm_extensions`.
"""

app_name = "pm_construction"
app_title = "PM Construction"
app_publisher = "Project Manager Team"
app_description = "Quản lý dự án — lớp nghiệp vụ thi công xây dựng"
app_email = "admin@pm.localhost"
app_license = "MIT"

required_apps = ["erpnext", "project_manager"]
