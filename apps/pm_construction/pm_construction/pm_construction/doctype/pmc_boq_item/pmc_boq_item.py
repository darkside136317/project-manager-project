import frappe
from frappe.model.document import Document


class PMCBOQItem(Document):
    """One line of a BOQ version: a section (hạng mục) or a work item (công tác) with its quantity and unit price."""


def on_doctype_update():
    frappe.db.add_index("PMC BOQ Item", ["boq", "line_no"])
    frappe.db.add_index("PMC BOQ Item", ["task"])
