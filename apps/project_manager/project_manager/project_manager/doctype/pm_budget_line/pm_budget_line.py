import frappe
from frappe.model.document import Document


class PMBudgetLine(Document):
    pass


def on_doctype_update():
    frappe.db.add_index("PM Budget Line", ["task"])
