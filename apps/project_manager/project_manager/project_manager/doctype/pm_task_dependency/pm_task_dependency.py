import frappe
from frappe.model.document import Document


class PMTaskDependency(Document):
    """Phụ thuộc giữa hai công việc. Written only by services/schedule.py, which refuses circles and links across
    projects."""

    def validate(self):
        self.project = frappe.db.get_value("Task", self.successor, "project")


def on_doctype_update():
    frappe.db.add_unique("PM Task Dependency", ["predecessor", "successor"], constraint_name="pm_dependency_pair")
    frappe.db.add_index("PM Task Dependency", ["successor"])
    frappe.db.add_index("PM Task Dependency", ["project"])
