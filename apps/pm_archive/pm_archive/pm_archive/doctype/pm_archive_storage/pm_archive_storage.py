import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class PMArchiveStorage(NestedSet):
    """Chỗ để bản giấy: kho → phòng → giá → hộp."""

    nsm_parent_field = "parent_pm_archive_storage"

    def validate(self):
        self.code = (self.code or "").strip()
        self.title = (self.title or "").strip()

    def on_trash(self):
        if frappe.db.exists("PM Archive File", {"storage": self.name}):
            frappe.throw(_("Còn hồ sơ để ở đây: chuyển hồ sơ đi trước khi xóa"))
        super().on_trash()
