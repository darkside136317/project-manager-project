"""The discussion of a task or of a project: comments with @mentions and photos, read next to the task's history.

Everything is a PM Activity row (services/activity.py writes them): a comment is the type "Bình luận", the rest
(progress, assignments, date changes, forms...) is written by the services that make those changes. This module reads
them page by page (keyset on the id, newest first), adds comments, and keeps who follows what (PM Follow):

* whoever comments, is mentioned or is given the task follows it; anyone may stop or start following;
* followers are notified of a new comment, mentioned people get their own notice;
* a comment is sent once even when a phone resends it (client_uuid), and its photos are uploaded before it
  (services/media.py) and linked to it here.

Who may read may comment: a project member who sees the task (or the project, for the project's own discussion).
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint

from project_manager.project_manager.policy import can_see_task, get_access, is_admin, project_in
from project_manager.project_manager.services import activity
from project_manager.project_manager.services.notify import notify_user

COMMENT = "Bình luận"
MAX_TEXT = 5000
PAGE = 30
MAX_PAGE = 100
MAX_MEDIA = 12
SPA_TASK = "/pm/cong-viec/{}"
SPA_PROJECT = "/pm/du-an/{}/trao-doi"
# @[Full name](user@example.com): what the composer inserts; shown as a name, notified by the address.
MENTION = re.compile(r"@\[([^\]\n]{1,140})\]\(([^)\s]{3,140})\)")
KINDS = {
    "comment": ("Bình luận",),
    "progress": ("Tiến độ",),
    "change": ("Thay đổi", "Giao việc", "Đổi hạn", "Trạng thái", "Tệp", "Biểu mẫu", "Hệ thống"),
}
FIELDS = ["name", "project", "reference_doctype", "reference_name", "task", "activity_type", "actor", "content",
          "data", "creation"]


# --- what may be read ---------------------------------------------------------------------------------------------------

def target(reference_doctype: str, reference_name: str, user: str | None = None) -> tuple[str, str | None]:
    """(project, task) of a discussion the user may read; PermissionError otherwise."""
    user = user or frappe.session.user
    if reference_doctype == "Task":
        project = frappe.db.get_value("Task", reference_name, "project")
        if not project or not can_see_task(reference_name, project, user):
            raise frappe.PermissionError(_("Bạn không xem được công việc này"))
        return project, reference_name
    if reference_doctype == "Project":
        if not frappe.db.exists("Project", reference_name) or not project_in(get_access(user).read, reference_name):
            raise frappe.PermissionError(_("Bạn không xem được dự án này"))
        return reference_name, None
    raise frappe.ValidationError(_("Chỉ trao đổi trên công việc hoặc dự án"))


def may_read_entry(row, user: str | None = None) -> bool:
    """Can `user` read this PM Activity (or PM Media) row? The task's visibility, or the project's for the rest."""
    access = get_access(user)
    if access.kind == "admin":
        return True
    if row.get("task"):
        return can_see_task(row["task"], row.get("project"), access.user)
    return project_in(access.read, row.get("project"))


# --- reading ----------------------------------------------------------------------------------------------------------

def feed(reference_doctype: str, reference_name: str, before=None, limit=PAGE, kind: str | None = None) -> dict:
    """One page of a discussion, newest first. A project's page holds its tasks' entries too (the ones the user may
    see: PM Activity's query condition applies)."""
    project, task = target(reference_doctype, reference_name)
    limit = max(1, min(cint(limit) or PAGE, MAX_PAGE))
    filters = {"is_deleted": 0}
    if task:
        filters["task"] = task
    else:
        filters["project"] = project
    if kind in KINDS:
        filters["activity_type"] = ["in", KINDS[kind]]
    if cint(before):
        filters["name"] = ["<", cint(before)]
    rows = frappe.get_list("PM Activity", filters=filters, fields=FIELDS, order_by="name desc",
                           limit_page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    follow = _follow_row(frappe.session.user, reference_doctype, reference_name)
    return {
        "entries": decorate(rows, with_task=not task), "more": more, "next": rows[-1].name if more and rows else None,
        "following": bool(follow and follow.watching), "last_read": cint(follow.last_read_id) if follow else 0,
        "unread": unread_count(reference_doctype, reference_name, follow),
    }


def decorate(rows, with_task: bool = False) -> list[dict]:
    """Entries as the screen shows them: names, photos, mentions, the task each one belongs to."""
    if not rows:
        return []
    ids = [row.name for row in rows]
    photos = {}
    for media in frappe.get_all("PM Media", filters={"activity_id": ["in", ids], "is_deleted": 0},
                                fields=["name", "activity_id", "width", "height", "thumb_key", "taken_at", "lat", "lng"],
                                order_by="name asc"):
        photos.setdefault(media.activity_id, []).append(_photo(media))
    users = {row.actor for row in rows}
    names = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
                                as_list=True)) if users else {}
    tasks = {}
    if with_task:
        task_names = {row.task for row in rows if row.task}
        if task_names:
            tasks = {t.name: t for t in frappe.get_all("Task", filters={"name": ["in", list(task_names)]},
                                                       fields=["name", "subject", "pm_wbs_code"])}
    out = []
    for row in rows:
        data = _json(row.get("data"))
        entry = {
            "name": row.name, "type": row.activity_type, "actor": row.actor,
            "actor_name": names.get(row.actor) or row.actor, "content": row.content or "", "creation": row.creation,
            "task": row.task, "photos": photos.get(row.name, []),
            "mentions": (data.get("mentions") or []) if row.activity_type == COMMENT else [],
            "mine": row.actor == frappe.session.user,
        }
        if with_task and row.task and row.task in tasks:
            info = tasks[row.task]
            entry["task_label"] = f"{info.pm_wbs_code or ''} {info.subject}".strip()
        out.append(entry)
    return out


def _photo(media) -> dict:
    return {"name": media.name, "width": media.width, "height": media.height, "thumb": bool(media.thumb_key),
            "taken_at": media.taken_at, "lat": media.lat or None, "lng": media.lng or None}


def _json(value) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) or {}
    except ValueError:
        return {}


def entry(name) -> dict:
    """One entry the user may read, as the screen shows it."""
    row = frappe.db.get_value("PM Activity", cint(name), FIELDS + ["is_deleted"], as_dict=True)
    if not row or row.is_deleted or not may_read_entry(row):
        raise frappe.DoesNotExistError(_("Không tìm thấy mục trao đổi"))
    return decorate([row], with_task=True)[0]


def people(reference_doctype: str, reference_name: str, search: str = "") -> list[dict]:
    """Members who may read this discussion: the ones a comment can mention."""
    project, task = target(reference_doctype, reference_name)
    members = frappe.get_all("PM Project Member", filters={"project": project, "is_active": 1}, pluck="user",
                             distinct=True)
    search = (search or "").strip().lower()
    rows = frappe.get_all("User", filters={"name": ["in", members or [""]], "enabled": 1},
                          fields=["name", "full_name"], order_by="full_name asc")
    out = []
    for row in rows:
        if search and search not in (row.full_name or "").lower() and search not in row.name.lower():
            continue
        if task and not can_see_task(task, project, row.name):
            continue
        out.append({"user": row.name, "full_name": row.full_name or row.name})
    return out[:50]


# --- writing ----------------------------------------------------------------------------------------------------------

def post(reference_doctype: str, reference_name: str, content: str = "", media=None, client_uuid: str | None = None) -> dict:
    """Add a comment. `media`: client_uuids of photos the same user uploaded for this discussion (services/media.py).
    Sending the same client_uuid again returns the first comment."""
    user = frappe.session.user
    client_uuid = (client_uuid or "").strip()[:64] or None
    if client_uuid:
        existing = frappe.db.get_value("PM Activity", {"client_uuid": client_uuid}, ["name", "actor"], as_dict=True)
        if existing:
            if existing.actor != user:
                raise frappe.PermissionError(_("Mã gửi này thuộc người khác"))
            return entry(existing.name)
    project, task = target(reference_doctype, reference_name)
    content = (content or "").strip()
    media = _as_list(media)[:MAX_MEDIA]
    if not content and not media:
        frappe.throw(_("Nhập nội dung hoặc chọn ảnh"))
    if len(content) > MAX_TEXT:
        frappe.throw(_("Nội dung dài quá {0} ký tự").format(MAX_TEXT))
    photos = _photos_for(media, reference_doctype, reference_name, user)
    mentioned = _mentions(content, project, task)
    name = activity.record(reference_doctype, reference_name, COMMENT, content,
                           data={"mentions": mentioned, "media": [p.name for p in photos]},
                           project=project, task=task, actor=user, client_uuid=client_uuid)
    if photos:
        frappe.db.sql("update `tabPM Media` set activity_id = %s where name in %s",
                      (name, tuple(p.name for p in photos)))
    follow(reference_doctype, reference_name, True, user=user, project=project)
    mark_read(reference_doctype, reference_name, name, user=user)
    _tell(reference_doctype, reference_name, project, task, name, content, bool(photos), mentioned)
    _publish(reference_doctype, reference_name, project, name)
    from project_manager.project_manager.services import search_index

    search_index.enqueue_activity(name)
    return entry(name)


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    return [str(item)[:64] for item in value if item]


def _photos_for(media: list[str], reference_doctype, reference_name, user) -> list:
    if not media:
        return []
    rows = frappe.get_all("PM Media", filters={"client_uuid": ["in", media]},
                          fields=["name", "client_uuid", "uploaded_by", "reference_doctype", "reference_name",
                                  "activity_id"])
    found = {row.client_uuid: row for row in rows}
    missing = [uuid for uuid in media if uuid not in found]
    if missing:
        frappe.throw(_("Còn {0} ảnh chưa gửi xong").format(len(missing)), title=_("Chưa đủ ảnh"))
    for row in rows:
        if (row.uploaded_by != user or row.reference_doctype != reference_doctype
                or row.reference_name != reference_name or row.activity_id):
            raise frappe.PermissionError(_("Ảnh này không gắn được vào bình luận"))
    return [found[uuid] for uuid in media]


def _mentions(content: str, project: str, task: str | None) -> list[str]:
    """Addresses mentioned in the text who may read the discussion (others are left as plain text)."""
    out = []
    for _label, user in MENTION.findall(content or ""):
        if user in out or user == frappe.session.user or not frappe.db.exists("User", {"name": user, "enabled": 1}):
            continue
        access = get_access(user)
        allowed = can_see_task(task, project, user) if task else project_in(access.read, project)
        if access.kind != "guest" and allowed:
            out.append(user)
    return out[:20]


def plain(content: str) -> str:
    """The text with mentions shown as names (notifications, search)."""
    return MENTION.sub(lambda match: "@" + match.group(1), content or "")


def _tell(reference_doctype, reference_name, project, task, name, content, with_photos, mentioned) -> None:
    actor = frappe.session.user
    who = frappe.db.get_value("User", actor, "full_name") or actor
    where = (frappe.db.get_value("Task", task, "subject") if task else
             frappe.db.get_value("Project", project, "project_name")) or reference_name
    link = SPA_TASK.format(task) if task else SPA_PROJECT.format(project)
    text = plain(content)
    excerpt = (text[:120] + "…") if len(text) > 120 else text
    if not excerpt and with_photos:
        excerpt = _("đã gửi ảnh")
    for user in mentioned:
        follow(reference_doctype, reference_name, True, user=user, project=project)
        notify_user(user, _("{0} nhắc bạn trong {1}: {2}").format(who, where, excerpt), link, reference_doctype,
                    reference_name)
    followers = frappe.get_all("PM Follow", filters={"reference_doctype": reference_doctype,
                                                     "reference_name": reference_name, "watching": 1}, pluck="user")
    for user in followers:
        if user == actor or user in mentioned:
            continue
        row = {"project": project, "task": task}
        if not may_read_entry(row, user):
            continue
        notify_user(user, _("{0} bình luận ở {1}: {2}").format(who, where, excerpt), link, reference_doctype,
                    reference_name)


def _publish(reference_doctype, reference_name, project, name) -> None:
    """Open screens of this task (and of its project's discussion) reload the new entry (document rooms)."""
    message = {"reference_doctype": reference_doctype, "reference_name": reference_name, "project": project,
               "id": name}
    frappe.publish_realtime("pm_timeline", message, doctype=reference_doctype, docname=reference_name,
                            after_commit=True)
    if reference_doctype != "Project":
        frappe.publish_realtime("pm_timeline", message, doctype="Project", docname=project, after_commit=True)


def hide(name) -> dict:
    """Take back one's own comment (it stays in the database, marked hidden). Administrators may hide any."""
    row = frappe.db.get_value("PM Activity", cint(name), ["name", "actor", "activity_type", "is_deleted", "project",
                                                          "task"], as_dict=True)
    if not row or row.is_deleted or not may_read_entry(row):
        raise frappe.DoesNotExistError(_("Không tìm thấy mục trao đổi"))
    if row.activity_type != COMMENT or (row.actor != frappe.session.user and not is_admin()):
        raise frappe.PermissionError(_("Chỉ người viết mới ẩn được bình luận của mình"))
    frappe.db.set_value("PM Activity", row.name, "is_deleted", 1, update_modified=False)
    frappe.db.sql("update `tabPM Media` set is_deleted = 1 where activity_id = %s", row.name)
    from project_manager.project_manager.services import search_index

    search_index.enqueue_remove(f"act-{row.name}")
    return {"name": row.name, "hidden": True}


# --- following and reading ----------------------------------------------------------------------------------------------

def _follow_row(user, reference_doctype, reference_name):
    return frappe.db.get_value("PM Follow", {"user": user, "reference_doctype": reference_doctype,
                                             "reference_name": reference_name},
                               ["name", "watching", "last_read_id"], as_dict=True)


def follow(reference_doctype: str, reference_name: str, watching: bool = True, user: str | None = None,
           project: str | None = None) -> dict:
    """Start or stop following. Called for the user themself from the screen, and by the services for others."""
    user = user or frappe.session.user
    if user in ("Guest", "Administrator"):
        return {"following": False}
    if project is None:
        project, _task = target(reference_doctype, reference_name)
    row = _follow_row(user, reference_doctype, reference_name)
    if row:
        if cint(row.watching) != cint(watching):
            frappe.db.set_value("PM Follow", row.name, "watching", cint(watching), update_modified=False)
    else:
        try:
            frappe.get_doc({"doctype": "PM Follow", "user": user, "reference_doctype": reference_doctype,
                            "reference_name": reference_name, "project": project,
                            "watching": cint(watching)}).insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            frappe.db.set_value("PM Follow", {"user": user, "reference_doctype": reference_doctype,
                                              "reference_name": reference_name}, "watching", cint(watching))
    return {"following": bool(cint(watching))}


def mark_read(reference_doctype: str, reference_name: str, upto, user: str | None = None) -> dict:
    """Everything up to entry `upto` has been seen. Only moves forward."""
    user = user or frappe.session.user
    upto = cint(upto)
    if user in ("Guest", "Administrator") or upto <= 0:
        return {"last_read": upto}
    row = _follow_row(user, reference_doctype, reference_name)
    if row:
        if upto > cint(row.last_read_id):
            frappe.db.set_value("PM Follow", row.name, "last_read_id", upto, update_modified=False)
        return {"last_read": max(upto, cint(row.last_read_id))}
    project, _task = target(reference_doctype, reference_name, user)
    frappe.get_doc({"doctype": "PM Follow", "user": user, "reference_doctype": reference_doctype,
                    "reference_name": reference_name, "project": project, "watching": 0,
                    "last_read_id": upto}).insert(ignore_permissions=True)
    return {"last_read": upto}


def unread_count(reference_doctype: str, reference_name: str, follow_row=None, cap: int = 99) -> int:
    """Comments by others since the user last read this discussion (capped)."""
    row = follow_row if follow_row is not None else _follow_row(frappe.session.user, reference_doctype, reference_name)
    since = cint(row.last_read_id) if row else 0
    column = "task" if reference_doctype == "Task" else "project"
    # get_list: PM Activity's query condition keeps out the tasks this user does not see
    return len(frappe.get_list("PM Activity", filters={column: reference_name, "name": [">", since],
                                                       "activity_type": COMMENT, "is_deleted": 0,
                                                       "actor": ["!=", frappe.session.user]},
                               pluck="name", limit_page_length=cap, order_by="name desc"))
