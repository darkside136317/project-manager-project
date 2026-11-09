import frappe
from frappe.model.document import Document


class PMDocumentVersion(Document):
    """One uploaded file of a PM Document. The file never changes; only its approval state moves
    (Nháp → Đã duyệt → Thay thế when a newer version is approved), set by services/documents.py."""

    def on_update(self):
        if not self.flags.in_insert and not self.flags.pm_service:
            frappe.throw(frappe._("Phiên bản tài liệu không sửa được"))


def on_doctype_update():
    frappe.db.add_unique("PM Document Version", ["document", "version_no"], constraint_name="pm_document_version_no")
    frappe.db.add_index("PM Document Version", ["project", "uploaded_on"])
