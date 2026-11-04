import frappe
from frappe.model.document import Document


class PMProgressEntry(Document):
    """One progress report on a task (who, when, from what to what, why late). Written by services/progress.py."""

    def validate(self):
        self.project = frappe.db.get_value("Task", self.task, "project")


def on_doctype_update():
    frappe.db.add_index("PM Progress Entry", ["task", "entry_date"])
    frappe.db.add_index("PM Progress Entry", ["project", "entry_date"])
    frappe.db.add_index("PM Progress Entry", ["reporter", "entry_date"])
