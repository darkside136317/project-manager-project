import frappe
from frappe.model.document import Document


class PMGateRequirement(Document):
    """Điều kiện đóng việc: a task or group that cannot close until a form of this code has been approved.
    Written only by services/gates.py."""

    def validate(self):
        self.project = frappe.db.get_value("Task", self.task, "project")


def on_doctype_update():
    frappe.db.add_index("PM Gate Requirement", ["task", "form_code"])
    frappe.db.add_index("PM Gate Requirement", ["project", "form_code"])
