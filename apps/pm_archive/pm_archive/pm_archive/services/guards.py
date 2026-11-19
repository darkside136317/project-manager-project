"""What a filed archive file holds cannot disappear from the project: deleting its source is refused (doc_events
on_trash, hooks.py). The sources themselves never change under their key (a document version, a photo, a kept form
PDF), so the filed SHA-256 stays true; the weekly integrity check proves it."""

import frappe
from frappe import _

from pm_archive.pm_archive import constants as A


def _filed(condition: str, values: dict) -> str | None:
    rows = frappe.db.sql(f"""select f.file_number from `tabPM Archive Item` i
                             join `tabPM Archive File` f on f.name = i.archive_file
                             where f.status = %(filed)s and {condition} limit 1""", {**values, "filed": A.FILED})
    return rows[0][0] if rows else None


def _refuse(number: str) -> None:
    frappe.throw(_("Không xóa được: tài liệu này thuộc hồ sơ lưu trữ {0} đã nộp lưu").format(number))


def _by_source(doctype: str, names) -> None:
    names = [str(n) for n in names if n]
    if names and (number := _filed("i.source_doctype = %(doctype)s and i.source_name in %(names)s",
                                    {"doctype": doctype, "names": tuple(names)})):
        _refuse(number)


def document_version(doc, method=None):
    _by_source("PM Document Version", [doc.name])


def document(doc, method=None):
    _by_source("PM Document Version", frappe.get_all("PM Document Version", filters={"document": doc.name}, pluck="name"))


def media(doc, method=None):
    _by_source("PM Media", [doc.name])


def form_submission(doc, method=None):
    _by_source("PM Form Submission", [doc.name])


def file(doc, method=None):
    if doc.file_url and (number := _filed("i.file_url = %(url)s", {"url": doc.file_url})):
        _refuse(number)


def project(doc, method=None):
    number = frappe.db.get_value("PM Archive File", {"project": doc.name, "status": A.FILED}, "file_number")
    if number:
        _refuse(number)
