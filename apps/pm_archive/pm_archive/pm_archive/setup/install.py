"""Set-up of the archive layer (idempotent): the company archivist's group, the archive capabilities of the built-in
project roles and of the director's group, the default categories (danh mục hồ sơ) and settings."""

import frappe

from pm_archive.pm_archive import constants as A


def capabilities() -> list[dict]:
    """Core hook pm_capabilities."""
    return [dict(entry) for entry in A.CAPABILITIES]


def project_capabilities() -> list[dict]:
    """Core hook pm_project_capabilities."""
    return [dict(entry) for entry in A.PROJECT_CAPABILITIES]


def masters() -> list[dict]:
    """Core hook pm_masters: the categories and the paper storage, on the generic catalogue screens."""
    return [dict(entry) for entry in A.MASTERS]


def before_install():
    # the DocTypes give the archivist's role read access: it must exist before they are synced
    ensure_archivist_role()


def after_install():
    seed_all()


def after_migrate():
    seed_all()


def _refresh_maps():
    """Installed into a running bench, the layer's DocTypes are newer than Frappe's cached maps of modules and DocTypes
    (shared in Redis by every process): records of its own DocTypes could not be made before they are rebuilt."""
    frappe.clear_cache()
    frappe.setup_module_map(include_all_apps=True)


def seed_all():
    _refresh_maps()
    ensure_archivist_role()
    ensure_archivist_group()
    grant_builtin_capabilities()
    grant_project_roles()
    ensure_categories()
    from project_manager.project_manager.setup import install as core

    core.ensure_alert_rules()  # this layer's alert types and rules (installed after the core)


CATEGORY_FIELDS = ("title", "is_group", "retention", "required", "access_mode", "document_categories", "form_templates",
                   "all_forms", "kinds", "data_paths", "description")


def category_specs() -> list[dict]:
    """The default categories: this layer's, then those the industry layers give (hook pm_archive_categories)."""
    specs = [{**spec, "industry": ""} for spec in A.DEFAULT_CATEGORIES]
    for path in frappe.get_hooks("pm_archive_categories") or []:
        specs += [{**spec, "industry": path.split(".")[0]} for spec in frappe.get_attr(path)() or []]
    return specs


def ensure_categories():
    """Create each default category once (parents first): the administrator may change or delete them afterwards."""
    pending = [spec for spec in category_specs() if not frappe.db.get_default(f"pm_archive_category:{spec['code']}")]
    while pending:
        placed = []
        for spec in pending:
            parent = spec.get("parent")
            if parent and not frappe.db.exists("PM Archive Category", parent):
                continue
            if not frappe.db.exists("PM Archive Category", spec["code"]):
                values = {key: spec[key] for key in CATEGORY_FIELDS if key in spec}
                values["access_mode"] = values.get("access_mode") or A.INTERNAL
                frappe.get_doc({"doctype": "PM Archive Category", "code": spec["code"], "industry": spec["industry"],
                                "parent_pm_archive_category": parent, **values}).insert(ignore_permissions=True)
            frappe.db.set_default(f"pm_archive_category:{spec['code']}", "1")
            placed.append(spec)
        if not placed:  # a parent that does not exist and will not come
            break
        pending = [spec for spec in pending if spec not in placed]


def alert_rules() -> list[dict]:
    """Core hook pm_alert_rules."""
    return [dict(rule) for rule in A.ALERT_RULES]


def ensure_archivist_role():
    if not frappe.db.exists("Role", A.ARCHIVIST_ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": A.ARCHIVIST_ROLE, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_archivist_group():
    if frappe.db.exists("PM Role Profile", A.ARCHIVIST_ROLE):
        return
    spec = A.ARCHIVIST_PROFILE
    frappe.get_doc({
        "doctype": "PM Role Profile", "role": spec["role"], "label": spec["label"], "group_label": spec["group_label"],
        "description": spec["description"], "is_builtin": 1,
        "capabilities": [{"capability": code} for code in spec["capabilities"]],
    }).insert(ignore_permissions=True)


def _granted(doctype: str, name: str, codes, flag: str) -> None:
    """Add `codes` to a permission group or a project role, once: the administrator may take them away afterwards."""
    if not frappe.db.exists(doctype, name) or frappe.db.get_default(flag):
        return
    doc = frappe.get_doc(doctype, name)
    held = {row.capability for row in doc.get("capabilities") or []}
    for code in codes:
        if code not in held:
            doc.append("capabilities", {"capability": code})
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.db.set_default(flag, "1")


def grant_builtin_capabilities():
    """A built-in group that a capability names as its starting point (the director sees every archive)."""
    for entry in A.CAPABILITIES:
        for role in entry.get("builtin") or ():
            _granted("PM Role Profile", role, [entry["code"]], f"pm_archive_granted:{role}:{entry['code']}")


def grant_project_roles():
    for role, codes in A.ROLE_GRANTS.items():
        _granted("PM Project Role", role, codes, f"pm_archive_granted:{role}")
    from project_manager.project_manager.policy import clear_cache

    clear_cache()
