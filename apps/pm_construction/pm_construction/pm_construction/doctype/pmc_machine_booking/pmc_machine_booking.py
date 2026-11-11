import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class PMCMachineBooking(Document):
    """Đặt máy: a machine wanted by a project from one day to another (services/machines.book). Two projects booking
    the same machine on the same days is a conflict between projects (core workload, hook pm_conflicts)."""

    def validate(self):
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw(_("Ngày kết thúc đặt máy phải sau ngày bắt đầu"))
        self.machine_name = frappe.db.get_value("PMC Machine", self.machine, "machine_name")


def on_doctype_update():
    frappe.db.add_index("PMC Machine Booking", ["machine", "from_date"])
    frappe.db.add_index("PMC Machine Booking", ["project", "from_date"])
