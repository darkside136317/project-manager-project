import frappe
from frappe.model.document import Document


class PMDocument(Document):
    """A project document (drawing, contract, minutes...) with numbered versions (PM Document Version).
    Written only by services/documents.py; the fields here describe the newest version."""

    def on_trash(self):
        if not (self.flags.pm_cleanup or frappe.flags.in_uninstall):
            frappe.throw(frappe._("Tài liệu không xóa được: tải phiên bản mới thay thế"))


def on_doctype_update():
    frappe.db.add_index("PM Document", ["project", "category"])
    frappe.db.add_index("PM Document", ["task"])
