import frappe
from frappe import _
from frappe.model.document import Document


class PMFormSubmission(Document):
    """Biểu mẫu đã điền: one filled-in form of a project or task, tied to the exact template version it used.

    Written only by services/forms.py (who may fill in, approve, and the states are decided there). An approved form
    never changes; a form that was submitted is never deleted.
    """

    def validate(self):
        if self.task:
            self.project = frappe.db.get_value("Task", self.task, "project")
        if not self.is_new() and frappe.db.get_value(self.doctype, self.name, "state") == "Đã duyệt":
            frappe.throw(_("Biểu mẫu đã duyệt không sửa được"))

    def on_trash(self):
        if self.flags.pm_cleanup or frappe.flags.in_uninstall:
            return
        if self.state != "Nháp" or self.submitted_on:
            frappe.throw(_("Biểu mẫu đã nộp không xóa được"))


def on_doctype_update():
    frappe.db.add_index("PM Form Submission", ["project", "template_code", "state"])
    frappe.db.add_index("PM Form Submission", ["task", "template_code", "state"])
    frappe.db.add_index("PM Form Submission", ["submitted_by", "state"])
    frappe.db.add_index("PM Form Submission", ["state", "project"])
