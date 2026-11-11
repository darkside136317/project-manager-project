"""Set-up of the construction layer (idempotent): Task fields for quantities, the node types "Hạng mục" and
"Công tác". The roll-up method, the acceptance forms and the screens come in through the core's hooks."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pm_construction.pm_construction import constants as K


def after_install():
    seed_all()


def after_migrate():
    seed_all()


def seed_all():
    create_custom_fields({"Task": K.TASK_FIELDS}, ignore_validate=True, update=True)
    create_custom_fields(K.STOCK_FIELDS, ignore_validate=True, update=True)
    ensure_stock_masters()
    frappe.db.add_index("Task", ["project", "pmc_boq_key"])
    for values in K.NODE_TYPES:
        if not frappe.db.exists("PM Node Type", values["node_type"]):
            frappe.get_doc({"doctype": "PM Node Type", **values}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Task")
    from project_manager.project_manager.setup import install as core

    core.ensure_alert_rules()  # this layer's alert type and rule (installed after the core)


def ensure_stock_masters():
    """The item group of construction materials and the units of the norms (m3, tấn, viên...). On a new site the
    layer is installed before ERPNext's setup wizard has made the root item group: the group comes at the migrate
    that follows the wizard. The root is found by its place in the tree, its name follows the site's language."""
    root = root_item_group()
    if not frappe.db.exists("Item Group", K.ITEM_GROUP) and root:
        frappe.get_doc({"doctype": "Item Group", "item_group_name": K.ITEM_GROUP, "parent_item_group": root,
                        "is_group": 0}).insert(ignore_permissions=True)
    for uom, whole in K.UOMS:
        if not frappe.db.exists("UOM", uom):
            frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert(ignore_permissions=True)


def root_item_group() -> str | None:
    """The top of the item group tree ("All Item Groups" in English, translated on a Vietnamese site)."""
    return frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ["is", "not set"]}, "name")


def masters() -> list[dict]:
    """Core hook pm_masters."""
    return [dict(entry) for entry in K.MASTERS]


def alert_rules() -> list[dict]:
    """Core hook pm_alert_rules: the layer's default rules."""
    return [dict(rule) for rule in K.ALERT_RULES]
