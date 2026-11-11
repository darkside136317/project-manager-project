import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

OWNED, RENTED = "Sở hữu", "Thuê"


class PMCMachine(Document):
    """Máy thi công. An owned machine is an ERPNext Asset (moving it between projects records an Asset Movement); a
    rented one is not an asset of the company. Its project is set by transfers (services/machines.transfer)."""

    def validate(self):
        if self.ownership == OWNED:
            self.supplier = None
        else:
            self.asset = None
        if flt(self.shift_rate) < 0 or flt(self.fuel_norm) < 0:
            frappe.throw(_("Đơn giá ca và định mức nhiên liệu không được âm"))
        if self.asset and frappe.db.get_value("Asset", self.asset, "docstatus") != 1:
            frappe.throw(_("Tài sản {0} chưa được ghi nhận (submit) trong ERPNext").format(self.asset))
