import frappe
from frappe.model.document import Document


class PMFollow(Document):
    """Who follows a task or a project's discussion, and how far they have read. Written only by services/timeline.py."""


def on_doctype_update():
    frappe.db.add_unique("PM Follow", ["user", "reference_doctype", "reference_name"], constraint_name="pm_follow_user_ref")
    frappe.db.add_index("PM Follow", ["reference_doctype", "reference_name", "watching"])
