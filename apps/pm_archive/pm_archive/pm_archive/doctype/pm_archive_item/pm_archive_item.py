import frappe
from frappe import _
from frappe.model.document import Document

from pm_archive.pm_archive import constants as A


class PMArchiveItem(Document):
    """A record in an archive file: a reference to a project file (or a file this layer made) and its SHA-256 once
    filed. The services insert them in bulk; nothing changes them once their file is filed."""

    def validate(self):
        if frappe.db.get_value("PM Archive File", self.archive_file, "status") == A.FILED and not self.flags.pm_archive_lock:
            frappe.throw(_("Hồ sơ đã nộp lưu, không thêm, sửa tài liệu được"))

    def on_trash(self):
        if frappe.db.get_value("PM Archive File", self.archive_file, "status") == A.FILED:
            frappe.throw(_("Tài liệu của hồ sơ đã nộp lưu không xóa được"))


def on_doctype_update():
    frappe.db.add_index("PM Archive Item", ["archive_file", "seq"])
    frappe.db.add_index("PM Archive Item", ["project", "kind"])
    frappe.db.add_index("PM Archive Item", ["source_doctype", "source_name"])
    frappe.db.add_unique("PM Archive Item", ["archive_file", "source_doctype", "source_name"],
                         constraint_name="unique_archive_source")
