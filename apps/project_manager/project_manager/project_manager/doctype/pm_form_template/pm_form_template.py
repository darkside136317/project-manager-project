import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class PMFormTemplate(Document):
    """Mẫu biểu mẫu, one row per version: named {code}-v01, v02...

    Only a draft (Nháp) can change. Once in use a version is frozen, so a submission always reads the fields it was
    filled in with; changing a form means a new version (services/form_templates.py).
    """

    def autoname(self):
        self.name = f"{self.code}-v{cint(self.version) or 1:02d}"

    def validate(self):
        if not self.is_new() and frappe.db.get_value(self.doctype, self.name, "status") != "Nháp":
            frappe.throw(_("Mẫu đã đưa vào dùng không sửa được: hãy tạo phiên bản mới"))

    def on_trash(self):
        if self.flags.pm_cleanup or frappe.flags.in_uninstall:
            return
        if self.status != "Nháp" or frappe.db.exists("PM Form Submission", {"template": self.name}):
            frappe.throw(_("Chỉ xóa được mẫu nháp chưa có bản nộp nào"))
