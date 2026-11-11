from frappe.model.document import Document


class PMCMaterialPlan(Document):
    """What a work item should consume of one material: its design quantity by the norm (with waste). Rebuilt from the
    norms (services/materials.plan_from_norms); never edited by hand."""


def on_doctype_update():
    import frappe

    frappe.db.add_unique("PMC Material Plan", ["task", "item"], constraint_name="pmc_plan_task_item")
    frappe.db.add_index("PMC Material Plan", ["project", "item"])
