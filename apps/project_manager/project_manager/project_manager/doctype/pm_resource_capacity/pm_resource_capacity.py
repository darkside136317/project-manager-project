import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class PMResourceCapacity(Document):
    """A period when a person works less than full time: leave (0 %), part time, sent elsewhere. Outside these
    periods everyone is available full time on the company's working days (services/workload.py)."""

    def validate(self):
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw(_("Ngày kết thúc phải sau ngày bắt đầu"))
        if not 0 <= flt(self.capacity_pct) <= 100:
            frappe.throw(_("Mức sẵn sàng phải từ 0 đến 100%"))
        if not self.set_by:
            self.set_by = frappe.session.user


def on_doctype_update():
    frappe.db.add_index("PM Resource Capacity", ["user", "from_date"])
