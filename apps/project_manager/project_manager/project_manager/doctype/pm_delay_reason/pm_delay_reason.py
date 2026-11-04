import frappe
from frappe import _
from frappe.model.document import Document


class PMDelayReason(Document):
    """Lý do chậm: chosen when late work is reported, so delays can be counted by cause instead of argued about."""

    def on_trash(self):
        if self.is_builtin and not frappe.flags.in_uninstall:
            frappe.throw(_("Không xóa được lý do có sẵn: hãy ngừng dùng"))
        if frappe.db.exists("Task", {"pm_delay_reason": self.name}):
            frappe.throw(_("Lý do {0} đang được dùng: hãy ngừng dùng thay vì xóa").format(self.name))
