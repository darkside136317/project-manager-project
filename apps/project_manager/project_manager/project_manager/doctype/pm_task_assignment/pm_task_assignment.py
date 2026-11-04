import frappe
from frappe import _
from frappe.model.document import Document


class PMTaskAssignment(Document):
    """Phân công: who does what on one task, in which RACI role, and where the assignment stands.

    Written only by services/assignments.py (the API checks who may assign and keeps exactly one accountable person
    per task); never deleted: an assignment that ends is revoked, declined or done, so the history stays complete.
    """

    def validate(self):
        self.project = frappe.db.get_value("Task", self.task, "project")
        if not self.user and not self.team:
            frappe.throw(_("Chọn người hoặc đội được giao"))

    def on_trash(self):
        if not frappe.flags.in_uninstall and not self.flags.pm_cleanup:
            frappe.throw(_("Không xóa phân công: hãy thu hồi để giữ lịch sử"))


def on_doctype_update():
    frappe.db.add_index("PM Task Assignment", ["task", "is_active"])
    frappe.db.add_index("PM Task Assignment", ["user", "is_active", "state"])
    frappe.db.add_index("PM Task Assignment", ["team", "is_active"])
    frappe.db.add_index("PM Task Assignment", ["project", "is_active"])
