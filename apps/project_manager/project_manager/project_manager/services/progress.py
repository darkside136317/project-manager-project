"""Progress of the work: one report on a task, approval of finished work, a move on the Kanban board.

Late work must say why: when a task is past its end date (or is being finished after it) and carries no delay reason
yet, the report has to give one, with the step that caused it (khâu gây chậm). Delays are then counted by cause and
by party, instead of argued about.

Every report is kept (PM Progress Entry) and appears in the task's timeline (PM Activity). `client_uuid` makes a report
idempotent: a phone that sends the same queued report twice (offline outbox) gets the first one back.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import has_project_capability, is_assigned
from project_manager.project_manager.services import activity, assignments, gates

UPDATE_CAPABILITIES = ("task.update", "plan.edit", "task.assign")


def _load(task: str):
    doc = frappe.get_doc("Task", task)
    if not frappe.has_permission("Task", "write", doc=doc):
        frappe.throw(_("Bạn không có quyền cập nhật công việc này"), frappe.PermissionError)
    if not has_project_capability(doc.project, *UPDATE_CAPABILITIES):
        frappe.throw(_("Vai trò của bạn trong dự án không được cập nhật tiến độ"), frappe.PermissionError)
    return doc


def _late(doc, finishing: bool) -> bool:
    end = doc.get("exp_end_date")
    if not end or doc.status in C.CLOSED_STATUSES:
        return False
    return getdate(nowdate()) > getdate(end) and (finishing or flt(doc.progress) < 100)


def _apply_delay(doc, finishing: bool, delay_reason, delay_source, delay_note) -> None:
    for field, value, doctype in (("pm_delay_reason", delay_reason, "PM Delay Reason"),
                                  ("pm_delay_source", delay_source, "PM Delay Source")):
        if value:
            if not frappe.db.get_value(doctype, value, "is_active"):
                frappe.throw(_("{0} không hợp lệ: {1}").format(_(doctype), value))
            doc.set(field, value)
    if delay_note:
        doc.pm_delay_note = delay_note.strip()
    if _late(doc, finishing) and not (doc.pm_delay_reason and doc.pm_delay_source):
        frappe.throw(_("Công việc đã quá hạn: hãy chọn lý do chậm và khâu gây chậm"), title=_("Thiếu lý do chậm"))


def report(task: str, progress, note: str = "", delay_reason=None, delay_source=None, delay_note=None,
           man_days=None, client_uuid: str | None = None) -> dict:
    """Report the progress (0-100) of a leaf task. Returns the task's new state."""
    if client_uuid:
        existing = frappe.db.get_value("PM Progress Entry", {"client_uuid": client_uuid}, ["name", "task"], as_dict=True)
        if existing:
            return state_of(existing.task)
    doc = _load(task)
    if cint(doc.is_group):
        frappe.throw(_("Tiến độ của nhóm được tính tự động từ các việc con"))
    progress = flt(progress)
    if not 0 <= progress <= 100:
        frappe.throw(_("Tiến độ phải từ 0 đến 100%"))
    before = flt(doc.progress)
    finishing = progress >= 100
    _apply_delay(doc, finishing, delay_reason, delay_source, delay_note)
    if finishing:
        gates.assert_ready(task, allow_submitted=bool(doc.get("pm_reviewer")))
    doc.progress = progress
    doc.status = _status_for(doc, progress)
    doc.pm_last_progress_on = now_datetime()
    if doc.status != C.OPEN and not doc.act_start_date:
        doc.act_start_date = nowdate()
    if doc.status == C.COMPLETED:
        doc.act_end_date = doc.act_end_date or nowdate()
    doc.flags.pm_reason = note
    doc.flags.pm_history_type = "Tiến độ"
    doc.save(ignore_permissions=True)
    frappe.get_doc({"doctype": "PM Progress Entry", "task": task, "entry_date": nowdate(), "reporter": frappe.session.user,
                    "progress_before": before, "progress_after": progress, "note": note or None,
                    "man_days": flt(man_days) or None, "delay_reason": doc.pm_delay_reason,
                    "delay_source": doc.pm_delay_source, "client_uuid": client_uuid or None}).insert(ignore_permissions=True)
    if doc.status == C.COMPLETED:
        assignments.complete_for(task)
    return state_of(task)


def _status_for(doc, progress: float) -> str:
    if progress >= 100:
        return C.REVIEW if doc.get("pm_reviewer") else C.COMPLETED
    return C.WORKING if progress > 0 else C.OPEN


def review(task: str, approve: bool, note: str = "") -> dict:
    """The reviewer (or whoever may approve in the project) accepts finished work, or sends it back with a note."""
    doc = frappe.get_doc("Task", task)
    if doc.status != C.REVIEW:
        frappe.throw(_("Công việc không ở trạng thái chờ duyệt"))
    if doc.pm_reviewer != frappe.session.user and not has_project_capability(doc.project, "task.approve"):
        frappe.throw(_("Bạn không phải người duyệt công việc này"), frappe.PermissionError)
    if not approve and not (note or "").strip():
        frappe.throw(_("Hãy ghi lý do trả lại"))
    doc.status = C.COMPLETED if approve else C.WORKING
    if not approve:
        doc.progress = min(flt(doc.progress), 95)
    else:
        doc.act_end_date = doc.act_end_date or nowdate()
    doc.flags.pm_reason = note or (_("Đã duyệt") if approve else "")
    doc.flags.pm_history_type = "Trạng thái"
    doc.save(ignore_permissions=True)
    if approve:
        assignments.complete_for(task)
    return state_of(task)


def move(task: str, status: str, note: str = "", delay_reason=None, delay_source=None, delay_note=None) -> dict:
    """A move on the Kanban board. Finishing goes through `report` (100%), approval through `review`."""
    if status not in (C.OPEN, C.WORKING, C.REVIEW, C.COMPLETED):
        frappe.throw(_("Trạng thái không hợp lệ"))
    doc = _load(task)
    if cint(doc.is_group):
        frappe.throw(_("Trạng thái của nhóm được tính tự động từ các việc con"))
    if status == doc.status:
        return state_of(task)
    if status in (C.COMPLETED, C.REVIEW):
        if doc.status == C.REVIEW and status == C.COMPLETED:
            return review(task, True, note)
        return report(task, 100, note, delay_reason, delay_source, delay_note)
    if doc.status == C.REVIEW:
        return review(task, False, note or _("Chuyển lại sang {0}").format(C.STATUS_LABELS[status]))
    progress = 0 if status == C.OPEN else max(flt(doc.progress), 1)
    if doc.status == C.COMPLETED:
        progress = min(flt(doc.progress), 95)
    return report(task, progress, note or _("Chuyển sang {0}").format(C.STATUS_LABELS[status]), delay_reason,
                  delay_source, delay_note)


def state_of(task: str) -> dict:
    values = frappe.db.get_value("Task", task, ["name", "status", "progress", "pm_is_overdue", "pm_delay_days",
                                                "pm_delay_reason", "pm_delay_source", "pm_last_progress_on"], as_dict=True)
    values["status_label"] = C.STATUS_LABELS.get(values.status, values.status)
    values["mine"] = is_assigned(task)
    return values


def history(task: str, limit: int = 50) -> list[dict]:
    """The progress reports of a task, newest first (the timeline shows them too)."""
    frappe.get_doc("Task", task).check_permission("read")
    return frappe.get_all("PM Progress Entry", filters={"task": task},
                          fields=["name", "entry_date", "reporter", "progress_before", "progress_after", "note",
                                  "delay_reason", "delay_source", "creation"],
                          order_by="name desc", limit_page_length=max(1, min(cint(limit), 200)))


def record_activity(doc, method=None) -> None:
    """Task on_update (doc_events): every change that matters goes to the timeline, with its reason."""
    if doc.flags.in_insert or frappe.flags.in_import or doc.flags.pm_skip_history:
        return
    before = doc.get_doc_before_save()
    if before is None:
        return
    reason = doc.flags.pm_reason or ""
    parts = []
    changed_dates = []
    for field, label in (("exp_start_date", _("bắt đầu")), ("exp_end_date", _("hạn hoàn thành"))):
        old, new = before.get(field), doc.get(field)
        if (getdate(old) if old else None) != (getdate(new) if new else None):
            changed_dates.append(field)
            parts.append(_("{0}: {1} → {2}").format(label, _day(old), _day(new)))
    if changed_dates:
        activity.record("Task", doc.name, "Đổi hạn", "; ".join(parts) + (f". {_('Lý do')}: {reason}" if reason else ""),
                        data={f: [str(before.get(f) or ""), str(doc.get(f) or "")] for f in changed_dates} | {"reason": reason})
    if flt(before.progress) != flt(doc.progress) or before.status != doc.status:
        kind = doc.flags.pm_history_type or ("Tiến độ" if flt(before.progress) != flt(doc.progress) else "Trạng thái")
        text = _("Tiến độ {0}% → {1}%").format(_pct(before.progress), _pct(doc.progress))
        if before.status != doc.status:
            text += "; " + _("trạng thái {0} → {1}").format(C.STATUS_LABELS.get(before.status, before.status),
                                                            C.STATUS_LABELS.get(doc.status, doc.status))
        activity.record("Task", doc.name, kind, text + (f". {reason}" if reason else ""),
                        data={"progress": [flt(before.progress), flt(doc.progress)], "status": [before.status, doc.status]})
    if (before.parent_task or "") != (doc.parent_task or "") or before.subject != doc.subject:
        activity.record("Task", doc.name, "Thay đổi", _("Đổi tên hoặc vị trí trong cây công việc") +
                        (f". {reason}" if reason else ""),
                        data={"subject": [before.subject, doc.subject], "parent": [before.parent_task, doc.parent_task]})


def _pct(value) -> str:
    return f"{flt(value, 1):g}"


def _day(value) -> str:
    return frappe.utils.formatdate(value, "dd/MM/yyyy") if value else "—"
