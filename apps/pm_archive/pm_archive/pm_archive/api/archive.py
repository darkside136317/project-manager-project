"""The archive's API (lưu trữ hồ sơ). Rules live in services/ (filing, locking, integrity, register); this module only
checks who may call what: the app's staff, then the archive capabilities (permissions.py)."""

import frappe
from frappe import _
from project_manager.project_manager.services.ui import assert_staff

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive import permissions as P
from pm_archive.pm_archive.services import filing, integrity, locking, register


def _list(value):
    return frappe.parse_json(value) if isinstance(value, str) else (value or [])


def _dict(value):
    return frappe.parse_json(value) if isinstance(value, str) else (value or {})


def _manage(project: str) -> None:
    if not P.may_manage(project):
        frappe.throw(_("Bạn không lập hồ sơ lưu trữ của dự án này"), frappe.PermissionError)


def _manage_file(file: str) -> None:
    project = frappe.db.get_value("PM Archive File", file, "project")
    if not project:
        raise frappe.DoesNotExistError(_("Không tìm thấy hồ sơ"))
    _manage(project)


def _manage_item(item) -> None:
    file = frappe.db.get_value("PM Archive Item", frappe.utils.cint(item), "archive_file")
    if not file:
        raise frappe.DoesNotExistError(_("Không tìm thấy tài liệu"))
    _manage_file(file)


def _archivist() -> None:
    if not P.manages_everything():
        frappe.throw(_("Chỉ người lưu trữ làm được việc này"), frappe.PermissionError)


# --- reading ------------------------------------------------------------------------------------------------------------

@frappe.whitelist(methods=["GET"])
def overview(project):
    assert_staff()
    return register.overview(project)


@frappe.whitelist(methods=["GET"])
def file_detail(name, start=0, limit=500):
    assert_staff()
    return register.detail(name, start, limit)


@frappe.whitelist(methods=["GET"])
def listing(filters=None, before=None, limit=50):
    assert_staff()
    return register.listing(_dict(filters), before or None, limit)


@frappe.whitelist(methods=["GET"])
def download(item, inline=0):
    assert_staff()
    return register.download(item, inline)


@frappe.whitelist(methods=["GET"])
def storages():
    assert_staff()
    return register.storages()


@frappe.whitelist(methods=["GET"])
def checks(limit=20):
    assert_staff()
    return register.checks(limit)


# --- building the files (the project's manager, the archivist) ----------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def compile_files(project):
    assert_staff()
    _manage(project)
    return filing.compile(project)


@frappe.whitelist(methods=["POST"])
def request_filing(project):
    assert_staff()
    _manage(project)
    return {"waiting": filing.request_filing(project)}


@frappe.whitelist(methods=["POST"])
def reorder(file, order):
    assert_staff()
    _manage_file(file)
    filing.reorder(file, _list(order))
    return register.detail(file)


@frappe.whitelist(methods=["POST"])
def describe(item, values):
    assert_staff()
    _manage_item(item)
    filing.describe(item, _dict(values))
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def exclude(item, excluded=1):
    assert_staff()
    _manage_item(item)
    filing.set_excluded(item, excluded)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def move(item, target):
    assert_staff()
    _manage_item(item)
    filing.move(item, target)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def upload(file, title=None, doc_number=None, doc_date=None, author=None, page_count=None):
    """multipart/form-data with the scan in `file_content`."""
    assert_staff()
    _manage_file(file)
    sent = frappe.request.files.get("file_content") if frappe.request else None
    if not sent:
        frappe.throw(_("Chưa có tệp"))
    raw = sent.stream.read(A.MAX_UPLOAD_BYTES + 1)
    return filing.upload(file, raw, sent.filename or "", {"title": title, "doc_number": doc_number,
                                                         "doc_date": doc_date, "author": author,
                                                         "page_count": page_count})


@frappe.whitelist(methods=["POST"])
def set_paper(file, storage=None, box=None, note=None):
    assert_staff()
    if not P.manages_everything():
        _manage_file(file)
    filing.set_paper(file, storage or None, box, note)
    return {"ok": True}


# --- the archivist ------------------------------------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def file_records(names):
    """Nộp lưu: queue the filing of these files."""
    assert_staff()
    _archivist()
    return locking.request(_list(names))


@frappe.whitelist(methods=["POST"])
def start_check(file=None):
    assert_staff()
    _archivist()
    return {"check": integrity.start(file or None)}


@frappe.whitelist(methods=["POST"])
def export_package(file):
    """Gói nộp lưu (TT 05/2025/TT-BNV) of a filed file, built in the background."""
    assert_staff()
    _archivist()
    from pm_archive.pm_archive.services import aip_export

    return aip_export.request(file)


@frappe.whitelist(methods=["GET"])
def download_package(file):
    assert_staff()
    _archivist()
    from pm_archive.pm_archive.services import aip_export

    return aip_export.download(file)
