"""API of the construction layer: BOQ, site diary, acceptance. Rules live in services/."""

import base64

import frappe
from frappe import _
from project_manager.project_manager.services.errors import retry_on_deadlock
from project_manager.project_manager.services.ui import assert_staff

from pm_construction.pm_construction.services import acceptance, boq, boq_import, diary

MAX_BOQ_BYTES = 10 * 1024 * 1024


def _content(content: str) -> bytes:
    """A file as the SPA sends it: base64 (optionally a data: URL)."""
    if not content:
        frappe.throw(_("Chưa chọn tệp"))
    if "," in content[:100] and content.startswith("data:"):
        content = content.split(",", 1)[1]
    if len(content) > MAX_BOQ_BYTES * 4 // 3 + 4:
        frappe.throw(_("Tệp lớn hơn 10 MB"))
    try:
        return base64.b64decode(content, validate=True)
    except Exception:
        frappe.throw(_("Tệp không hợp lệ"))


# --- BOQ ------------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def boq_versions(project):
    assert_staff()
    return boq.versions(project)


@frappe.whitelist()
def boq_detail(name):
    assert_staff()
    return boq.detail(name)


@frappe.whitelist(methods=["POST"])
def boq_preview(project, content):
    assert_staff()
    return boq.preview(project, _content(content))


@frappe.whitelist(methods=["POST"])
def boq_upload(project, content, filename="", title="", note=""):
    assert_staff()
    return boq.import_version(project, _content(content), filename, title, note)


@frappe.whitelist(methods=["POST"])
def boq_approve(name):
    assert_staff()
    return retry_on_deadlock(lambda: boq.approve(name))


@frappe.whitelist()
def boq_template():
    assert_staff()
    frappe.response["filename"] = "mau-boq.xlsx"
    frappe.response["filecontent"] = boq_import.template_file()
    frappe.response["type"] = "binary"


# --- site diary -----------------------------------------------------------------------------------------------------

@frappe.whitelist()
def diaries(project, start=0, limit=31):
    assert_staff()
    return diary.listing(project, start, limit)


@frappe.whitelist()
def diary_day(project, day=None):
    assert_staff()
    return diary.get_day(project, day or None)


@frappe.whitelist()
def diary_works(project, search=""):
    assert_staff()
    return diary.works(project, search)


@frappe.whitelist(methods=["POST"])
def diary_save(project, day, values=None, rows=None, client_uuid=None):
    assert_staff()
    return retry_on_deadlock(lambda: diary.save(project, day, values, rows, client_uuid or None))


@frappe.whitelist(methods=["POST"])
def diary_submit(name, media=None, client_uuid=None):
    assert_staff()
    return retry_on_deadlock(lambda: diary.submit(name, media, client_uuid or None))


@frappe.whitelist(methods=["POST"])
def diary_record(project, day, values=None, rows=None, client_uuid=None, media=None):
    """Save and submit at once: what a phone's outbox sends."""
    assert_staff()
    return retry_on_deadlock(lambda: diary.record(project, day, values, rows, client_uuid or None, media))


@frappe.whitelist(methods=["POST"])
def diary_confirm(name, note=""):
    assert_staff()
    return diary.confirm(name, note)


@frappe.whitelist(methods=["POST"])
def diary_send_back(name, note):
    assert_staff()
    return diary.send_back(name, note)


# --- acceptance -----------------------------------------------------------------------------------------------------

@frappe.whitelist()
def acceptance_overview(project):
    assert_staff()
    return acceptance.overview(project)
