import frappe
from frappe.model.document import Document


class PMBaselineTask(Document):
    """One task's planned dates and weight when a baseline was taken. Written in bulk by services/baseline.py."""


def on_doctype_update():
    frappe.db.add_unique("PM Baseline Task", ["baseline", "task"], constraint_name="pm_baseline_task")
    frappe.db.add_index("PM Baseline Task", ["task"])
