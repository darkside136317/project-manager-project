"""Gói nộp lưu: the archive package (AIP_hoso, TT 05/2025/TT-BNV) of a filed archive file, for handing it to another
archive. Built on the long queue (services/aip.py), kept in the archive collection (only the newest one: the nightly
sweep drops the older), downloaded by the archivist.

Metadata of the file (EAD): arcFileCode = <fonds code>.<year of its last record>.<file number>; the fonds code is the
one of PM Archive Settings, else the company's abbreviation. Of each document: its number and symbol, date, author
(autograph), summary (subject), kind (typeName), number of sheets, format.
"""

import os
import shutil
import tempfile

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime
from project_manager.project_manager.services import object_storage
from project_manager.project_manager.services.audit import log_activity
from project_manager.project_manager.services.notify import notify_user

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.services import aip
from pm_archive.pm_archive.services.locking import chunks_of


def _day(value) -> str:
    return getdate(value).strftime("%d/%m/%Y") if value else ""


def fonds_code(project: str) -> str:
    code = (frappe.db.get_single_value("PM Archive Settings", "fonds_code") or "").strip()
    if code:
        return code
    company = frappe.db.get_value("Project", project, "company")
    return frappe.db.get_value("Company", company, "abbr") or "PM"


def metadata(file) -> tuple[dict, list]:
    """(EAD of the file, [EAD of each document]) for the package."""
    fonds = fonds_code(file.project)
    year = getdate(file.end_date).year if file.end_date else now_datetime().year
    code = f"{fonds}.{year}.{file.file_number}"
    project = frappe.db.get_value("Project", file.project, ["project_name", "company"], as_dict=True)
    mode = file.access_mode or A.INTERNAL
    place = ", ".join(p for p in (frappe.db.get_value("PM Archive Storage", file.storage, "code") if file.storage else "",
                                  _("hộp {0}").format(file.box) if file.box else "") if p)
    head = {"arcFileCode": code, "title": file.title,
            "maintenance": file.retention if file.retention == A.PERMANENT else _("{0} năm").format(file.retention),
            "mode": mode, "language": "Tiếng Việt", "startDate": _day(file.start_date), "endDate": _day(file.end_date),
            "keyword": project.project_name, "totalDoc": cint(file.item_count), "numberOfPaper": cint(file.page_count),
            "numberOfPage": cint(file.page_count), "format": "Điện tử", "confidenceLevel": "Bản điện tử",
            "paperFileCode": place, "description": file.description or ""}
    documents = []
    for item in frappe.get_all("PM Archive Item", filters={"archive_file": file.name, "excluded": 0}, order_by="seq asc",
                               fields=["seq", "kind", "title", "doc_number", "doc_date", "author", "page_count", "note",
                                       "file_name", "content_type"], limit_page_length=0):
        documents.append({"arcFileCode": code, "mode": mode, "language": "Tiếng Việt", "keyword": project.project_name,
                          "numberOfPage": cint(item.page_count), "format": item.content_type or "",
                          "confidenceLevel": "Bản số hóa" if item.kind == A.UPLOAD else "Bản điện tử",
                          "description": item.note or "", "docCode": f"{code}.{item.seq:04d}", "docOrdinal": item.seq,
                          "typeName": item.kind, "codeNumber": item.doc_number or "", "issuedDate": _day(item.doc_date),
                          "organName": project.company, "subject": item.title, "autograph": item.author or ""})
    return head, documents


def request(name: str) -> dict:
    status = frappe.db.get_value("PM Archive File", name, "status")
    if status != A.FILED:
        frappe.throw(_("Chỉ lập gói cho hồ sơ đã nộp lưu"))
    frappe.db.set_value("PM Archive File", name, "aip_error", None, update_modified=False)
    frappe.enqueue("pm_archive.pm_archive.services.aip_export.run", queue="long", timeout=6 * 3600, name=name,
                   user=frappe.session.user, enqueue_after_commit=True, job_id=f"pm-archive-aip:{name}", deduplicate=True)
    return {"queued": True}


def run(name: str, user: str) -> str | None:
    """Build the package of a filed file; returns its object key (None when it failed, with the reason kept)."""
    file = frappe.get_doc("PM Archive File", name)
    items = frappe.get_all("PM Archive Item", filters={"archive_file": name, "excluded": 0}, order_by="seq asc",
                           fields=["name", "seq", "file_name", "content_type", "object_key", "collection", "file_url",
                                   "sha256", "size_bytes"], limit_page_length=0)
    head, described = metadata(file)
    documents = []
    for item, meta in zip(items, described, strict=True):
        documents.append({"suffix": os.path.splitext(item.file_name or "")[1], "sha256": item.sha256,
                          "size": item.size_bytes, "mime": item.content_type, "metadata": meta,
                          "chunks": (lambda row=item: chunks_of(row)[0])})
    folder = tempfile.mkdtemp(prefix="pm-aip-")
    try:
        path = os.path.join(folder, f"AIP_{file.file_number}.zip")
        try:
            built = aip.build_package(path, fonds_code(file.project), file.title, head, documents)
        except Exception as error:  # noqa: BLE001 (a document changed or gone, an invalid record)
            frappe.db.set_value("PM Archive File", name, "aip_error", str(error)[:500], update_modified=False)
            frappe.db.commit()
            return None
        with open(path, "rb") as stream:
            key = object_storage.put_stream(stream, os.path.basename(path), "application/zip", A.COLLECTION,
                                            built["sha256"])
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    frappe.db.set_value("PM Archive File", name, {"aip_key": key, "aip_size": built["bytes"], "aip_sha256": built["sha256"],
                                                  "aip_on": now_datetime(), "aip_by": user, "aip_error": None},
                        update_modified=False)
    log_activity("Xuất dữ liệu", "PM Archive File", name, _("Lập gói nộp lưu {0} ({1} tài liệu)").format(
        file.file_number, built["documents"]), user=user)
    notify_user(user, _("Gói nộp lưu của hồ sơ {0} đã sẵn sàng").format(file.file_number), f"/pm/luu-tru/{name}",
                "PM Archive File", name)
    frappe.db.commit()
    return key


def download(name: str):
    from werkzeug.wrappers import Response
    from project_manager.project_manager.services import files as core_files

    row = frappe.db.get_value("PM Archive File", name, ["name", "file_number", "aip_key", "aip_size"], as_dict=True)
    if not row or not row.aip_key:
        raise frappe.DoesNotExistError(_("Hồ sơ chưa có gói nộp lưu"))
    chunks, _type, length = object_storage.open_stream(row.aip_key, A.COLLECTION)
    log_activity("Tải xuống", "PM Archive File", name, _("Tải gói nộp lưu {0}").format(row.file_number))
    headers = {"Content-Disposition": core_files.disposition(f"AIP_{row.file_number}.zip", False),
               "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache"}
    if length or row.aip_size:
        headers["Content-Length"] = str(length or row.aip_size)
    return Response(chunks, status=200, content_type="application/zip", headers=headers, direct_passthrough=True)
