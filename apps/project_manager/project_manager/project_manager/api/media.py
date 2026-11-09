"""Photos from the field. Rules: services/media.py."""

import frappe

from project_manager.project_manager.services import media
from project_manager.project_manager.services.ui import assert_staff


@frappe.whitelist(methods=["POST"])
def upload(reference_doctype, reference_name, client_uuid, taken_at=None, lat=None, lng=None):
    """multipart/form-data with the picture in `file` (the phone has already shrunk it)."""
    assert_staff()
    sent = frappe.request.files.get("file") if frappe.request else None
    if not sent:
        frappe.throw(frappe._("Không nhận được ảnh"))
    return media.upload(reference_doctype, reference_name, client_uuid, sent.stream.read(media.MAX_BYTES + 1),
                        sent.filename or "", taken_at, lat, lng)


@frappe.whitelist(methods=["GET"])
def file(name, size="thumb"):
    assert_staff()
    return media.serve(name, "full" if size == "full" else "thumb")


@frappe.whitelist()
def gallery(project, task=None, before=None, limit=60):
    assert_staff()
    return media.gallery(project, task or None, before, limit)
