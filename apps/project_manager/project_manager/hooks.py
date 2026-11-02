"""Hooks of the core app.

The core is industry neutral: it never imports an industry layer such as pm_construction.
Layers extend it through their own hooks (the `pm_extensions` contract, from M1).
"""

app_name = "project_manager"
app_title = "Project Manager"
app_publisher = "Project Manager Team"
app_description = "Quản lý dự án — lõi dùng chung mọi ngành"
app_email = "admin@pm.localhost"
app_license = "MIT"

required_apps = ["erpnext"]

# =============================================================================
# Single-page application: /pm and every /pm/... route is served by www/pm.py
# =============================================================================
website_route_rules = [
    {"from_route": "/pm/<path:app_path>", "to_route": "pm"},
]
