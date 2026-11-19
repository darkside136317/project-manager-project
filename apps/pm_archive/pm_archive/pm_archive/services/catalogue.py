"""The archive's catalogues, as reports of the core's report hub (hook pm_reports; Excel, CSV, PDF and print come from
the framework, with the company's heading):

* Mục lục hồ sơ: the files, by number: title, period, sheets, items, retention, where the paper is, state;
* Mục lục văn bản: the items of one file, in order: number and symbol, date, author, summary, sheets, note.
Each keeps to the files the user may read (permissions.py).
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate
from project_manager.project_manager.services.reports.base import Report, col, integer, link, select

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive import permissions as P

GROUP = "Lưu trữ"


def _period(start, end) -> str:
    if not start and not end:
        return ""
    first = getdate(start).strftime("%d/%m/%Y") if start else ""
    last = getdate(end).strftime("%d/%m/%Y") if end else ""
    return first if first == last else f"{first} – {last}"


def _retention(value) -> str:
    return value if value == A.PERMANENT else (_("{0} năm").format(value) if value else "")


def _files(filters, page, size):
    conditions, values = [], {}
    condition = P.file_condition()
    if condition:
        conditions.append(condition)
    if filters.get("project"):
        conditions.append("`tabPM Archive File`.project = %(project)s")
        values["project"] = filters["project"]
    if filters.get("status"):
        conditions.append("`tabPM Archive File`.status = %(status)s")
        values["status"] = filters["status"]
    if filters.get("year"):
        conditions.append("year(`tabPM Archive File`.end_date) = %(year)s")
        values["year"] = cint(filters["year"])
    where = " and ".join(conditions) or "1=1"
    total = frappe.db.sql(f"select count(*) from `tabPM Archive File` where {where}", values)[0][0]
    columns = ", ".join(f"`tabPM Archive File`.{c}" for c in (
        "name", "project", "file_number", "title", "start_date", "end_date", "page_count", "item_count", "retention",
        "status", "storage", "box", "paper_note", "description"))
    rows = frappe.db.sql(f"""select {columns}, p.project_name
                             from `tabPM Archive File` join `tabProject` p on p.name = `tabPM Archive File`.project
                             where {where} order by p.project_name, `tabPM Archive File`.file_number
                             limit {int(size)} offset {int((page - 1) * size)}""", values, as_dict=True)
    places = {s.name: s.title for s in frappe.get_all("PM Archive Storage", fields=["name", "title"])}
    out = []
    for number, row in enumerate(rows, (page - 1) * size + 1):
        place = ", ".join(p for p in (places.get(row.storage), _("hộp {0}").format(row.box) if row.box else "") if p)
        out.append({"stt": number, "file": row.name, "file_number": row.file_number, "title": row.title,
                    "project_name": row.project_name, "project": row.project,
                    "period": _period(row.start_date, row.end_date), "page_count": row.page_count or None,
                    "item_count": row.item_count, "retention": _retention(row.retention), "place": place,
                    "status": row.status, "note": row.paper_note or row.description or ""})
    return {"rows": out, "total": total}


def _items(filters, page, size):
    from pm_archive.pm_archive.services.register import _load

    file = _load(filters["archive_file"])
    total = frappe.db.count("PM Archive Item", {"archive_file": file.name, "excluded": 0})
    rows = frappe.get_all("PM Archive Item", filters={"archive_file": file.name, "excluded": 0},
                          fields=["seq", "doc_number", "doc_date", "author", "title", "page_count", "note", "kind"],
                          order_by="seq asc", limit_start=(page - 1) * size, limit_page_length=size)
    info = [(_("Hồ sơ"), f"{file.file_number} {file.title}"), (_("Thời hạn bảo quản"), _retention(file.retention)),
            (_("Trạng thái"), file.status)]
    return {"rows": [{**row, "doc_date": getdate(row.doc_date).strftime("%d/%m/%Y") if row.doc_date else ""}
                     for row in rows], "total": total, "info": info}


def reports() -> list[Report]:
    return [
        Report(slug="muc-luc-ho-so", title="Mục lục hồ sơ", group=GROUP, icon="archive", order=10, paged=True,
               description="Các hồ sơ lưu trữ theo dự án và số hồ sơ: tiêu đề, thời gian, số tờ, số tài liệu, thời hạn "
                           "bảo quản, chỗ để bản giấy, trạng thái.",
               run=_files,
               filters=[link("project", "Dự án", "Project"),
                        select("status", "Trạng thái", ["", *A.FILE_STATES]),
                        integer("year", "Năm kết thúc")],
               columns=[col("stt", "STT", "Int"), col("file_number", "Số hồ sơ", link="/luu-tru/{file}"),
                        col("title", "Tiêu đề hồ sơ"), col("project_name", "Dự án", link="/du-an/{project}"),
                        col("period", "Thời gian"), col("page_count", "Số tờ", "Int"),
                        col("item_count", "Số tài liệu", "Int"), col("retention", "Thời hạn bảo quản"),
                        col("place", "Chỗ để bản giấy"), col("status", "Trạng thái"), col("note", "Ghi chú")]),
        Report(slug="muc-luc-van-ban", title="Mục lục văn bản trong hồ sơ", group=GROUP, icon="list-ordered",
               order=20, paged=True, landscape=True,
               description="Các tài liệu của một hồ sơ lưu trữ theo thứ tự: số và ký hiệu, ngày, tác giả, trích yếu, số "
                           "tờ, ghi chú.",
               run=_items, filters=[link("archive_file", "Hồ sơ", "PM Archive File", reqd=1)],
               columns=[col("seq", "STT", "Int"), col("doc_number", "Số, ký hiệu"), col("doc_date", "Ngày"),
                        col("author", "Tác giả"), col("title", "Trích yếu nội dung"), col("page_count", "Số tờ", "Int"),
                        col("kind", "Loại"), col("note", "Ghi chú")]),
    ]
