"""Site diary (nhật ký thi công): one per project and day, written on site, confirmed by the site commander.

* Whoever may update progress in the project writes the diary of a day: weather, people on site, what was done,
  problems, safety, the quantity done on each work item, photos. It can be written offline: its name
  ({project}-ND-{date}) is known in advance and every write carries a client_uuid (the phone's outbox).
* Submitting it (Nháp → Đã nộp) counts its quantities: each work item's done quantity and progress move
  (services/quantities.py). The commander (project role with "task.approve") confirms it (Đã xác nhận, locked) or
  sends it back with a reason (back to Nháp: its quantities stop counting until it is submitted again).
* Photos are PM Media of the diary (the core's discussion: hooks.pm_discussion_targets).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate
from project_manager.project_manager.policy import (
    assert_project_capability,
    get_access,
    has_project_capability,
    project_in,
)
from project_manager.project_manager.services import activity, timeline
from project_manager.project_manager.services.notify import notify_user

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import quantities

WRITE_CAPABILITIES = ("task.update", "plan.edit")
FIELDS = ["name", "project", "diary_date", "status", "weather", "temperature", "workers", "work_summary", "issues",
          "safety", "author", "submitted_on", "confirmed_by", "confirmed_on", "return_note", "client_uuid", "modified"]
SPA_DIARY = "/pm/du-an/{0}/nhat-ky?ngay={1}"


def name_of(project: str, day) -> str:
    return f"{project}-ND-{getdate(day)}"


def target(name: str, user: str | None = None):
    """hooks.pm_discussion_targets: (project, task) of a diary the user may read."""
    project = frappe.db.get_value("PMC Site Diary", name, "project")
    if not project or not project_in(get_access(user).read, project):
        raise frappe.PermissionError(_("Bạn không xem được nhật ký này"))
    return project, None


def _may_write(project: str) -> bool:
    return has_project_capability(project, *WRITE_CAPABILITIES)


def _may_confirm(project: str) -> bool:
    return has_project_capability(project, "task.approve")


def _lock(name: str):
    row = frappe.db.sql(f"select {', '.join(FIELDS)} from `tabPMC Site Diary` where name = %s for update", name,
                        as_dict=True)
    if not row:
        raise frappe.DoesNotExistError(_("Không tìm thấy nhật ký"))
    return row[0]


# --- writing ------------------------------------------------------------------------------------------------------------

def save(project: str, day, values: dict | None = None, rows=None, client_uuid: str | None = None) -> dict:
    """Create or update the draft of a day. `rows`: [{task, qty, note}] replaces the diary's quantities."""
    if not _may_write(project):
        raise frappe.PermissionError(_("Vai trò của bạn trong dự án không được ghi nhật ký"))
    day = getdate(day or nowdate())
    if day > getdate(nowdate()):
        frappe.throw(_("Không ghi nhật ký cho ngày chưa tới"))
    values = _values(values)
    rows = _rows(project, rows)
    name = name_of(project, day)
    frappe.db.sql("select name from `tabProject` where name = %s for update", project)
    if frappe.db.exists("PMC Site Diary", name):
        doc = _lock(name)
        if client_uuid and doc.client_uuid == client_uuid and doc.status != K.DIARY_DRAFT:
            return detail(name)  # the same send arriving again after it was submitted
        if doc.status != K.DIARY_DRAFT:
            frappe.throw(_("Nhật ký ngày {0} đã nộp: không sửa được nữa").format(day.strftime("%d/%m/%Y")))
        frappe.db.set_value("PMC Site Diary", name, {**values, "client_uuid": client_uuid or doc.client_uuid})
    else:
        frappe.get_doc({"doctype": "PMC Site Diary", "project": project, "diary_date": day, "status": K.DIARY_DRAFT,
                        "author": frappe.session.user, "client_uuid": client_uuid or None, **values}).insert(
            ignore_permissions=True)
    if rows is not None:
        frappe.db.delete("PMC Diary Quantity", {"diary": name})
        for row in rows:
            frappe.get_doc({"doctype": "PMC Diary Quantity", "diary": name, "project": project, "task": row["task"],
                            "entry_date": day, "qty": row["qty"], "uom": row["uom"], "note": row["note"]}).insert(
                ignore_permissions=True)
    return detail(name)


def _values(values) -> dict:
    if isinstance(values, str):
        values = json.loads(values or "{}")
    values = values or {}
    out = {}
    weather = (values.get("weather") or "").strip()
    if weather and weather not in K.WEATHER:
        frappe.throw(_("Thời tiết không hợp lệ: {0}").format(weather))
    out["weather"] = weather or None
    out["temperature"] = (str(values.get("temperature") or "").strip()[:40]) or None
    out["workers"] = max(0, cint(values.get("workers")))
    for field, limit in (("work_summary", 5000), ("issues", 5000), ("safety", 2000)):
        out[field] = (values.get(field) or "").strip()[:limit] or None
    return out


def _rows(project: str, rows):
    if rows is None:
        return None
    if isinstance(rows, str):
        rows = json.loads(rows or "[]")
    tasks = {r.name: r for r in frappe.get_all(
        "Task", filters={"project": project, "name": ["in", [r.get("task") for r in rows if r.get("task")] or [""]]},
        fields=["name", "is_group", "pmc_uom", "subject", "status"])}
    out, seen = [], set()
    for row in rows:
        task = tasks.get(row.get("task"))
        if not task:
            frappe.throw(_("Công tác không thuộc dự án này"))
        if task.is_group:
            frappe.throw(_("Chỉ ghi khối lượng cho công tác, không cho hạng mục: {0}").format(task.subject))
        if task.name in seen:
            frappe.throw(_("Công tác {0} được ghi hai lần trong cùng một ngày").format(task.subject))
        qty = flt(row.get("qty"), 6)
        if qty <= 0:
            frappe.throw(_("Khối lượng của {0} phải lớn hơn 0").format(task.subject))
        seen.add(task.name)
        out.append({"task": task.name, "qty": qty, "uom": task.pmc_uom, "note": (row.get("note") or "").strip()[:500] or None})
    return out


def submit(name: str, media=None, client_uuid: str | None = None) -> dict:
    """Nháp → Đã nộp: the quantities count. Photos sent for the diary (`media`: their client_uuids) go with a comment."""
    doc = _lock(name)
    if not _may_write(doc.project):
        raise frappe.PermissionError(_("Vai trò của bạn trong dự án không được ghi nhật ký"))
    if doc.status != K.DIARY_DRAFT:
        return detail(name)  # already submitted (a resent request)
    count = frappe.db.count("PMC Diary Quantity", {"diary": name})
    if not count and not (doc.work_summary or "").strip():
        frappe.throw(_("Nhật ký trống: ghi công việc đã làm hoặc khối lượng"))
    frappe.db.set_value("PMC Site Diary", name, {"status": K.DIARY_SUBMITTED, "submitted_on": now_datetime(),
                                                 "return_note": None})
    day = getdate(doc.diary_date).strftime("%d/%m/%Y")
    tasks = frappe.get_all("PMC Diary Quantity", filters={"diary": name}, pluck="task")
    quantities.refresh(tasks, _("Theo nhật ký thi công ngày {0}").format(day))
    activity.record("PMC Site Diary", name, "Tiến độ", _("Nộp nhật ký thi công ngày {0}: {1} công tác").format(day, count),
                    project=doc.project)
    photos = [m for m in (json.loads(media) if isinstance(media, str) else media or []) if m]
    if photos:
        timeline.post("PMC Site Diary", name, _("Ảnh nhật ký ngày {0}").format(day), photos,
                      f"{client_uuid}:photos" if client_uuid else None)
    manager = frappe.db.get_value("Project", doc.project, "pm_manager")
    if manager and manager != frappe.session.user:
        notify_user(manager, _("Nhật ký thi công ngày {0} chờ xác nhận").format(day),
                    SPA_DIARY.format(doc.project, getdate(doc.diary_date)), "PMC Site Diary", name)
    return detail(name)


def record(project: str, day, values=None, rows=None, client_uuid: str | None = None, media=None) -> dict:
    """Save and submit in one call (the outbox of a phone): sending it again changes nothing."""
    saved = save(project, day, values, rows, client_uuid)
    return submit(saved["name"], media, client_uuid)


def confirm(name: str, note: str = "") -> dict:
    doc = _lock(name)
    if not _may_confirm(doc.project):
        raise frappe.PermissionError(_("Chỉ người có quyền duyệt trong dự án mới xác nhận nhật ký"))
    if doc.status != K.DIARY_SUBMITTED:
        frappe.throw(_("Chỉ xác nhận được nhật ký đã nộp"))
    frappe.db.set_value("PMC Site Diary", name, {"status": K.DIARY_CONFIRMED, "confirmed_by": frappe.session.user,
                                                 "confirmed_on": now_datetime()})
    day = getdate(doc.diary_date).strftime("%d/%m/%Y")
    activity.record("PMC Site Diary", name, "Trạng thái",
                    _("Xác nhận nhật ký ngày {0}").format(day) + (f": {note.strip()}" if (note or "").strip() else ""),
                    project=doc.project)
    return detail(name)


def send_back(name: str, note: str) -> dict:
    doc = _lock(name)
    if not _may_confirm(doc.project):
        raise frappe.PermissionError(_("Chỉ người có quyền duyệt trong dự án mới trả lại nhật ký"))
    if doc.status != K.DIARY_SUBMITTED:
        frappe.throw(_("Chỉ trả lại được nhật ký đã nộp, chưa xác nhận"))
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Hãy ghi lý do trả lại"))
    frappe.db.set_value("PMC Site Diary", name, {"status": K.DIARY_DRAFT, "return_note": note[:1000]})
    day = getdate(doc.diary_date).strftime("%d/%m/%Y")
    tasks = frappe.get_all("PMC Diary Quantity", filters={"diary": name}, pluck="task")
    quantities.refresh(tasks, _("Nhật ký ngày {0} bị trả lại").format(day))
    activity.record("PMC Site Diary", name, "Trạng thái", _("Trả lại nhật ký ngày {0}: {1}").format(day, note),
                    project=doc.project)
    if doc.author and doc.author != frappe.session.user:
        notify_user(doc.author, _("Nhật ký ngày {0} bị trả lại: {1}").format(day, note),
                    SPA_DIARY.format(doc.project, getdate(doc.diary_date)), "PMC Site Diary", name)
    return detail(name)


# --- reading ------------------------------------------------------------------------------------------------------------

def listing(project: str, start=0, limit=31) -> dict:
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))
    limit = max(1, min(cint(limit) or 31, 120))
    rows = frappe.get_list("PMC Site Diary", filters={"project": project}, fields=FIELDS, order_by="diary_date desc",
                           start=cint(start), limit_page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    names = [r.name for r in rows]
    counts = dict(frappe.db.sql("""select diary, count(*) from `tabPMC Diary Quantity` where diary in %s
                                   group by diary""", (tuple(names),))) if names else {}
    photos = dict(frappe.db.sql("""select reference_name, count(*) from `tabPM Media`
                                   where reference_doctype = 'PMC Site Diary' and reference_name in %s and is_deleted = 0
                                   group by reference_name""", (tuple(names),))) if names else {}
    authors = _names({r.author for r in rows})
    for row in rows:
        row["quantities"] = cint(counts.get(row.name))
        row["photos"] = cint(photos.get(row.name))
        row["author_name"] = authors.get(row.author) or row.author
    return {"diaries": rows, "more": more, "today": name_of(project, nowdate()),
            "can": {"write": _may_write(project), "confirm": _may_confirm(project)}, "weather": list(K.WEATHER)}


def _names(users) -> dict:
    users = [u for u in users if u]
    return dict(frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"],
                               as_list=True)) if users else {}


def works(project: str, search: str = "") -> list[dict]:
    """Work items one can write a quantity for: planned, done, what is left."""
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))
    filters = {"project": project, "is_group": 0, "status": ["not in", ["Cancelled"]], "pmc_planned_qty": [">", 0]}
    or_filters = None
    if (search or "").strip():
        text = f"%{search.strip()}%"
        or_filters = {"subject": ["like", text], "pm_wbs_code": ["like", text], "pmc_norm_code": ["like", text]}
    rows = frappe.get_list("Task", filters=filters, or_filters=or_filters,
                           fields=["name", "subject", "pm_wbs_code", "pmc_uom", "pmc_planned_qty", "pmc_done_qty",
                                   "pmc_norm_code", "progress"], order_by="pm_path asc", limit_page_length=300)
    for row in rows:
        row["remaining"] = max(0.0, flt(row.pmc_planned_qty) - flt(row.pmc_done_qty))
    return rows


def detail(name: str) -> dict:
    doc = frappe.db.get_value("PMC Site Diary", name, FIELDS, as_dict=True)
    if not doc:
        raise frappe.DoesNotExistError(_("Không tìm thấy nhật ký"))
    target(name)
    rows = frappe.get_all("PMC Diary Quantity", filters={"diary": name},
                          fields=["name", "task", "qty", "uom", "note"], order_by="name asc")
    tasks = {t.name: t for t in frappe.get_all("Task", filters={"name": ["in", [r.task for r in rows] or [""]]},
                                               fields=["name", "subject", "pm_wbs_code", "pmc_planned_qty",
                                                       "pmc_done_qty"])}
    for row in rows:
        task = tasks.get(row.task) or frappe._dict()
        row["label"] = f"{task.pm_wbs_code or ''} {task.subject or ''}".strip()
        row["planned_qty"] = flt(task.pmc_planned_qty)
        row["done_qty"] = flt(task.pmc_done_qty)
    names = _names({doc.author, doc.confirmed_by})
    doc["author_name"] = names.get(doc.author) or doc.author
    doc["confirmed_by_name"] = names.get(doc.confirmed_by) or doc.confirmed_by
    doc["rows"] = rows
    doc["photos"] = [timeline._photo(m) for m in frappe.get_all(
        "PM Media", filters={"reference_doctype": "PMC Site Diary", "reference_name": name, "is_deleted": 0},
        fields=["name", "width", "height", "thumb_key", "taken_at", "lat", "lng"], order_by="name asc")]
    doc["can"] = {"edit": doc.status == K.DIARY_DRAFT and _may_write(doc.project),
                  "confirm": doc.status == K.DIARY_SUBMITTED and _may_confirm(doc.project)}
    return doc


def get_day(project: str, day=None) -> dict:
    """The diary of a day, or an empty one to fill (not stored until saved)."""
    day = getdate(day or nowdate())
    name = name_of(project, day)
    if frappe.db.exists("PMC Site Diary", name):
        return detail(name)
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))
    assert_project_capability(project, *WRITE_CAPABILITIES)
    return {"name": name, "project": project, "diary_date": day, "status": None, "rows": [], "photos": [],
            "can": {"edit": True, "confirm": False}, "is_new": True}
