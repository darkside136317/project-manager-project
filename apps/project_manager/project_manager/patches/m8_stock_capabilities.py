"""M8: the built-in project roles of a site installed before M8 get the stock capabilities and the Frappe roles they
need (a new site gets them from setup/install.ensure_project_roles). A role an administrator made is left alone."""

import frappe

NEW = {"material.request", "stock.manage"}


def execute():
    from project_manager.project_manager import constants as C

    for spec in C.DEFAULT_PROJECT_ROLES:
        if not frappe.db.exists("PM Project Role", spec["role_name"]):
            continue
        doc = frappe.get_doc("PM Project Role", spec["role_name"])
        if not doc.is_builtin:
            continue
        have = {row.capability for row in doc.capabilities}
        roles = {row.role for row in doc.required_roles}
        changed = False
        for code in spec["capabilities"]:
            if code in NEW and code not in have:
                doc.append("capabilities", {"capability": code})
                changed = True
        for role in spec.get("required_roles", ()):
            if role not in roles and frappe.db.exists("Role", role):
                doc.append("required_roles", {"role": role})
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
