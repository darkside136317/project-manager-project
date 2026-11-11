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
    frappe.db.add_index("Task", ["project", "pmc_boq_key"])
    for values in K.NODE_TYPES:
        if not frappe.db.exists("PM Node Type", values["node_type"]):
            frappe.get_doc({"doctype": "PM Node Type", **values}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Task")
    from project_manager.project_manager.setup import install as core

    core.ensure_alert_rules()  # this layer's alert type and rule (installed after the core)


def alert_rules() -> list[dict]:
    """Core hook pm_alert_rules: the layer's default rules."""
    return [dict(rule) for rule in K.ALERT_RULES]
