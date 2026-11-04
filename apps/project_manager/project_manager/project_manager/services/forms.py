"""Biểu mẫu đã điền: a form filled in for a project or a task. Nháp → Đã nộp → Đã duyệt (or Trả lại, then again).

The states live here rather than in a Frappe Workflow because who may approve depends on the person's role in *that*
project (task.approve) or on being the task's reviewer, which a Workflow's global roles cannot express.

* Who fills in: whoever may update work in the project and sees the task (`task.update` and the like).
* Who approves: `task.approve` in the project, or the task's reviewer; never the person who submitted it (administrators
  excepted), so that an acceptance form always has a second pair of eyes.
* A form keeps the exact template version it was started on. Values are checked against that version here, on every
  save; required fields only when submitting. Files in the answers must be attached to this very form: a form cannot
  point at somebody else's private file (it would end up in the PDF).
* Approved forms never change. The PDF is made once, when approved, and kept with its checksum (form_output.py).
"""

import base64
import json
import math
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import can_see_task, has_project_capability, is_admin
from project_manager.project_manager.services import activity, form_templates, gates, rollup
from project_manager.project_manager.services.notify import notify_user

SPA_FORM = "/pm/bieu-mau/{}"
FILL_CAPABILITIES = ("task.update", "plan.edit", "task.assign", "task.approve")
TEXT_LIMITS = {C.F_TEXT: 500, C.F_LONG: 10000}
MAX_TABLE_ROWS = 200
MAX_IMAGES = 20
MAX_ATTACHMENTS = 100
MAX_FILE_BYTES = 10 * 1024 * 1024
# What an uploaded picture really is, from its first bytes (never from its name)
IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"RIFF", "webp"))
LIST_FIELDS = ["name", "title", "template_code", "version", "state", "project", "task", "owner", "submitted_by",
               "submitted_on", "reviewed_by", "reviewed_on", "modified"]


# --- values -------------------------------------------------------------------------------------------------------------

def _number(value):
    number = float(str(value).strip().replace(",", "."))
    if math.isnan(number) or math.isinf(number):
        raise ValueError
    return int(number) if number.is_integer() and abs(number) < 1e15 else number


def _date(value) -> str:
    return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")


def _empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _cell(column: dict, value):
    """A clean table cell, or ValueError."""
    if _empty(value):
        return None
    kind = column["type"]
    if kind == C.F_NUMBER:
        return _number(value)
    if kind == C.F_DATE:
        return _date(value)
    if kind == C.F_CHECK:
        return 1 if value in (1, True, "1", "true") else 0
    if kind == C.F_SELECT and str(value) not in column["choices"]:
        raise ValueError
    return str(value).strip()[:500]


def _table(field: dict, value, errors: list, strict: bool):
    columns = field["columns"]
    preset = field["preset_rows"]
    rows = value if isinstance(value, list) else []
    if preset:  # a checklist: its rows and first column are the template's
        rows = [(rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}) for i in range(len(preset))]
    elif len(rows) > MAX_TABLE_ROWS:
        errors.append(_("{0}: tối đa {1} hàng").format(field["label"], MAX_TABLE_ROWS))
        rows = rows[:MAX_TABLE_ROWS]
    out = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            errors.append(_("{0}: hàng {1} không hợp lệ").format(field["label"], index + 1))
            continue
        row = {}
        for position, column in enumerate(columns):
            if preset and position == 0:
                row[column["key"]] = preset[index]
                continue
            try:
                cell = _cell(column, raw.get(column["key"]))
            except (ValueError, TypeError):
                errors.append(_("{0}: hàng {1}, cột {2} không hợp lệ").format(field["label"], index + 1, column["label"]))
                continue
            if cell is not None:
                row[column["key"]] = cell
        filled = [k for k in row if not (preset and k == columns[0]["key"])]
        if filled or preset:
            out.append(row)
        if preset and strict and field["reqd"] and not filled:
            errors.append(_("{0}: chưa điền hàng \"{1}\"").format(field["label"], preset[index]))
    if strict and field["reqd"] and not out:
        errors.append(_("{0}: chưa có hàng nào").format(field["label"]))
    return out


def _files(field: dict, value, errors: list, allowed: set):
    items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    if field["fieldtype"] == C.F_SIGNATURE:
        items = items[:1]
    elif len(items) > MAX_IMAGES:
        errors.append(_("{0}: tối đa {1} ảnh").format(field["label"], MAX_IMAGES))
        items = items[:MAX_IMAGES]
    out = []
    for item in items:
        url = item.get("file") if isinstance(item, dict) else None
        if url not in allowed:
            errors.append(_("{0}: tệp không thuộc biểu mẫu này").format(field["label"]))
            continue
        out.append({"file": url, "name": str(item.get("name") or "")[:140]})
    return out


def clean_data(spec, raw, allowed_files=(), strict: bool = False) -> tuple[dict, list]:
    """(clean answers, problems). Answers to fields the template does not have are dropped."""
    raw = raw if isinstance(raw, dict) else {}
    allowed = set(allowed_files)
    data, errors = {}, []
    for field in spec["fields"]:
        kind, key, label = field["fieldtype"], field["fieldname"], field["label"]
        if kind == C.F_SECTION:
            continue
        value = raw.get(key)
        if kind == C.F_TABLE:
            clean = _table(field, value, errors, strict)
        elif kind in (C.F_IMAGE, C.F_SIGNATURE):
            clean = _files(field, value, errors, allowed)
        elif kind == C.F_CHECK:
            clean = 1 if value in (1, True, "1", "true") else 0
        elif _empty(value):
            clean = None
        else:
            try:
                if kind == C.F_NUMBER:
                    clean = _number(value)
                    low, high = field["min_value"], field["max_value"]
                    if form_templates.bound(low) is not None and clean < form_templates.bound(low):
                        errors.append(_("{0}: không được nhỏ hơn {1}").format(label, low))
                    if form_templates.bound(high) is not None and clean > form_templates.bound(high):
                        errors.append(_("{0}: không được lớn hơn {1}").format(label, high))
                elif kind == C.F_DATE:
                    clean = _date(value)
                elif kind == C.F_SELECT:
                    clean = str(value)
                    if clean not in field["choices"]:
                        errors.append(_("{0}: \"{1}\" không có trong danh sách").format(label, clean))
                else:
                    clean = str(value).strip()
                    if len(clean) > TEXT_LIMITS[kind]:
                        errors.append(_("{0}: dài quá {1} ký tự").format(label, TEXT_LIMITS[kind]))
            except (ValueError, TypeError):
                errors.append(_("{0}: giá trị không hợp lệ").format(label))
                clean = None
        if strict and field["reqd"] and kind != C.F_TABLE and (_empty(clean) or (kind == C.F_CHECK and not clean)):
            errors.append(_("{0}: chưa điền").format(label))
        if not _empty(clean):
            data[key] = clean
    return data, errors


def _throw_if(errors: list) -> None:
    if errors:
        frappe.throw("\n".join(errors), title=_("Biểu mẫu chưa hợp lệ"))


# --- who may ------------------------------------------------------------------------------------------------------------

def may_fill(project: str, task: str | None, user: str | None = None) -> bool:
    if not has_project_capability(project, *FILL_CAPABILITIES, user=user):
        return False
    return not task or can_see_task(task, project, user)


def may_approve(doc, user: str | None = None) -> bool:
    """May this person decide on this form? (Whether they also submitted it is checked separately, with a message.)"""
    user = user or frappe.session.user
    if has_project_capability(doc.project, "task.approve", user=user):
        return True
    return bool(doc.task) and frappe.db.get_value("Task", doc.task, "pm_reviewer") == user


def _may_edit(doc, user: str | None = None) -> bool:
    user = user or frappe.session.user
    return doc.state in C.SUB_EDITABLE and (doc.owner == user or is_admin(user) or may_approve(doc, user))


def _load(name) -> "frappe.model.document.Document":
    doc = frappe.get_doc("PM Form Submission", cint(name))
    doc.check_permission("read")
    return doc


def _lock(name):
    """The form, with its row locked: two people deciding at the same moment take turns."""
    frappe.db.sql("select name from `tabPM Form Submission` where name = %s for update", cint(name))
    return _load(name)


def _attached(name) -> list[str]:
    return frappe.get_all("File", filters={"attached_to_doctype": "PM Form Submission", "attached_to_name": str(name)},
                          pluck="file_url")


def _log(doc, text: str, **data) -> None:
    activity.record("PM Form Submission", str(doc.name), "Biểu mẫu", text, project=doc.project, task=doc.task or None,
                    data={"submission": doc.name, "state": doc.state, **data})


def _full_name(user) -> str | None:
    return frappe.utils.get_fullname(user) if user else None


# --- the workflow -------------------------------------------------------------------------------------------------------

def start(template_code: str, project: str, task: str | None = None, client_uuid: str | None = None) -> dict:
    """Open a form to fill in. The caller's unfinished form of the same kind, if any, is opened again."""
    if client_uuid:
        existing = frappe.db.get_value("PM Form Submission", {"client_uuid": client_uuid}, "name")
        if existing:
            return {"name": existing, "resumed": True}
    if task:
        project = frappe.db.get_value("Task", task, "project") or project
    if not project or not frappe.db.exists("Project", project):
        frappe.throw(_("Không tìm thấy dự án"), frappe.DoesNotExistError)
    if not may_fill(project, task):
        frappe.throw(_("Bạn không được điền biểu mẫu cho công việc này"), frappe.PermissionError)
    template = form_templates.active_version(template_code)
    if not template:
        frappe.throw(_("Mẫu {0} không có phiên bản đang dùng").format(template_code))
    filters = {"template_code": template_code, "project": project, "task": task or ("is", "not set"),
               "owner": frappe.session.user, "state": ["in", C.SUB_EDITABLE]}
    open_form = frappe.db.get_value("PM Form Submission", filters, "name")
    if open_form:
        return {"name": open_form, "resumed": True}
    spec = form_templates.spec(template)
    doc = frappe.get_doc({"doctype": "PM Form Submission", "template": template, "template_code": template_code,
                          "title": spec["title"], "version": spec["version"], "project": project, "task": task or None,
                          "state": C.SUB_DRAFT, "data": "{}", "client_uuid": client_uuid or None})
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "resumed": False}


def save(name, data) -> dict:
    """Keep the answers of a form being filled in (required fields are only checked when submitting)."""
    doc = _lock(name)
    if not _may_edit(doc):
        frappe.throw(_("Biểu mẫu này không sửa được"), frappe.PermissionError)
    clean, errors = clean_data(form_templates.spec(doc.template), data, _attached(doc.name))
    _throw_if(errors)
    frappe.db.set_value("PM Form Submission", doc.name, "data", json.dumps(clean, ensure_ascii=False))
    return detail(doc.name)


def submit(name, data=None) -> dict:
    doc = _lock(name)
    if not _may_edit(doc):
        frappe.throw(_("Biểu mẫu này không nộp được"), frappe.PermissionError)
    answers = data if data is not None else json.loads(doc.data or "{}")
    clean, errors = clean_data(form_templates.spec(doc.template), answers, _attached(doc.name), strict=True)
    _throw_if(errors)
    user = frappe.session.user
    frappe.db.set_value("PM Form Submission", doc.name, {
        "data": json.dumps(clean, ensure_ascii=False), "state": C.SUB_SUBMITTED, "submitted_by": user,
        "submitted_on": now_datetime(), "review_note": None})
    doc.state = C.SUB_SUBMITTED
    _log(doc, _("Nộp biểu mẫu {0}").format(doc.title))
    for person in _approvers(doc) - {user}:
        notify_user(person, _("{0} chờ bạn duyệt: {1}").format(doc.title, _full_name(user)), SPA_FORM.format(doc.name),
                    "PM Form Submission", str(doc.name))
    return detail(doc.name)


def _approvers(doc) -> set:
    reviewer = frappe.db.get_value("Task", doc.task, "pm_reviewer") if doc.task else None
    if reviewer:
        return {reviewer}
    manager = frappe.db.get_value("Project", doc.project, "pm_manager")
    return {manager} if manager else set()


def _assert_decider(doc) -> None:
    if doc.state != C.SUB_SUBMITTED:
        frappe.throw(_("Biểu mẫu không ở trạng thái chờ duyệt (đang là {0})").format(doc.state))
    if not may_approve(doc):
        frappe.throw(_("Bạn không được duyệt biểu mẫu này"), frappe.PermissionError)


def approve(name, note: str = "") -> dict:
    doc = _lock(name)
    _assert_decider(doc)
    user = frappe.session.user
    if doc.submitted_by == user and not is_admin(user):
        frappe.throw(_("Người nộp không tự duyệt biểu mẫu của mình: cần một người khác trong dự án"),
                     frappe.PermissionError)
    frappe.db.set_value("PM Form Submission", doc.name, {
        "state": C.SUB_APPROVED, "reviewed_by": user, "reviewed_on": now_datetime(), "review_note": (note or "").strip() or None})
    doc.state = C.SUB_APPROVED
    _log(doc, _("Duyệt biểu mẫu {0}").format(doc.title) + (f": {note.strip()}" if (note or "").strip() else ""))
    if doc.submitted_by and doc.submitted_by != user:
        notify_user(doc.submitted_by, _("Đã duyệt: {0}").format(doc.title), SPA_FORM.format(doc.name),
                    "PM Form Submission", str(doc.name))
    if doc.task and frappe.db.get_value("Task", doc.task, "is_group"):
        rollup.schedule(doc.project, {doc.task})  # a finished group may have been waiting only for this form
    frappe.enqueue("project_manager.project_manager.services.form_output.make_pdf_job", queue="default",
                   submission=doc.name, enqueue_after_commit=True, job_id=f"pm-form-pdf:{doc.name}", deduplicate=True)
    return detail(doc.name)


def send_back(name, note: str) -> dict:
    doc = _lock(name)
    _assert_decider(doc)
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Hãy ghi lý do trả lại"))
    user = frappe.session.user
    frappe.db.set_value("PM Form Submission", doc.name, {
        "state": C.SUB_RETURNED, "reviewed_by": user, "reviewed_on": now_datetime(), "review_note": note})
    doc.state = C.SUB_RETURNED
    _log(doc, _("Trả lại biểu mẫu {0}: {1}").format(doc.title, note))
    if doc.submitted_by and doc.submitted_by != user:
        notify_user(doc.submitted_by, _("Trả lại: {0}: {1}").format(doc.title, note), SPA_FORM.format(doc.name),
                    "PM Form Submission", str(doc.name))
    return detail(doc.name)


def discard(name) -> dict:
    """Throw away a form that was never submitted (with the files it holds)."""
    doc = _lock(name)
    if doc.state != C.SUB_DRAFT or doc.submitted_on or not _may_edit(doc):
        frappe.throw(_("Chỉ bỏ được bản nháp chưa từng nộp"), frappe.PermissionError)
    frappe.delete_doc("PM Form Submission", doc.name, ignore_permissions=True)
    return {"name": doc.name, "deleted": True}


def attach(name, content: str, filename: str = "") -> dict:
    """Keep a photo or signature (base64) privately with this form. Returns what goes into the answers."""
    doc = _lock(name)
    if not _may_edit(doc):
        frappe.throw(_("Biểu mẫu này không sửa được"), frappe.PermissionError)
    if len(_attached(doc.name)) >= MAX_ATTACHMENTS:
        frappe.throw(_("Biểu mẫu đã có quá nhiều tệp"))
    if "," in (content or "")[:100] and content.startswith("data:"):
        content = content.split(",", 1)[1]
    try:
        raw = base64.b64decode(content or "", validate=True)
    except Exception:
        frappe.throw(_("Tệp không hợp lệ"))
    if not raw or len(raw) > MAX_FILE_BYTES:
        frappe.throw(_("Ảnh phải nhỏ hơn 10 MB"))
    extension = next((ext for magic, ext in IMAGE_MAGIC if raw.startswith(magic)), None)
    if extension == "webp" and raw[8:12] != b"WEBP":
        extension = None
    if not extension:
        frappe.throw(_("Chỉ nhận ảnh PNG, JPEG hoặc WebP"))
    token = frappe.generate_hash(length=10)
    file = frappe.get_doc({"doctype": "File", "file_name": f"bm-{doc.name}-{token}.{extension}", "content": raw,
                           "is_private": 1, "attached_to_doctype": "PM Form Submission",
                           "attached_to_name": str(doc.name)})
    file.insert(ignore_permissions=True)
    return {"file": file.file_url, "name": (filename or "")[:140]}


# --- reading ------------------------------------------------------------------------------------------------------------

def detail(name) -> dict:
    doc = _load(name)
    user = frappe.session.user
    decider = doc.state == C.SUB_SUBMITTED and may_approve(doc)
    task = frappe.db.get_value("Task", doc.task, ["subject", "pm_wbs_code"], as_dict=True) if doc.task else None
    history = frappe.get_all("PM Activity", filters={"reference_doctype": "PM Form Submission",
                                                     "reference_name": str(doc.name), "is_deleted": 0},
                             fields=["name", "actor", "content", "creation"], order_by="name desc", limit_page_length=30)
    for row in history:
        row["actor_name"] = _full_name(row.actor) or row.actor
    return {
        "name": doc.name, "state": doc.state, "title": doc.title, "template": doc.template,
        "template_code": doc.template_code, "version": doc.version, "project": doc.project,
        "project_name": frappe.db.get_value("Project", doc.project, "project_name"), "task": doc.task,
        "task_label": f"{task.pm_wbs_code or ''} {task.subject}".strip() if task else None,
        "data": json.loads(doc.data or "{}"), "spec": form_templates.spec(doc.template),
        "owner": doc.owner, "owner_name": _full_name(doc.owner),
        "submitted_by": doc.submitted_by, "submitted_by_name": _full_name(doc.submitted_by),
        "submitted_on": doc.submitted_on, "reviewed_by": doc.reviewed_by, "reviewed_by_name": _full_name(doc.reviewed_by),
        "reviewed_on": doc.reviewed_on, "review_note": doc.review_note, "has_pdf": bool(doc.pdf_file),
        "history": history,
        "can": {"edit": _may_edit(doc), "approve": decider and (doc.submitted_by != user or is_admin(user)),
                "send_back": decider, "discard": doc.state == C.SUB_DRAFT and not doc.submitted_on and _may_edit(doc),
                "self_submitted": doc.submitted_by == user},
    }


def _names(rows) -> None:
    people = {r.submitted_by for r in rows if r.submitted_by} | {r.owner for r in rows}
    full = dict(frappe.get_all("User", filters={"name": ["in", list(people)]}, fields=["name", "full_name"],
                               as_list=True)) if people else {}
    tasks = {r.task for r in rows if r.task}
    labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", list(tasks)]}, fields=["name", "subject", "pm_wbs_code"])} if tasks else {}
    for row in rows:
        row["who"] = full.get(row.submitted_by or row.owner) or row.submitted_by or row.owner
        row["task_label"] = labels.get(row.task)


def list_forms(project: str | None = None, task: str | None = None, state: str | None = None,
               template_code: str | None = None, start: int = 0, limit: int = 50) -> dict:
    """Forms in the caller's scope, newest first. A draft belongs to its author: it shows only to them."""
    filters = [["PM Form Submission", "state", "!=", C.SUB_DRAFT]]
    if state == C.SUB_DRAFT:
        filters = [["PM Form Submission", "state", "=", C.SUB_DRAFT],
                   ["PM Form Submission", "owner", "=", frappe.session.user]]
    elif state:
        filters.append(["PM Form Submission", "state", "=", state])
    for field, value in (("project", project), ("task", task), ("template_code", template_code)):
        if value:
            filters.append(["PM Form Submission", field, "=", value])
    limit = max(1, min(cint(limit) or 50, 200))
    rows = frappe.get_list("PM Form Submission", filters=filters, fields=LIST_FIELDS, order_by="name desc",
                           start=max(0, cint(start)), page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    _names(rows)
    return {"rows": rows, "more": more}


def waiting_for_me(limit: int = 20) -> dict:
    """Forms the caller could approve now (their own excepted), oldest first."""
    user = frappe.session.user
    candidates = frappe.get_list("PM Form Submission", filters=[["PM Form Submission", "state", "=", C.SUB_SUBMITTED]],
                                 fields=LIST_FIELDS, order_by="submitted_on asc", limit_page_length=300)
    tasks = {row.task for row in candidates if row.task}
    reviewing = set(frappe.get_all("Task", filters={"name": ["in", list(tasks)], "pm_reviewer": user}, pluck="name")) if tasks else set()
    rights = {project: has_project_capability(project, "task.approve", user=user) for project in {row.project for row in candidates}}
    rows = [row for row in candidates if row.submitted_by != user and (rights[row.project] or row.task in reviewing)]
    total = len(rows)
    rows = rows[:max(1, min(cint(limit) or 20, 100))]
    _names(rows)
    return {"rows": rows, "total": total}


def for_task(task: str) -> dict:
    """What the task panel shows: the forms this task requires, the ones filled in, what the caller may do."""
    info = frappe.get_doc("Task", task)
    info.check_permission("read")
    rows = list_forms(task=task, limit=50)["rows"]
    drafts = list_forms(task=task, state=C.SUB_DRAFT, limit=10)["rows"]
    return {
        "gates": gates.of_task(task), "forms": drafts + rows,
        "can_fill": may_fill(info.project, task), "can_gate": has_project_capability(info.project, "plan.edit"),
        "templates": form_templates.in_use(),
    }
