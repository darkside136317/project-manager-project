"""M10: the built-in project roles of a site installed before M10 get the capabilities of budgets, risks and change
requests (a new site gets them from setup/install.ensure_project_roles). A role an administrator made is left alone."""

import frappe

NEW = {"budget.manage", "risk.manage", "change.request", "change.approve"}


def execute():
    from project_manager.project_manager import constants as C

    for spec in C.DEFAULT_PROJECT_ROLES:
        if not frappe.db.exists("PM Project Role", spec["role_name"]):
            continue
        doc = frappe.get_doc("PM Project Role", spec["role_name"])
        if not doc.is_builtin:
            continue
        have = {row.capability for row in doc.capabilities}
        missing = [code for code in spec["capabilities"] if code in NEW and code not in have]
        for code in missing:
            doc.append("capabilities", {"capability": code})
        if missing:
            doc.save(ignore_permissions=True)
