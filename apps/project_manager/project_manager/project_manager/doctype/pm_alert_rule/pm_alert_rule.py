import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class PMAlertRule(Document):
    """When to warn whom (services/alerts.py). Administrators change the seeded rules or add their own."""

    def validate(self):
        if cint(self.days) < 0:
            frappe.throw(_("Số ngày không được âm"))
        last = 0
        for row in self.escalations or []:
            if cint(row.after_days) <= last:
                frappe.throw(_("Các bậc leo thang phải có số ngày tăng dần (lớn hơn 0)"))
            if not (row.to_manager or row.to_role or row.to_supervisor):
                frappe.throw(_("Bậc leo thang sau {0} ngày chưa có người nhận").format(row.after_days))
            last = cint(row.after_days)

    def on_trash(self):
        if cint(self.is_builtin):  # it would come back at the next update (setup/install.ensure_alert_rules)
            frappe.throw(_("Quy tắc có sẵn không xóa được: bỏ chọn \"Đang dùng\" để tắt nó"))
