"""What the archive screens read: a project's files (the project tab), one file and its items, the archive across
projects (/pm/luu-tru), and the download of an item. Every read checks permissions.py; every download is logged."""

import frappe
from frappe import _
from frappe.utils import cint, getdate
from project_manager.project_manager.services import files as core_files
from project_manager.project_manager.services.audit import log_activity

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive import permissions as P
from pm_archive.pm_archive.services import filing

FILE_FIELDS = ["name", "project", "category", "file_number", "title", "status", "access_mode", "is_addendum",
               "start_date", "end_date", "retention", "expires_on", "item_count", "page_count", "storage", "box",
               "paper_note", "description", "locked_by", "locked_on", "manifest_sha256", "lock_total", "lock_done",
               "lock_error", "waiting_since", "aip_on", "aip_by", "aip_size", "aip_sha256", "aip_error"]
ITEM_FIELDS = ["name", "seq", "kind", "title", "doc_number", "doc_date", "author", "page_count", "excluded", "note",
               "source_doctype", "source_name", "file_name", "content_type", "size_bytes", "sha256"]
MAX_ITEMS = 500
PAGE = 50


def _project_info(names) -> dict:
    if not names:
        return {}
    return {r.name: r for r in frappe.get_all("Project", filters={"name": ["in", list(names)]},
                                              fields=["name", "project_name", "pm_code", "pm_state"])}


def _visible(rows) -> list:
    return [r for r in rows if P.may_read(r.project, r.access_mode)]


def overview(project: str) -> dict:
    """The project tab: its files by category, the required categories with nothing yet, the counts by state."""
    if not frappe.db.exists("Project", project):
        raise frappe.DoesNotExistError(_("Không tìm thấy dự án"))
    managing = P.may_manage(project)
    if not managing and not P.may_read(project, A.INTERNAL):
        raise frappe.PermissionError(_("Bạn không xem được hồ sơ lưu trữ của dự án này"))
    files = _visible(frappe.get_all("PM Archive File", filters={"project": project}, fields=FILE_FIELDS,
                                    order_by="file_number asc", limit_page_length=0))
    categories = {c.name: c for c in frappe.get_all("PM Archive Category", fields=["name", "code", "title"])}
    for row in files:
        category = categories.get(row.category)
        row["category_label"] = f"{category.code} {category.title}" if category else row.category
    info = _project_info([project])[project]
    return {
        "project": info, "files": files, "missing": filing.missing(project),
        "counts": {state: sum(1 for f in files if f.status == state) for state in A.FILE_STATES},
        "can": {"manage": managing, "file": P.manages_everything(),
                "request": managing and any(f.status == A.DRAFT for f in files)},
    }


def _load(name: str) -> frappe._dict:
    row = frappe.db.get_value("PM Archive File", name, FILE_FIELDS, as_dict=True)
    if not row:
        raise frappe.DoesNotExistError(_("Không tìm thấy hồ sơ"))
    if not P.may_read(row.project, row.access_mode):
        raise frappe.PermissionError(_("Bạn không xem được hồ sơ này"))
    return row


def detail(name: str, start=0, limit=MAX_ITEMS) -> dict:
    """One file: its description and its items in order (a page of them)."""
    row = _load(name)
    start, limit = max(0, cint(start)), max(1, min(cint(limit) or MAX_ITEMS, MAX_ITEMS))
    items = frappe.get_all("PM Archive Item", filters={"archive_file": name}, fields=ITEM_FIELDS, order_by="seq asc",
                           limit_start=start, limit_page_length=limit)
    total = frappe.db.count("PM Archive Item", {"archive_file": name})
    category = frappe.db.get_value("PM Archive Category", row.category, ["code", "title"], as_dict=True)
    storage = frappe.db.get_value("PM Archive Storage", row.storage, ["code", "title", "kind"], as_dict=True) if row.storage else None
    others = frappe.get_all("PM Archive File", filters={"project": row.project, "status": ["!=", A.FILED],
                                                        "name": ["!=", name]},
                            fields=["name", "file_number", "title"], order_by="file_number asc")
    open_ = row.status != A.FILED
    managing = P.may_manage(row.project)
    return {
        "file": row, "category": category, "storage": storage, "project": _project_info([row.project])[row.project],
        "items": items, "total": total, "start": start, "others": others if managing else [],
        "can": {"edit": open_ and managing, "file": open_ and P.manages_everything(),
                "paper": (open_ and managing) or P.manages_everything(), "export": row.status == A.FILED},
    }


def listing(filters: dict | None = None, before: str | None = None, limit=PAGE) -> dict:
    """Every file the user may read, newest file number first, filtered; keyset paging on the name."""
    filters = filters or {}
    conditions, values = [], {}
    condition = P.file_condition()
    if condition:
        conditions.append(condition)
    for key in ("project", "category", "status"):
        if filters.get(key):
            conditions.append(f"`tabPM Archive File`.{key} = %({key})s")
            values[key] = filters[key]
    if filters.get("year"):
        conditions.append("year(`tabPM Archive File`.end_date) = %(year)s")
        values["year"] = cint(filters["year"])
    if filters.get("expiring"):
        conditions.append("`tabPM Archive File`.expires_on is not null and `tabPM Archive File`.expires_on <= %(until)s")
        values["until"] = getdate(filters["expiring"])
    text = (filters.get("search") or "").strip()[:100]
    if text:
        conditions.append("""(`tabPM Archive File`.title like %(text)s or `tabPM Archive File`.file_number like %(text)s
                               or `tabPM Archive File`.name in (select archive_file from `tabPM Archive Item`
                                                                 where title like %(text)s))""")
        values["text"] = f"%{text}%"
    if before:
        conditions.append("`tabPM Archive File`.name < %(before)s")
        values["before"] = before
    limit = max(1, min(cint(limit) or PAGE, 200))
    where = " and ".join(conditions) or "1=1"
    rows = frappe.db.sql(f"""select {', '.join(f'`tabPM Archive File`.{f}' for f in FILE_FIELDS)}
                             from `tabPM Archive File` where {where}
                             order by `tabPM Archive File`.name desc limit {limit + 1}""", values, as_dict=True)
    more = len(rows) > limit
    rows = rows[:limit]
    projects = _project_info({r.project for r in rows})
    for row in rows:
        project = projects.get(row.project)
        row["project_name"] = project.project_name if project else row.project
    waiting = frappe.db.sql(f"""select count(*) from `tabPM Archive File` where {condition or '1=1'}
                                and `tabPM Archive File`.status = %(waiting)s""", {"waiting": A.WAITING})[0][0]
    last = frappe.get_all("PM Archive Check", fields=["name", "run_on", "status", "checked", "changed", "missing"],
                          order_by="run_on desc", limit_page_length=1) if P.manages_everything() else []
    return {"rows": rows, "next": rows[-1].name if more else None, "waiting": waiting,
            "last_check": last[0] if last else None, "can": {"file": P.manages_everything()}}


def download(item, inline=0):
    """The content of an item, after the file's permission; logged."""
    from pm_archive.pm_archive.services.locking import MissingContent, chunks_of

    row = frappe.db.get_value("PM Archive Item", cint(item), ["name", "archive_file", "title", "file_name", "content_type",
                                                              "object_key", "collection", "file_url"], as_dict=True)
    if not row:
        raise frappe.DoesNotExistError(_("Không tìm thấy tài liệu"))
    file = _load(row.archive_file)
    try:
        chunks, stored_type, length = chunks_of(row)
    except MissingContent:
        frappe.throw(_("Tệp của tài liệu này không còn: hãy báo người lưu trữ"))
    log_activity("Tải xuống", "PM Archive Item", str(row.name), _("Tải tài liệu {0} của hồ sơ {1}").format(
        row.title or row.file_name, file.file_number))
    from werkzeug.wrappers import Response

    content_type = row.content_type or stored_type or "application/octet-stream"
    headers = {"Content-Disposition": core_files.disposition(row.file_name or "tai-lieu",
                                                              bool(cint(inline)) and content_type in core_files.INLINE_TYPES),
               "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache"}
    if length:
        headers["Content-Length"] = str(length)
    return Response(chunks, status=200, content_type=content_type, headers=headers, direct_passthrough=True)


def storages() -> list[dict]:
    return frappe.get_all("PM Archive Storage", filters={"is_active": 1},
                          fields=["name", "code", "title", "kind", "parent_pm_archive_storage as parent", "is_group"],
                          order_by="lft asc", limit_page_length=0)


def checks(limit=20) -> list[dict]:
    if not P.manages_everything():
        raise frappe.PermissionError(_("Chỉ người lưu trữ xem được các lần kiểm tra"))
    return frappe.get_all("PM Archive Check", fields=["name", "run_on", "trigger", "scope", "status", "checked",
                                                      "changed", "missing", "finished_on"],
                          order_by="run_on desc", limit_page_length=max(1, min(cint(limit) or 20, 100)))


def nav_items(user: str) -> list[dict]:
    """Core hook pm_nav_items: "Lưu trữ hồ sơ" for whoever may read some archive (the archivist sees how many files
    wait for filing)."""
    if not (P.sees_everything(user) or P.readable_projects(user) or P.managed_projects(user)):
        return []
    item = {"group": "Công việc", "label": "Lưu trữ hồ sơ", "route": "/pm/luu-tru", "icon": "archive"}
    if P.manages_everything(user):
        waiting = frappe.db.count("PM Archive File", {"status": A.WAITING})
        if waiting:
            item["badge"] = waiting
    return [item]
