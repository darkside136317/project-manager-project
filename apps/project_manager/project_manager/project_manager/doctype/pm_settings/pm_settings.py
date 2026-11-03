import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

MIN_AUDIT_RETENTION_DAYS = 7


class PMSettings(Document):
    """Thiết lập hệ thống của ứng dụng (Single)."""

    def validate(self):
        if cint(self.audit_retention_days) < MIN_AUDIT_RETENTION_DAYS:
            frappe.throw(_("Giữ nhật ký ít nhất {0} ngày").format(MIN_AUDIT_RETENTION_DAYS))
