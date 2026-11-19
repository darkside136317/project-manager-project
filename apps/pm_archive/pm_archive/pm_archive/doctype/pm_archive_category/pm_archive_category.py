import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet

from pm_archive.pm_archive import constants as A


def lines(value) -> list[str]:
    """The non-empty lines of a Small Text field."""
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


class PMArchiveCategory(NestedSet):
    """Danh mục hồ sơ: a kind of archive file of a project, how long it is kept and which records are filed into it
    (services/filing.py reads the rules)."""

    nsm_parent_field = "parent_pm_archive_category"

    def validate(self):
        self.code = (self.code or "").strip()
        self.title = (self.title or "").strip()
        retention = (self.retention or "").strip()
        if retention.lower() == A.PERMANENT.lower():
            retention = A.PERMANENT
        elif retention and not (retention.isdigit() and 0 < int(retention) <= 200):
            frappe.throw(_("Thời hạn bảo quản là số năm (1–200) hoặc {0}").format(A.PERMANENT))
        self.retention = retention or "10"
        unknown = [kind for kind in lines(self.kinds) if kind not in A.SOURCE_KINDS]
        if unknown:
            frappe.throw(_("Loại tư liệu không có: {0} (chỉ {1})").format(", ".join(unknown), ", ".join(A.SOURCE_KINDS)))
        if self.is_group and frappe.db.exists("PM Archive File", {"category": self.name}):
            frappe.throw(_("Danh mục đã có hồ sơ, không chuyển thành nhóm được"))

    def on_trash(self):
        if frappe.db.exists("PM Archive File", {"category": self.name}):
            frappe.throw(_("Danh mục đã có hồ sơ: hãy tắt nó (bỏ Đang dùng) thay vì xóa"))
        super().on_trash()
