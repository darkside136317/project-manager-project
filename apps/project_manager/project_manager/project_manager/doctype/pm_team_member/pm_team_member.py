import frappe
from frappe.model.document import Document


class PMTeamMember(Document):
    pass


def on_doctype_update():
    # teams_of(user): which teams a person belongs to
    frappe.db.add_index("PM Team Member", ["user", "parenttype"])
