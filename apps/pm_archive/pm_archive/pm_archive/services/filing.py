"""Lập hồ sơ: filing a project's records into its archive files, by category (danh mục hồ sơ).

* compile(project) — can run any number of times: for each active category, the records its rules name and that no
  file of the project holds yet go into that category's open file (made when needed; once a file is filed, the next
  records go into an addendum file):
  - documents: every version that was approved; when the project is closed, also the newest version of a document
    nobody approved (noted so);
  - approved forms (their kept PDF), by template code, the rest into the category that takes every form;
  - photos (not hidden) into the category of kind Ảnh.
* on_project_close(project) (core hook project_close_handlers): compile, keep the project's data and discussions as
  files of the archive collection, and the open files wait for the archivist (Chờ nộp lưu).
* The manager orders, leaves out, describes and moves items and adds scans until a file is filed (locking.py).

Items only point at the project's files (MinIO objects, Frappe files): those never change under their key, and the
SHA-256 kept when filing proves it. What this layer makes (data, discussions, scans) goes to the archive collection.
"""

import csv
import hashlib
import io
import mimetypes
import uuid
from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate
from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import users_with_capability
from project_manager.project_manager.services import activity, closing, object_storage
from project_manager.project_manager.services.notify import notify_user
from project_manager.project_manager.services.queries import reserve_ids

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.doctype.pm_archive_category.pm_archive_category import lines

ITEM_FIELDS = ("name", "archive_file", "project", "seq", "kind", "title", "doc_number", "doc_date", "author",
               "page_count", "excluded", "note", "source_doctype", "source_name", "file_name", "content_type",
               "size_bytes", "collection", "object_key", "file_url", "sha256", "added_by",
               "owner", "modified_by", "creation", "modified", "docstatus", "idx")
CATEGORY_FIELDS = ["name", "code", "title", "retention", "required", "access_mode", "document_categories",
                   "form_templates", "all_forms", "kinds", "data_paths"]


# --- the rules of the categories ----------------------------------------------------------------------------------------

def rules() -> frappe._dict:
    """Which category takes what: the first one (in tree order) that names a document category, a form, a kind."""
    categories = frappe.get_all("PM Archive Category", filters={"is_group": 0, "is_active": 1}, fields=CATEGORY_FIELDS,
                                order_by="lft asc", limit_page_length=0)
    out = frappe._dict(categories={c.name: c for c in categories}, documents={}, forms={}, kinds={}, paths=[],
                       all_forms=None)
    for category in categories:
        for value in lines(category.document_categories):
            out.documents.setdefault(value, category)
        for value in lines(category.form_templates):
            out.forms.setdefault(value, category)
        for value in lines(category.kinds):
            out.kinds.setdefault(value, category)
        out.paths += [(prefix, category) for prefix in lines(category.data_paths)]
        if category.all_forms and out.all_forms is None:
            out.all_forms = category
    out.paths.sort(key=lambda pair: -len(pair[0]))  # the longest prefix wins
    return out


# --- files --------------------------------------------------------------------------------------------------------------

def _project(project: str) -> frappe._dict:
    return frappe.db.get_value("Project", project, ["name", "project_name", "pm_code", "pm_state"], as_dict=True)


def _next_number(project: frappe._dict) -> str:
    prefix = project.pm_code or project.name
    number = frappe.db.count("PM Archive File", {"project": project.name}) + 1
    while frappe.db.exists("PM Archive File", {"file_number": f"{prefix}-{number:02d}"}):
        number += 1
    return f"{prefix}-{number:02d}"


def open_file(project: str, category: frappe._dict) -> str:
    """The category's file still being built, else a new one (an addendum when one was filed already)."""
    name = frappe.db.get_value("PM Archive File", {"project": project, "category": category.name,
                                                   "status": ["!=", A.FILED]}, "name", order_by="creation desc")
    if name:
        return name
    info = _project(project)
    addendum = bool(frappe.db.exists("PM Archive File", {"project": project, "category": category.name, "status": A.FILED}))
    title = category.title + (_(" (bổ sung)") if addendum else "")
    doc = frappe.get_doc({
        "doctype": "PM Archive File", "project": project, "category": category.name,
        "file_number": _next_number(info), "title": f"{title} — {info.project_name}"[:140],
        "status": A.WAITING if info.pm_state == closing.CLOSED else A.DRAFT,
        "waiting_since": now_datetime() if info.pm_state == closing.CLOSED else None,
        "access_mode": category.access_mode or A.INTERNAL, "retention": category.retention or "10",
        "is_addendum": int(addendum)})
    doc.insert(ignore_permissions=True)
    return doc.name


def expires_on(end_date, retention: str):
    """The last day kept: the end of the year that many years after the file's last record (none when permanent)."""
    if not end_date or not str(retention or "").isdigit():
        return None
    return date(getdate(end_date).year + int(retention), 12, 31)


def refresh(name: str) -> None:
    """Counts, dates and the end of retention of a file from its items (left-out ones aside)."""
    count, pages, first, last = frappe.db.sql(
        """select count(*), sum(ifnull(page_count, 0)), min(doc_date), max(doc_date) from `tabPM Archive Item`
           where archive_file = %s and excluded = 0""", name)[0]
    retention = frappe.db.get_value("PM Archive File", name, "retention")
    frappe.db.set_value("PM Archive File", name, {
        "item_count": cint(count), "page_count": cint(pages), "start_date": first, "end_date": last,
        "expires_on": expires_on(last, retention)}, update_modified=False)


def insert_items(file: str, project: str, items: list[dict]) -> int:
    """Bulk insert of items at the end of a file."""
    if not items:
        return 0
    seq = cint(frappe.db.sql("select max(seq) from `tabPM Archive Item` where archive_file = %s", file)[0][0])
    now, user = now_datetime(), frappe.session.user
    rows = []
    for number, item in zip(reserve_ids("PM Archive Item", len(items)), items, strict=True):
        seq += 1
        values = {**item, "name": number, "archive_file": file, "project": project, "seq": seq, "excluded": 0,
                  "page_count": cint(item.get("page_count")), "size_bytes": cint(item.get("size_bytes")),
                  "added_by": user, "owner": user, "modified_by": user, "creation": now, "modified": now,
                  "docstatus": 0, "idx": 0}
        rows.append(tuple(values.get(field) for field in ITEM_FIELDS))
    frappe.db.bulk_insert("PM Archive Item", ITEM_FIELDS, rows, chunk_size=500)
    return len(rows)


# --- what the rules find ------------------------------------------------------------------------------------------------

def _author(user: str | None) -> str | None:
    """The person's name as a catalogue shows it (the login when the account has no name)."""
    if not user:
        return None
    memo = getattr(frappe.local, "pm_archive_authors", None)
    if memo is None:
        memo = frappe.local.pm_archive_authors = {}
    if user not in memo:
        memo[user] = frappe.utils.get_fullname(user) or user
    return memo[user]


def _documents(project: str, closed: bool, found: frappe._dict):
    titles = {d.name: d for d in frappe.get_all("PM Document", filters={"project": project},
                                                fields=["name", "title", "category"], limit_page_length=0)}
    versions = defaultdict(list)
    for v in frappe.get_all("PM Document Version", filters={"project": project}, order_by="version_no asc",
                            fields=["name", "document", "version_no", "file_name", "content_type", "size_bytes", "sha256",
                                    "object_key", "uploaded_by", "uploaded_on", "approved_by", "approved_on"],
                            limit_page_length=0):
        versions[v.document].append(v)
    for name, doc in titles.items():
        category = found.documents.get(doc.category)
        if not category or not versions[name]:
            continue
        picked = [v for v in versions[name] if v.approved_by]
        unapproved = not picked
        if unapproved:
            if not closed:
                continue  # until someone approves one, or the project closes
            picked = [versions[name][-1]]
        for v in picked:
            yield category, {
                "kind": A.DOCUMENT, "source_doctype": "PM Document Version", "source_name": str(v.name),
                "title": _("{0} (bản {1})").format(doc.title, v.version_no), "doc_date": getdate(v.approved_on or v.uploaded_on),
                "author": _author(v.uploaded_by), "file_name": v.file_name, "content_type": v.content_type, "size_bytes": v.size_bytes,
                "collection": "documents", "object_key": v.object_key, "sha256": v.sha256,
                "note": _("Bản chưa được duyệt khi đóng dự án") if unapproved else None}


def _forms(project: str, found: frappe._dict):
    from project_manager.project_manager.services import form_output

    for f in frappe.get_all("PM Form Submission", filters={"project": project, "state": C.SUB_APPROVED},
                            fields=["name", "template_code", "title", "reviewed_on", "submitted_by", "pdf_file", "pdf_hash"],
                            order_by="name asc", limit_page_length=0):
        category = found.forms.get(f.template_code) or found.all_forms
        if not category:
            continue
        if not f.pdf_file:  # the kept PDF is made after the approval, in a job: make it now
            form_output.freeze(frappe.get_doc("PM Form Submission", f.name))
            f.pdf_file, f.pdf_hash = frappe.db.get_value("PM Form Submission", f.name, ["pdf_file", "pdf_hash"])
        yield category, {
            "kind": A.FORM, "source_doctype": "PM Form Submission", "source_name": str(f.name), "title": f.title,
            "doc_number": f"{f.template_code}-{f.name}", "doc_date": getdate(f.reviewed_on) if f.reviewed_on else None,
            "author": _author(f.submitted_by), "file_name": f"bieu-mau-{f.name}.pdf", "content_type": "application/pdf",
            "file_url": f.pdf_file, "sha256": f.pdf_hash}


def _photos(project: str, found: frappe._dict):
    category = found.kinds.get(A.PHOTO)
    if not category:
        return
    for m in frappe.get_all("PM Media", filters={"project": project, "is_deleted": 0}, order_by="name asc",
                            fields=["name", "file_name", "content_type", "size_bytes", "taken_at", "creation",
                                    "uploaded_by", "object_key"], limit_page_length=0):
        yield category, {
            "kind": A.PHOTO, "source_doctype": "PM Media", "source_name": str(m.name), "title": m.file_name,
            "doc_date": getdate(m.taken_at or m.creation), "author": _author(m.uploaded_by), "file_name": m.file_name,
            "content_type": m.content_type, "size_bytes": m.size_bytes, "collection": "media", "object_key": m.object_key}


def compile(project: str, closed: bool | None = None) -> dict:
    """File what the rules find and no file of the project holds yet. Returns {"added", "files"}."""
    if closed is None:
        closed = frappe.db.get_value("Project", project, "pm_state") == closing.CLOSED
    found = rules()
    held = {(r.source_doctype, r.source_name) for r in frappe.get_all(
        "PM Archive Item", filters={"project": project}, fields=["source_doctype", "source_name"], limit_page_length=0)}
    groups = defaultdict(list)
    for source in (_documents(project, closed, found), _forms(project, found), _photos(project, found)):
        for category, item in source:
            key = (item["source_doctype"], item["source_name"])
            if key not in held:
                held.add(key)
                groups[category.name].append(item)
    return _place(project, found, groups)


def _place(project: str, found: frappe._dict, groups: dict) -> dict:
    added, files = 0, []
    for name, items in groups.items():
        file = open_file(project, found.categories[name])
        added += insert_items(file, project, items)
        refresh(file)
        files.append(file)
    return {"added": added, "files": files}


# --- when the project closes --------------------------------------------------------------------------------------------

def _stored(content, filename: str, content_type: str) -> dict:
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    key = object_storage.put(data, filename, content_type, A.COLLECTION)
    return {"file_name": filename, "content_type": content_type, "size_bytes": len(data), "collection": A.COLLECTION,
            "object_key": key, "sha256": hashlib.sha256(data).hexdigest()}


def _discussions_csv(project: str) -> bytes:
    rows = frappe.db.sql("""select a.creation, a.actor, a.reference_doctype, a.reference_name, t.subject, a.content
                            from `tabPM Activity` a left join `tabTask` t on t.name = a.task
                            where a.project = %s and a.activity_type = 'Bình luận' and a.is_deleted = 0
                            order by a.name""", project)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Thời điểm", "Người viết", "Đối tượng", "Mã", "Công việc", "Nội dung"])
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return ("﻿" + out.getvalue()).encode("utf-8")


def snapshot(project: str) -> dict:
    """The project's data files (as the person closing it may read them) and its discussions, kept in the archive."""
    found, today, stamp = rules(), getdate(nowdate()), now_datetime().strftime("%Y%m%d-%H%M%S")
    user = frappe.session.user
    groups = defaultdict(list)
    for part in closing.data_parts(project):
        category = next((c for prefix, c in found.paths if part["path"].startswith(prefix)), None) or found.kinds.get(A.DATA)
        if not category:
            continue
        name = part["path"].rsplit("/", 1)[-1]
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        groups[category.name].append({
            "kind": A.DATA, "source_doctype": "Dữ liệu dự án", "source_name": f"{part['path']}@{stamp}",
            "title": _("Dữ liệu dự án: {0}").format(part["path"]), "doc_date": today, "author": _author(user),
            **_stored(part["content"], name, content_type)})
    category = found.kinds.get(A.DISCUSSION)
    if category:
        groups[category.name].append({
            "kind": A.DISCUSSION, "source_doctype": "Trao đổi dự án", "source_name": f"{project}@{stamp}",
            "title": _("Trao đổi của dự án đến ngày {0}").format(today.strftime("%d/%m/%Y")), "doc_date": today,
            "author": _author(user), **_stored(_discussions_csv(project), f"trao-doi-{stamp}.csv", "text/csv")})
    return _place(project, found, groups)


def _wait(names) -> None:
    """These files wait for the archivist from now on."""
    now = now_datetime()
    for name in names:
        frappe.db.set_value("PM Archive File", name, {"status": A.WAITING, "waiting_since": now}, update_modified=False)


def missing(project: str) -> list[dict]:
    """The required categories with no record in the project's files."""
    required = frappe.get_all("PM Archive Category", filters={"is_group": 0, "is_active": 1, "required": 1},
                              fields=["name", "code", "title"], order_by="lft asc")
    held = set(frappe.get_all("PM Archive File", filters={"project": project, "item_count": [">", 0]}, pluck="category"))
    return [{"code": c.code, "title": c.title} for c in required if c.name not in held]


def on_project_close(project: str) -> None:
    """Core hook project_close_handlers."""
    compile(project, closed=True)
    snapshot(project)
    _wait(frappe.get_all("PM Archive File", filters={"project": project, "status": A.DRAFT}, pluck="name"))
    gaps = missing(project)
    files = frappe.db.count("PM Archive File", {"project": project, "status": A.WAITING})
    text = _("Hồ sơ lưu trữ chờ nộp lưu: {0} hồ sơ").format(files)
    if gaps:
        text += _("; còn thiếu: {0}").format(", ".join(f"{g['code']} {g['title']}" for g in gaps))
    activity.record("Project", project, "Hệ thống", text, data={"waiting": files, "missing": gaps})
    info = _project(project)
    link = f"/pm/du-an/{project}/ho-so-luu-tru"
    manager = frappe.db.get_value("Project", project, "pm_manager")
    for user in {*users_with_capability(A.MANAGE_ALL), *([manager] if manager else [])}:
        notify_user(user, _("{0} đã đóng: {1}").format(info.project_name, text), link, "Project", project)


# --- what the manager changes before filing -----------------------------------------------------------------------------

def _open(name: str) -> frappe._dict:
    file = frappe.db.get_value("PM Archive File", name, ["name", "project", "status", "access_mode"], as_dict=True)
    if not file:
        raise frappe.DoesNotExistError(_("Không tìm thấy hồ sơ"))
    if file.status == A.FILED:
        frappe.throw(_("Hồ sơ đã nộp lưu, không sửa được"))
    return file


def _item(item) -> frappe._dict:
    row = frappe.db.get_value("PM Archive Item", cint(item), ["name", "archive_file", "project"], as_dict=True)
    if not row:
        raise frappe.DoesNotExistError(_("Không tìm thấy tài liệu"))
    return row


def reorder(file: str, order: list) -> None:
    """Number the items in this order (the ones not named keep theirs, after)."""
    _open(file)
    names = [cint(n) for n in order or []]
    known = set(frappe.get_all("PM Archive Item", filters={"archive_file": file}, pluck="name", limit_page_length=0))
    if set(names) - known:
        frappe.throw(_("Có tài liệu không thuộc hồ sơ này"))
    rest = frappe.get_all("PM Archive Item", filters={"archive_file": file, "name": ["not in", names or [0]]},
                          pluck="name", order_by="seq asc", limit_page_length=0)
    for seq, name in enumerate([*names, *rest], 1):
        frappe.db.set_value("PM Archive Item", name, "seq", seq, update_modified=False)


DESCRIBED = ("title", "doc_number", "doc_date", "author", "page_count", "note")


def describe(item, values: dict) -> None:
    row = _item(item)
    _open(row.archive_file)
    changes = {k: (values.get(k) or None) for k in DESCRIBED if k in (values or {})}
    if "page_count" in changes:
        changes["page_count"] = max(0, cint(changes["page_count"]))  # (an Int column is never null)
    if "title" in changes and not (changes["title"] or "").strip():
        frappe.throw(_("Trích yếu không được trống"))
    if changes:
        frappe.db.set_value("PM Archive Item", row.name, changes)
        refresh(row.archive_file)


def set_excluded(item, excluded) -> None:
    row = _item(item)
    _open(row.archive_file)
    frappe.db.set_value("PM Archive Item", row.name, "excluded", 1 if cint(excluded) else 0)
    refresh(row.archive_file)


def move(item, target: str) -> None:
    """To another file of the same project, at its end (both still being built)."""
    row = _item(item)
    source = _open(row.archive_file)
    to = _open(target)
    if to.project != source.project:
        frappe.throw(_("Chỉ chuyển được sang hồ sơ của cùng dự án"))
    seq = cint(frappe.db.sql("select max(seq) from `tabPM Archive Item` where archive_file = %s", target)[0][0]) + 1
    frappe.db.set_value("PM Archive Item", row.name, {"archive_file": target, "seq": seq})
    refresh(source.name)
    refresh(target)


def upload(file: str, raw: bytes, filename: str, values: dict | None = None) -> dict:
    """A scan (or any record not in the project) added to a file."""
    target = _open(file)
    filename = (filename or "").strip().replace("\\", "/").rsplit("/", 1)[-1][:140]
    if not raw or not filename:
        frappe.throw(_("Chưa có tệp"))
    if len(raw) > A.MAX_UPLOAD_BYTES:
        frappe.throw(_("Tệp phải nhỏ hơn 200 MB"))
    from project_manager.project_manager.services.documents import BLOCKED

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in BLOCKED:
        frappe.throw(_("Không nhận tệp .{0}").format(extension))
    values = values or {}
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    item = {"kind": A.UPLOAD, "source_doctype": "Tệp tải lên", "source_name": uuid.uuid4().hex,
            "title": (values.get("title") or filename).strip()[:500], "doc_number": values.get("doc_number") or None,
            "doc_date": getdate(values["doc_date"]) if values.get("doc_date") else getdate(nowdate()),
            "author": values.get("author") or None, "page_count": max(0, cint(values.get("page_count"))) or None,
            **_stored(raw, filename, content_type)}
    insert_items(target.name, target.project, [item])
    refresh(target.name)
    return {"file": target.name}


def set_paper(file: str, storage: str | None, box: str | None, note: str | None) -> None:
    """Where the paper originals are. The archivist may change it after filing too (boxes move)."""
    from pm_archive.pm_archive.permissions import manages_everything

    row = frappe.db.get_value("PM Archive File", file, ["name", "status"], as_dict=True)
    if not row:
        raise frappe.DoesNotExistError(_("Không tìm thấy hồ sơ"))
    if row.status == A.FILED and not manages_everything():
        frappe.throw(_("Hồ sơ đã nộp lưu: chỉ người lưu trữ đổi được chỗ để bản giấy"))
    if storage and not frappe.db.exists("PM Archive Storage", storage):
        frappe.throw(_("Không có chỗ để {0}").format(storage))
    frappe.db.set_value("PM Archive File", file, {"storage": storage or None, "box": (box or "").strip() or None,
                                                  "paper_note": (note or "").strip() or None})


def request_filing(project: str) -> int:
    """The manager says the files are ready: they wait for the archivist."""
    names = frappe.get_all("PM Archive File", filters={"project": project, "status": A.DRAFT}, pluck="name")
    _wait(names)
    if names:
        link = f"/pm/du-an/{project}/ho-so-luu-tru"
        info = _project(project)
        for user in users_with_capability(A.MANAGE_ALL):
            notify_user(user, _("{0}: {1} hồ sơ chờ nộp lưu").format(info.project_name, len(names)), link, "Project", project)
    return len(names)


def compile_running() -> None:
    """Scheduler (daily, long queue): keep the files of the running projects up to date."""
    from project_manager.project_manager.services.errors import log_exception

    for project in frappe.get_all("Project", filters={"pm_is_template": 0, "pm_state": ["not in", [closing.CLOSED, "Hủy"]]},
                                  pluck="name", limit_page_length=0):
        try:
            compile(project, closed=False)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            log_exception("Lập hồ sơ lưu trữ", f"Dự án {project}")
