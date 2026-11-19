"""Nộp lưu: the archivist files an archive file; from then on it is read-only.

Filing runs on the long queue, one job per file: every item's content is read (in chunks) and its SHA-256 kept, the
left-out items are dropped, and the file gets a manifest digest over its items' numbers, digests and sources. A file
whose content cannot all be read stays where it was (Chờ nộp lưu) with the reason; running it again starts over.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from project_manager.project_manager.services import activity, object_storage
from project_manager.project_manager.services.audit import log_activity
from project_manager.project_manager.services.notify import notify_user

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.services import filing

PROGRESS_EVERY = 50


class MissingContent(Exception):
    """An item's file cannot be read."""


def chunks_of(item) -> tuple:
    """(iterator of bytes, content type, length or None) of an item's content."""
    if item.object_key:
        try:
            return object_storage.open_stream(item.object_key, item.collection)
        except Exception as error:  # noqa: BLE001 (gone from MinIO, store down, bad key)
            raise MissingContent(f"{item.object_key}: {error}") from error
    if item.file_url:
        name = frappe.db.get_value("File", {"file_url": item.file_url}, "name")
        if not name:
            raise MissingContent(f"{item.file_url}: không còn tệp")
        try:
            content = frappe.get_doc("File", name).get_content()
        except Exception as error:  # noqa: BLE001
            raise MissingContent(f"{item.file_url}: {error}") from error
        data = content.encode() if isinstance(content, str) else content
        return iter([data]), item.content_type, len(data)
    raise MissingContent(_("Tài liệu không có tệp"))


def digest_of(item) -> tuple[str, int]:
    """(SHA-256, size) of an item's content, read in chunks."""
    chunks, _type, _length = chunks_of(item)
    digest, size = hashlib.sha256(), 0
    for chunk in chunks:
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def manifest_of(name: str) -> str:
    rows = frappe.db.sql("""select seq, sha256, source_doctype, source_name from `tabPM Archive Item`
                            where archive_file = %s and excluded = 0 order by seq""", name)
    text = "\n".join(f"{seq}\t{sha}\t{doctype}:{source}" for seq, sha, doctype, source in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request(names: list[str]) -> dict:
    """Queue the filing of these files (the caller is the archivist). Returns {"queued", "skipped"}."""
    queued, skipped = [], []
    for name in names or []:
        file = frappe.db.get_value("PM Archive File", name, ["name", "status", "item_count"], as_dict=True)
        if not file or file.status == A.FILED or not cint(file.item_count):
            skipped.append(name)
            continue
        total = frappe.db.count("PM Archive Item", {"archive_file": name, "excluded": 0})
        frappe.db.set_value("PM Archive File", name, {"lock_total": total, "lock_done": 0, "lock_error": None},
                            update_modified=False)
        frappe.enqueue("pm_archive.pm_archive.services.locking.run", queue="long", timeout=6 * 3600, name=name,
                       user=frappe.session.user, enqueue_after_commit=True, job_id=f"pm-archive-lock:{name}",
                       deduplicate=True)
        queued.append(name)
    return {"queued": queued, "skipped": skipped}


def run(name: str, user: str) -> bool:
    """File one archive file. Returns True when it was filed."""
    file = frappe.db.get_value("PM Archive File", name, ["name", "project", "status", "file_number", "title"], as_dict=True)
    if not file or file.status == A.FILED:
        return False
    items = frappe.get_all("PM Archive Item", filters={"archive_file": name, "excluded": 0},
                           fields=["name", "object_key", "collection", "file_url", "content_type", "sha256", "seq"],
                           order_by="seq asc", limit_page_length=0)
    if not items:
        return False
    for done, item in enumerate(items, 1):
        try:
            sha, size = digest_of(item)
        except MissingContent as error:  # (digests already written are true: nothing to undo)
            frappe.db.set_value("PM Archive File", name, {
                "lock_error": _("Tài liệu số {0} không đọc được: {1}").format(item.seq, str(error)[:300])},
                update_modified=False)
            frappe.db.commit()
            return False
        if item.sha256 and item.sha256 != sha:  # a source that should never change under its key did
            frappe.db.set_value("PM Archive File", name, {
                "lock_error": _("Tài liệu số {0} đã khác lúc được xếp vào hồ sơ (SHA-256 không khớp)").format(item.seq)},
                update_modified=False)
            frappe.db.commit()
            return False
        frappe.db.set_value("PM Archive Item", item.name, {"sha256": sha, "size_bytes": size}, update_modified=False)
        if done % PROGRESS_EVERY == 0:
            frappe.db.set_value("PM Archive File", name, "lock_done", done, update_modified=False)
            frappe.db.commit()
    frappe.db.delete("PM Archive Item", {"archive_file": name, "excluded": 1})  # left out: never part of the file
    filing.refresh(name)
    now = now_datetime()
    frappe.db.set_value("PM Archive File", name, {
        "status": A.FILED, "locked_by": user, "locked_on": now, "manifest_sha256": manifest_of(name),
        "lock_done": len(items), "lock_error": None}, update_modified=False)
    text = _("Nộp lưu hồ sơ {0}: {1}").format(file.file_number, file.title)
    activity.record("Project", file.project, "Hệ thống", text, data={"archive_file": name, "items": len(items)},
                    actor=user)
    log_activity("Cập nhật", "PM Archive File", name, f"{text} ({len(items)} tài liệu)", user=user)
    manager = frappe.db.get_value("Project", file.project, "pm_manager")
    if manager and manager != user:
        notify_user(manager, text, f"/pm/luu-tru/{name}", "PM Archive File", name)
    frappe.db.commit()
    return True
