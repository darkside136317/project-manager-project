import frappe
from frappe import _
from frappe.model.document import Document


class PMDelaySource(Document):
    """Khâu gây chậm: which party or step caused a delay (with the reason, it says who has to act)."""

    def on_trash(self):
        if self.is_builtin and not frappe.flags.in_uninstall:
            frappe.throw(_("Không xóa được khâu có sẵn: hãy ngừng dùng"))
        if frappe.db.exists("Task", {"pm_delay_source": self.name}):
            frappe.throw(_("Khâu {0} đang được dùng: hãy ngừng dùng thay vì xóa").format(self.name))
