import frappe
from frappe.model.document import Document


class PMChangeTask(Document):
    pass


def on_doctype_update():
    frappe.db.add_index("PM Change Task", ["task"])
