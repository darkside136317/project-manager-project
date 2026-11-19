import frappe
from frappe import _
from frappe.model.document import Document

from pm_archive.pm_archive import constants as A


class PMArchiveFile(Document):
    """Hồ sơ lưu trữ of a project. Written by the services (services/filing.py, locking.py); a filed one (Đã nộp lưu)
    is read-only for good."""

    def validate(self):
        if self.is_new() or self.flags.pm_archive_lock:
            return
        if self.get_db_value("status") == A.FILED:
            frappe.throw(_("Hồ sơ {0} đã nộp lưu, không sửa được").format(self.file_number or self.name))

    def on_trash(self):
        if self.status == A.FILED:
            frappe.throw(_("Hồ sơ đã nộp lưu không xóa được"))
        if frappe.db.exists("PM Archive Item", {"archive_file": self.name}):
            frappe.throw(_("Hồ sơ còn tài liệu: bỏ tài liệu ra trước khi xóa"))


def on_doctype_update():
    frappe.db.add_index("PM Archive File", ["project", "category"])
    frappe.db.add_index("PM Archive File", ["status", "project"])
