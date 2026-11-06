import frappe
from frappe.model.document import Document


class PMBaselineCurve(Document):
    """One point of a baseline's planned S-curve. Written in bulk by services/baseline.py."""


def on_doctype_update():
    frappe.db.add_unique("PM Baseline Curve", ["baseline", "point_date"], constraint_name="pm_baseline_point")
