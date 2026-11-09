import frappe
from frappe.model.document import Document


class PMMedia(Document):
    """A photo sent from a phone or a browser, kept in MinIO (object_key, thumb_key). Written only by services/media.py;
    `client_uuid` makes a resent upload (offline outbox) return the first row instead of a second photo."""

    def on_update(self):
        if not self.flags.in_insert and not self.flags.pm_service:
            frappe.throw(frappe._("Ảnh đã gửi không sửa được"))


def on_doctype_update():
    frappe.db.add_unique("PM Media", ["client_uuid"], constraint_name="pm_media_client_uuid")
    frappe.db.add_index("PM Media", ["project", "taken_at"])
    frappe.db.add_index("PM Media", ["task", "name"])
    frappe.db.add_index("PM Media", ["reference_doctype", "reference_name", "name"])
    frappe.db.add_index("PM Media", ["activity_id"])
