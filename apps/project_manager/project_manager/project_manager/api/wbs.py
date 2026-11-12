"""The WBS tree of a project: read a level, add, change, move, cancel, delete, import from Excel.
Rules live in services/tree.py and services/wbs_import.py."""

import base64

import frappe
from frappe import _
from frappe.utils import cint

from project_manager.project_manager.services import msproject, tree, wbs_import
from project_manager.project_manager.services.errors import retry_on_deadlock
from project_manager.project_manager.services.ui import assert_staff

MAX_IMPORT_BYTES = 5 * 1024 * 1024


@frappe.whitelist()
def children(project, parent=None, start=0, limit=500):
    assert_staff()
    return tree.children(project, parent or None, start, limit)


@frappe.whitelist(methods=["POST"])
def add(project, subject, parent=None, is_group=0, node_type=None, start=None, end=None, weight=None):
    assert_staff()
    return retry_on_deadlock(lambda: tree.add(project, subject, parent or None, cint(is_group), node_type or None,
                                              start or None, end or None, weight))


@frappe.whitelist(methods=["POST"])
def update(task, values, reason=""):
    assert_staff()
    values = frappe.parse_json(values) if isinstance(values, str) else values
    return tree.update(task, values, reason)


@frappe.whitelist(methods=["POST"])
def move(task, parent=None, index=None, reason=""):
    assert_staff()
    return retry_on_deadlock(lambda: tree.move(task, parent or None, None if index in (None, "") else cint(index), reason))


@frappe.whitelist(methods=["POST"])
def cancel(task, reason):
    assert_staff()
    return tree.cancel(task, reason)


@frappe.whitelist(methods=["POST"])
def delete(task):
    assert_staff()
    return tree.delete(task)


def _content(content: str, limit: int = 0) -> bytes:
    """The file as the SPA sends it: base64 (optionally a data: URL)."""
    limit = limit or MAX_IMPORT_BYTES
    if not content:
        frappe.throw(_("Chưa chọn tệp"))
    if "," in content[:100] and content.startswith("data:"):
        content = content.split(",", 1)[1]
    if len(content) > limit * 4 // 3 + 4:
        frappe.throw(_("Tệp lớn hơn {0} MB").format(limit // (1024 * 1024)))
    try:
        return base64.b64decode(content, validate=True)
    except Exception:
        frappe.throw(_("Tệp không hợp lệ"))


@frappe.whitelist(methods=["POST"])
def import_preview(project, content):
    assert_staff()
    return wbs_import.preview(project, _content(content))


@frappe.whitelist(methods=["POST"])
def import_run(project, content, parent=None):
    assert_staff()
    return wbs_import.run(project, _content(content), parent or None)


@frappe.whitelist()
def import_template():
    assert_staff()
    frappe.response["filename"] = "mau-nhap-wbs.xlsx"
    frappe.response["filecontent"] = wbs_import.template_file()
    frappe.response["type"] = "binary"


# --- MS Project XML (M10) ---------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def msproject_preview(project, content):
    assert_staff()
    return msproject.preview(project, _content(content, msproject.MAX_BYTES))


@frappe.whitelist(methods=["POST"])
def msproject_run(project, content, parent=None):
    assert_staff()
    return msproject.run(project, _content(content, msproject.MAX_BYTES), parent or None)


@frappe.whitelist()
def msproject_export(project):
    assert_staff()
    filename, content = msproject.export(project)
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = content
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "application/xml"
