import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class PMReportSubscription(Document):
    """A report sent on a schedule (services/reports/schedule.py); each recipient gets what they may see."""

    def validate(self):
        if not 0 <= cint(self.hour) <= 23:
            frappe.throw(_("Giờ gửi phải từ 0 đến 23"))
        if self.frequency == "Hằng tháng" and not 1 <= cint(self.day_of_month) <= 28:
            frappe.throw(_("Ngày trong tháng phải từ 1 đến 28"))
        if not self.recipients:
            frappe.throw(_("Chọn ít nhất một người nhận"))


def on_doctype_update():
    frappe.db.add_index("PM Report Subscription", ["is_active"])
