"""Kiểm tra toàn vẹn: the filed items are read again and their SHA-256 compared with the one kept when filing.

Every week (long queue) one part of the archive: the items whose id falls in this week's part, so that with 4 parts
(PM Archive Settings) the whole archive is read every 4 weeks. The archivist may run it on everything, or on one file.
A changed or missing item is listed in the PM Archive Check and raises the alert "Hồ sơ lưu trữ lỗi toàn vẹn" (the
projects' managers, and the archivists directly).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate
from project_manager.project_manager.policy import users_with_capability
from project_manager.project_manager.services import alerts

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.services.locking import MissingContent, digest_of

MAX_DETAILS = 500
COMMIT_EVERY = 200


def parts() -> int:
    return max(1, cint(frappe.db.get_single_value("PM Archive Settings", "check_parts")) or 4)


def weekly() -> None:
    """Scheduler: queue this week's part."""
    part = getdate(nowdate()).isocalendar()[1] % parts()
    frappe.enqueue("pm_archive.pm_archive.services.integrity.run", queue="long", timeout=6 * 3600,
                   trigger="Theo lịch", part=part, job_id="pm-archive-integrity", deduplicate=True)


def start(file: str | None = None) -> str:
    """The archivist asks for a check now: everything, or one file. Returns the check's name."""
    check = _new("Thủ công", file, None)
    frappe.enqueue("pm_archive.pm_archive.services.integrity.run", queue="long", timeout=6 * 3600, check=check,
                   trigger="Thủ công", file=file, enqueue_after_commit=True)
    return check


def _new(trigger: str, file: str | None, part: int | None) -> str:
    scope = _("Hồ sơ {0}").format(file) if file else (_("Phần {0}/{1}").format(part + 1, parts())
                                                      if part is not None else _("Toàn bộ"))
    doc = frappe.get_doc({"doctype": "PM Archive Check", "run_on": now_datetime(), "trigger": trigger, "scope": scope,
                          "status": "Đang chạy", "started_by": frappe.session.user}).insert(ignore_permissions=True)
    return doc.name


def run(trigger: str = "Theo lịch", part: int | None = None, file: str | None = None, check: str | None = None) -> str:
    check = check or _new(trigger, file, part)
    conditions, values = ["f.status = %(filed)s"], {"filed": A.FILED}
    if file:
        conditions.append("f.name = %(file)s")
        values["file"] = file
    if part is not None:
        conditions.append("mod(i.name, %(parts)s) = %(part)s")
        values.update(parts=parts(), part=part)
    items = frappe.db.sql(f"""select i.name, i.seq, i.project, i.archive_file, f.file_number, i.object_key, i.collection,
                                     i.file_url, i.content_type, i.sha256
                              from `tabPM Archive Item` i join `tabPM Archive File` f on f.name = i.archive_file
                              where {' and '.join(conditions)} order by i.name""", values, as_dict=True)
    problems, checked = [], 0
    for item in items:
        try:
            sha, _size = digest_of(item)
            if sha != item.sha256:
                problems.append({"kind": "changed", **_where(item)})
        except MissingContent as error:
            problems.append({"kind": "missing", "error": str(error)[:200], **_where(item)})
        checked += 1
        if checked % COMMIT_EVERY == 0:
            frappe.db.set_value("PM Archive Check", check, "checked", checked, update_modified=False)
            frappe.db.commit()
    changed = sum(1 for p in problems if p["kind"] == "changed")
    frappe.db.set_value("PM Archive Check", check, {
        "checked": checked, "changed": changed, "missing": len(problems) - changed, "finished_on": now_datetime(),
        "status": "Có lỗi" if problems else "Hoàn thành",
        "details": "\n".join(json.dumps(p, ensure_ascii=False) for p in problems[:MAX_DETAILS]) or None},
        update_modified=False)
    frappe.db.commit()
    return check


def _where(item) -> dict:
    return {"item": item.name, "seq": item.seq, "file": item.archive_file, "file_number": item.file_number,
            "project": item.project}


def problems_of(check: str) -> list[dict]:
    details = frappe.db.get_value("PM Archive Check", check, "details") or ""
    return [json.loads(line) for line in details.splitlines() if line.strip()]


def alert_integrity(rule, today) -> list:
    """Alert type "Hồ sơ lưu trữ lỗi toàn vẹn": the newest finished check, when it found problems (one hit per project,
    told to the archivists too)."""
    last = frappe.get_all("PM Archive Check", filters={"status": ["in", ["Hoàn thành", "Có lỗi"]]},
                          fields=["name", "status", "run_on"], order_by="run_on desc", limit_page_length=1)
    if not last or last[0].status != "Có lỗi":
        return []
    archivists = users_with_capability(A.MANAGE_ALL)
    by_project = {}
    for problem in problems_of(last[0].name):
        by_project.setdefault(problem["project"], []).append(problem)
    hits = []
    for project, found in by_project.items():
        numbers = sorted({p["file_number"] for p in found})
        hits.append(alerts._hit("Project", project, project, None, last[0].name, _(
            "Kiểm tra toàn vẹn {0}: {1} tài liệu bị đổi hoặc mất trong hồ sơ {2}").format(
                last[0].name, len(found), ", ".join(numbers)), direct=archivists))
    return hits
