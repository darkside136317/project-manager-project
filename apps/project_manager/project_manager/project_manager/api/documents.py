"""Project documents with versions. Rules: services/documents.py."""

import frappe

from project_manager.project_manager.services import documents
from project_manager.project_manager.services.ui import assert_staff


def _sent():
    sent = frappe.request.files.get("file") if frappe.request else None
    if not sent:
        frappe.throw(frappe._("Chưa chọn tệp"))
    return sent.stream.read(documents.MAX_BYTES + 1), sent.filename or ""


@frappe.whitelist()
def listing(project, category=None, task=None, search="", start=0, limit=50):
    assert_staff()
    return documents.listing(project, category or None, task or None, search, start, limit)


@frappe.whitelist()
def detail(name):
    assert_staff()
    return documents.detail(name)


@frappe.whitelist(methods=["POST"])
def create(project, title, category="Khác", task=None, description="", note=""):
    """multipart/form-data with the file in `file`."""
    assert_staff()
    raw, filename = _sent()
    return documents.create(project, title, raw, filename, category, task or None, description, note)


@frappe.whitelist(methods=["POST"])
def add_version(name, note=""):
    assert_staff()
    raw, filename = _sent()
    return documents.add_version(name, raw, filename, note)


@frappe.whitelist(methods=["POST"])
def approve(name, version_no):
    assert_staff()
    return documents.approve(name, version_no)


@frappe.whitelist(methods=["GET"])
def download(name, version=None, inline=0):
    assert_staff()
    return documents.download(name, version, inline)
