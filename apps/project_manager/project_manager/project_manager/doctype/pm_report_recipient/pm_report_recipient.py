import frappe
from frappe.model.document import Document


class PMReportRecipient(Document):
    pass


def on_doctype_update():
    frappe.db.add_index("PM Report Recipient", ["user"])
