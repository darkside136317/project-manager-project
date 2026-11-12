import frappe
from frappe.model.document import Document


class PMIssue(Document):
    """A problem of the project to solve (services/control.py), possibly a risk that happened."""


def on_doctype_update():
    frappe.db.add_index("PM Issue", ["project", "status"])
    frappe.db.add_index("PM Issue", ["owner_user", "status"])
