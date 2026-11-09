"""Photos from the field (PM Media): sent one by one before the comment that carries them.

* The phone shrinks a photo to at most 1600 px before sending it (frontend/src/lib/images.js), and reads when and
  where it was taken (EXIF, or the phone's position when the user asked for it).
* Each upload carries a client_uuid: a phone that lost the answer and sends again gets the first photo back.
* The original stays in MinIO; a thumbnail is made in the background right after the upload commits.
* Photos are read through `serve`, which checks the user may read the task (or project) every time.
"""

import io
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from project_manager.project_manager.services import object_storage
from project_manager.project_manager.services.timeline import may_read_entry, target

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
THUMB_SIDE = 480
TYPES = ((b"\xff\xd8\xff", "jpg", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
         (b"RIFF", "webp", "image/webp"))
FIELDS = ["name", "project", "reference_doctype", "reference_name", "task", "activity_id", "file_name", "content_type",
          "size_bytes", "width", "height", "taken_at", "lat", "lng", "uploaded_by", "object_key", "thumb_key",
          "client_uuid", "is_deleted", "creation"]


def kind_of(raw: bytes) -> tuple[str, str] | None:
    """(extension, content type) of a JPEG, PNG or WebP picture; None for anything else."""
    for magic, extension, content_type in TYPES:
        if raw.startswith(magic) and (extension != "webp" or raw[8:12] == b"WEBP"):
            return extension, content_type
    return None


def upload(reference_doctype: str, reference_name: str, client_uuid: str, raw: bytes, filename: str = "",
           taken_at=None, lat=None, lng=None) -> dict:
    """Keep one photo for a task's (or a project's) discussion. Returns the row as the screen needs it."""
    user = frappe.session.user
    client_uuid = (client_uuid or "").strip()
    if not client_uuid or len(client_uuid) > 64:
        frappe.throw(_("Thiếu mã gửi của ảnh"))
    existing = _by_uuid(client_uuid)
    if existing:
        if existing.uploaded_by != user:
            raise frappe.PermissionError(_("Mã gửi này thuộc người khác"))
        return describe(existing)
    project, task = target(reference_doctype, reference_name)
    if not raw:
        frappe.throw(_("Không nhận được ảnh"))
    if len(raw) > MAX_BYTES:
        frappe.throw(_("Ảnh phải nhỏ hơn 10 MB"))
    found = kind_of(raw)
    if not found:
        frappe.throw(_("Chỉ nhận ảnh JPEG, PNG hoặc WebP"))
    extension, content_type = found
    width, height = _size(raw)
    name = (filename or "").strip().rsplit("/", 1)[-1][:120] or f"anh.{extension}"
    key = object_storage.put(raw, name, content_type, "media")
    doc = frappe.get_doc({
        "doctype": "PM Media", "project": project, "reference_doctype": reference_doctype,
        "reference_name": reference_name, "task": task, "file_name": name, "content_type": content_type,
        "size_bytes": len(raw), "width": width, "height": height, "taken_at": _when(taken_at),
        "lat": _coordinate(lat, 90), "lng": _coordinate(lng, 180), "uploaded_by": user, "object_key": key,
        "client_uuid": client_uuid,
    })
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # the same photo arrived twice at once: keep the first, drop this copy's object
        object_storage.enqueue_delete([key], "media")
        existing = _by_uuid(client_uuid)
        if existing:
            return describe(existing)
        raise
    frappe.enqueue("project_manager.project_manager.services.media.make_thumbnail", name=doc.name, queue="short",
                   enqueue_after_commit=True, job_id=f"pm-thumb:{frappe.local.site}:{doc.name}", deduplicate=True)
    return describe(frappe._dict(doc.as_dict()))


def _by_uuid(client_uuid: str):
    return frappe.db.get_value("PM Media", {"client_uuid": client_uuid}, FIELDS, as_dict=True)


def _size(raw: bytes) -> tuple[int, int]:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(raw)) as picture:
            width, height = picture.size
    except (UnidentifiedImageError, OSError):
        frappe.throw(_("Không đọc được ảnh"))
    if width * height > MAX_PIXELS:
        frappe.throw(_("Ảnh quá lớn: hãy gửi ảnh nhỏ hơn 40 triệu điểm ảnh"))
    return width, height


def _when(value):
    """When the photo was taken, as sent by the phone (local time); ignored when it makes no sense."""
    if not value:
        return None
    try:
        moment = get_datetime(value)
    except Exception:
        return None
    if not moment:
        return None
    moment = moment.replace(tzinfo=None, microsecond=0)
    if moment < datetime(2000, 1, 1) or moment > now_datetime() + timedelta(days=1):
        return None
    return moment


def _coordinate(value, limit: float):
    if value in (None, ""):
        return None
    number = flt(value, 7)
    return number if -limit <= number <= limit and number != 0 else None


def describe(row) -> dict:
    return {"name": row.name, "client_uuid": row.client_uuid, "width": row.width, "height": row.height,
            "thumb": bool(row.thumb_key), "taken_at": row.taken_at, "lat": row.lat or None, "lng": row.lng or None,
            "activity_id": row.activity_id or None}


def make_thumbnail(name) -> None:
    """A small JPEG for lists and timelines (background, after the upload committed)."""
    from PIL import Image, ImageOps

    row = frappe.db.get_value("PM Media", cint(name), ["name", "object_key", "thumb_key"], as_dict=True)
    if not row or row.thumb_key:
        return
    raw = object_storage.get(row.object_key, "media")
    with Image.open(io.BytesIO(raw)) as picture:
        picture = ImageOps.exif_transpose(picture)
        picture.thumbnail((THUMB_SIDE, THUMB_SIDE))
        if picture.mode not in ("RGB", "L"):
            picture = picture.convert("RGB")
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=78, optimize=True)
    key = object_storage.put(out.getvalue(), f"thumb-{row.name}.jpg", "image/jpeg", "thumbs")
    frappe.db.set_value("PM Media", row.name, "thumb_key", key, update_modified=False)
    frappe.db.commit()
    message = frappe.db.get_value("PM Media", row.name, ["reference_doctype", "reference_name", "activity_id"],
                                  as_dict=True)
    if message:
        frappe.publish_realtime("pm_thumb", {"media": row.name, "activity": message.activity_id},
                                doctype=message.reference_doctype, docname=message.reference_name)


def sweep_thumbnails(limit: int = 200) -> int:
    """Photos whose thumbnail job was lost (a worker restarted): make them now. Runs every few minutes."""
    names = frappe.get_all("PM Media", filters={"thumb_key": ["is", "not set"], "is_deleted": 0,
                                                "creation": ["<", now_datetime() - timedelta(minutes=2)]},
                           pluck="name", limit_page_length=limit, order_by="name asc")
    for name in names:
        try:
            make_thumbnail(name)
        except Exception:
            frappe.db.rollback()
            frappe.log_error("Ảnh thu nhỏ", f"PM Media {name}\n{frappe.get_traceback()}")
    return len(names)


def readable(name):
    """The row of a photo the user may see; DoesNotExist otherwise (also for a hidden one)."""
    row = frappe.db.get_value("PM Media", cint(name), FIELDS, as_dict=True)
    if not row or row.is_deleted or not may_read_entry(row):
        raise frappe.DoesNotExistError(_("Không tìm thấy ảnh"))
    return row


def serve(name, size: str = "thumb"):
    """The photo itself (`size` "thumb" or "full"), streamed from MinIO after the permission check."""
    from project_manager.project_manager.services.files import stream

    row = readable(name)
    if size == "thumb" and row.thumb_key:
        return stream(row.thumb_key, "thumbs", "image/jpeg", f"thumb-{row.name}.jpg", inline=True, immutable=True)
    # the full photo answers a thumbnail request only until the thumbnail exists: that answer must not be kept
    return stream(row.object_key, "media", row.content_type, row.file_name, inline=True, immutable=size != "thumb")


def gallery(project: str, task: str | None = None, before=None, limit: int = 60) -> dict:
    """Photos of a project (or one task), newest first, that the user may see."""
    if task:
        target("Task", task)
    else:
        target("Project", project)
    limit = max(1, min(cint(limit) or 60, 200))
    filters = {"project": project, "is_deleted": 0, "activity_id": [">", 0]}  # sent with a comment (an Int is 0 before)
    if task:
        filters["task"] = task
    if cint(before):
        filters["name"] = ["<", cint(before)]
    rows = frappe.get_list("PM Media", filters=filters, fields=FIELDS, order_by="name desc",
                           limit_page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    tasks = {}
    names = {row.task for row in rows if row.task}
    if names:
        tasks = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip()
                 for t in frappe.get_all("Task", filters={"name": ["in", list(names)]},
                                         fields=["name", "subject", "pm_wbs_code"])}
    users = {row.uploaded_by for row in rows}
    full = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
                               as_list=True)) if users else {}
    photos = []
    for row in rows:
        item = describe(row)
        item.update({"task": row.task, "task_label": tasks.get(row.task), "uploaded_by": row.uploaded_by,
                     "uploaded_by_name": full.get(row.uploaded_by) or row.uploaded_by, "creation": row.creation})
        photos.append(item)
    return {"photos": photos, "more": more, "next": rows[-1].name if more and rows else None}
