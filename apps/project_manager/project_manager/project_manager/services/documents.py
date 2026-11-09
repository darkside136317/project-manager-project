"""Project documents with numbered versions (PM Document + PM Document Version), kept in MinIO.

* Whoever may change the project's data uploads a document or a new version of it; a version is never changed or
  deleted afterwards (a wrong file is replaced by the next version).
* Approving a version needs the project role's "task.approve"; the previously approved version, and older drafts
  nobody approved, become "Thay thế".
  Until the newest version is approved, the document shows both: the newest draft and the one in force.
* A document tied to a task follows that task's visibility, the others the project's.
"""

import hashlib
import mimetypes

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from project_manager.project_manager.policy import (
    assert_project_writable,
    can_see_task,
    get_access,
    has_project_capability,
    project_in,
)
from project_manager.project_manager.services import activity, object_storage

DRAFT, APPROVED, REPLACED = "Nháp", "Đã duyệt", "Thay thế"
MAX_BYTES = 100 * 1024 * 1024
BLOCKED = frozenset({"exe", "bat", "cmd", "com", "msi", "dll", "scr", "ps1", "vbs", "js", "jar", "sh", "php",
                     "html", "htm", "svg", "xhtml", "hta"})
LIST_FIELDS = ["name", "project", "task", "title", "category", "status", "description", "current_version",
               "approved_version", "file_name", "content_type", "size_bytes", "updated_on", "owner"]
VERSION_FIELDS = ["name", "document", "project", "task", "version_no", "status", "file_name", "content_type",
                  "size_bytes", "sha256", "object_key", "note", "uploaded_by", "uploaded_on", "approved_by",
                  "approved_on"]


def categories() -> list[str]:
    return [option for option in (frappe.get_meta("PM Document").get_field("category").options or "").split("\n")
            if option]


def _may_read(project: str, task: str | None, user: str | None = None) -> bool:
    access = get_access(user)
    if access.kind == "admin":
        return True
    if task:
        return can_see_task(task, project, access.user)
    return project_in(access.read, project)


def _load(name: str):
    doc = frappe.db.get_value("PM Document", name, LIST_FIELDS, as_dict=True)
    if not doc or not _may_read(doc.project, doc.task):
        raise frappe.DoesNotExistError(_("Không tìm thấy tài liệu"))
    return doc


def _check_file(raw: bytes, filename: str) -> tuple[str, str]:
    filename = (filename or "").strip().replace("\\", "/").rsplit("/", 1)[-1][:140]
    if not filename:
        frappe.throw(_("Thiếu tên tệp"))
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in BLOCKED:
        frappe.throw(_("Không nhận tệp .{0}").format(extension))
    if not raw:
        frappe.throw(_("Tệp rỗng"))
    if len(raw) > MAX_BYTES:
        frappe.throw(_("Tệp phải nhỏ hơn 100 MB"))
    return filename, mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _task_of(project: str, task: str | None) -> str | None:
    if not task:
        return None
    if frappe.db.get_value("Task", task, "project") != project or not can_see_task(task, project):
        frappe.throw(_("Công việc không thuộc dự án này"))
    return task


def create(project: str, title: str, raw: bytes, filename: str, category: str = "Khác", task: str | None = None,
           description: str = "", note: str = "") -> dict:
    assert_project_writable(project)
    title = (title or "").strip()[:140]
    if not title:
        frappe.throw(_("Nhập tên tài liệu"))
    if category not in categories():
        category = "Khác"
    task = _task_of(project, task)
    filename, content_type = _check_file(raw, filename)
    key = object_storage.put(raw, filename, content_type, "documents")
    doc = frappe.get_doc({"doctype": "PM Document", "project": project, "task": task, "title": title,
                          "category": category, "status": DRAFT, "description": (description or "").strip()[:2000],
                          "current_version": 1, "approved_version": 0, "file_name": filename,
                          "content_type": content_type, "size_bytes": len(raw), "updated_on": now_datetime()})
    doc.insert(ignore_permissions=True)
    _add_version(doc.name, project, task, 1, raw, key, filename, content_type, note)
    _log(project, task, _("Tải lên tài liệu {0} (bản 1)").format(title), doc.name)
    _index(doc.name)
    return detail(doc.name)


def _add_version(document, project, task, number, raw, key, filename, content_type, note) -> None:
    frappe.get_doc({"doctype": "PM Document Version", "document": document, "project": project, "task": task,
                    "version_no": number, "status": DRAFT, "file_name": filename, "content_type": content_type,
                    "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "object_key": key,
                    "note": (note or "").strip()[:1000], "uploaded_by": frappe.session.user,
                    "uploaded_on": now_datetime()}).insert(ignore_permissions=True)


def add_version(name: str, raw: bytes, filename: str, note: str = "") -> dict:
    doc = _lock(name)
    assert_project_writable(doc.project)
    filename, content_type = _check_file(raw, filename)
    latest = frappe.db.get_value("PM Document Version", {"document": doc.name, "version_no": doc.current_version},
                                 "sha256")
    if latest and latest == hashlib.sha256(raw).hexdigest():
        frappe.throw(_("Tệp giống hệt bản {0}").format(doc.current_version))
    number = cint(doc.current_version) + 1
    key = object_storage.put(raw, filename, content_type, "documents")
    _add_version(doc.name, doc.project, doc.task, number, raw, key, filename, content_type, note)
    frappe.db.set_value("PM Document", doc.name, {"current_version": number, "status": DRAFT, "file_name": filename,
                                                  "content_type": content_type, "size_bytes": len(raw),
                                                  "updated_on": now_datetime()})
    _log(doc.project, doc.task, _("Tải lên bản {0} của tài liệu {1}").format(number, doc.title), doc.name)
    _index(doc.name)
    return detail(doc.name)


def _lock(name: str):
    _load(name)  # the permission check
    frappe.db.sql("select name from `tabPM Document` where name = %s for update", name)
    return frappe._dict(frappe.db.get_value("PM Document", name, LIST_FIELDS, as_dict=True))


def may_approve(project: str) -> bool:
    return has_project_capability(project, "task.approve")


def approve(name: str, version_no) -> dict:
    doc = _lock(name)
    if not may_approve(doc.project):
        raise frappe.PermissionError(_("Bạn không có quyền duyệt tài liệu trong dự án này"))
    version = frappe.db.get_value("PM Document Version", {"document": doc.name, "version_no": cint(version_no)},
                                  ["name", "status", "version_no"], as_dict=True)
    if not version:
        frappe.throw(_("Không có bản {0}").format(version_no))
    if version.status != DRAFT:
        frappe.throw(_("Bản {0} không ở trạng thái nháp").format(version.version_no))
    now, user = now_datetime(), frappe.session.user
    if cint(doc.approved_version) and cint(doc.approved_version) > version.version_no:
        frappe.throw(_("Đã có bản mới hơn được duyệt (bản {0})").format(doc.approved_version))
    # what was in force, and older drafts nobody approved, are superseded by this version
    frappe.db.sql("""update `tabPM Document Version` set status = %s
                     where document = %s and (status = %s or (status = %s and version_no < %s))""",
                  (REPLACED, doc.name, APPROVED, DRAFT, version.version_no))
    frappe.db.set_value("PM Document Version", version.name, {"status": APPROVED, "approved_by": user,
                                                              "approved_on": now}, update_modified=False)
    frappe.db.set_value("PM Document", doc.name, {
        "approved_version": version.version_no,
        "status": APPROVED if version.version_no == cint(doc.current_version) else DRAFT, "updated_on": now})
    _log(doc.project, doc.task, _("Duyệt bản {0} của tài liệu {1}").format(version.version_no, doc.title), doc.name)
    _index(doc.name)
    return detail(doc.name)


def _log(project, task, text, name) -> None:
    activity.record("Task" if task else "Project", task or project, "Tệp", text, data={"document": name},
                    project=project, task=task)


def _index(name) -> None:
    from project_manager.project_manager.services import search_index

    search_index.enqueue_document(name)


# --- reading ----------------------------------------------------------------------------------------------------------

def listing(project: str, category: str | None = None, task: str | None = None, search: str = "", start=0,
            limit=50) -> dict:
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))
    filters = {"project": project}
    if category:
        filters["category"] = category
    if task:
        filters["task"] = task
    or_filters = None
    search = (search or "").strip()
    if search:
        or_filters = {"title": ["like", f"%{search}%"], "file_name": ["like", f"%{search}%"]}
    limit = max(1, min(cint(limit) or 50, 200))
    rows = frappe.get_list("PM Document", filters=filters, or_filters=or_filters, fields=LIST_FIELDS,
                           order_by="updated_on desc", start=cint(start), limit_page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    _decorate(rows)
    return {"documents": rows, "more": more, "categories": categories(),
            "can": {"upload": project_in(get_access().write, project), "approve": may_approve(project)}}


def _decorate(rows) -> None:
    tasks = {row.task for row in rows if row.task}
    labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip()
              for t in frappe.get_all("Task", filters={"name": ["in", list(tasks)]},
                                      fields=["name", "subject", "pm_wbs_code"])} if tasks else {}
    for row in rows:
        row["task_label"] = labels.get(row.task)


def detail(name: str) -> dict:
    doc = _load(name)
    versions = frappe.get_all("PM Document Version", filters={"document": doc.name},
                              fields=[f for f in VERSION_FIELDS if f != "object_key"], order_by="version_no desc")
    users = {v.uploaded_by for v in versions} | {v.approved_by for v in versions if v.approved_by}
    names = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
                                as_list=True)) if users else {}
    for version in versions:
        version["uploaded_by_name"] = names.get(version.uploaded_by) or version.uploaded_by
        version["approved_by_name"] = names.get(version.approved_by) or version.approved_by
    _decorate([doc])
    doc["project_name"] = frappe.db.get_value("Project", doc.project, "project_name")
    doc["versions"] = versions
    doc["can"] = {"upload": project_in(get_access().write, doc.project), "approve": may_approve(doc.project)}
    return doc


def download(name: str, version_no=None, inline: int = 0):
    """The file of one version (the newest when not given), streamed after the permission check."""
    from project_manager.project_manager.services.files import stream

    doc = _load(name)
    number = cint(version_no) or cint(doc.current_version)
    version = frappe.db.get_value("PM Document Version", {"document": doc.name, "version_no": number},
                                  ["object_key", "content_type", "file_name"], as_dict=True)
    if not version:
        raise frappe.DoesNotExistError(_("Không có bản {0}").format(number))
    return stream(version.object_key, "documents", version.content_type, version.file_name, inline=bool(cint(inline)),
                  immutable=True)
