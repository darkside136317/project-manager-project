"""Reports sent on a schedule (PM Report Subscription).

A member of staff subscribes people (themselves at least) to a report with its filters, as PDF or Excel, daily, weekly
(a weekday) or monthly (a day 1–28), at an hour. Each hour a job on the long queue sends what is due. **Each recipient
gets the report run as themselves**, so nobody receives rows they may not read; a recipient who may not run the report
gets nothing (noted in last_error). The file goes by email when the site has an outgoing email account (like the
alerts), and an in-app notice links to the report page either way.
Who: the author of a subscription changes or removes it; administrators manage all of them.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime

from project_manager.project_manager import policy
from project_manager.project_manager.services import notify
from project_manager.project_manager.services.errors import log_exception

WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật")
DAILY, WEEKLY, MONTHLY = "Hằng ngày", "Hằng tuần", "Hằng tháng"
FIELDS = ["name", "report", "title", "filters", "file_format", "frequency", "weekday", "day_of_month", "hour",
          "is_active", "owner_user", "last_sent_on", "last_error"]


def _assert_mine(doc) -> None:
    if doc.owner_user != frappe.session.user and not policy.is_admin():
        frappe.throw(_("Chỉ người tạo mới sửa được lịch gửi này"), frappe.PermissionError)


def mine(report: str | None = None) -> list[dict]:
    filters = {} if policy.is_admin() and not report else {"owner_user": frappe.session.user}
    if report:
        filters["report"] = report
    rows = frappe.get_all("PM Report Subscription", filters=filters, fields=FIELDS, order_by="creation desc",
                          limit_page_length=200)
    recipients = {}
    for row in frappe.get_all("PM Report Recipient", filters={"parent": ["in", [str(r.name) for r in rows] or [""]],
                                                              "parenttype": "PM Report Subscription"},
                              fields=["parent", "user"], limit_page_length=0):
        recipients.setdefault(row.parent, []).append(row.user)
    for row in rows:
        row["recipients"] = recipients.get(str(row.name), [])
        row["filters"] = json.loads(row.filters or "{}")
    return rows


def _reachable(user: str | None = None) -> set | None:
    """Who the caller may send reports to: the members of the projects they read (None: everyone on staff)."""
    access = policy.get_access(user)
    if access.read is None:
        return None
    users = set(frappe.get_all("PM Project Member", filters={"project": ["in", list(access.read) or [""]], "is_active": 1},
                               pluck="user"))
    return users | {access.user}


def candidates(txt: str = "") -> list[dict]:
    """People to send a report to, searched by name or account."""
    filters = {"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]}
    reachable = _reachable()
    if reachable is not None:
        filters["name"] = ["in", sorted(reachable) or [""]]
    like = f"%{(txt or '').strip()}%"
    rows = frappe.get_all("User", filters=filters, or_filters={"full_name": ["like", like], "name": ["like", like]},
                          fields=["name", "full_name"], order_by="full_name asc", limit_page_length=40)
    return [r for r in rows if policy.is_staff(r.name)][:20]


def save(report: str, values: dict, recipients, filters=None, name=None) -> dict:
    from project_manager.project_manager.services import reports
    from project_manager.project_manager.services.reports.base import parse_filters

    spec = reports.get(report)  # the author may run it
    values = frappe.parse_json(values) if isinstance(values, str) else (values or {})
    recipients = frappe.parse_json(recipients) if isinstance(recipients, str) else (recipients or [])
    people, reachable = [], _reachable()
    for user in recipients:
        if user and user not in people:
            if not policy.is_staff(user) or not frappe.db.get_value("User", user, "enabled"):
                frappe.throw(_("{0} không phải nhân viên đang hoạt động").format(user))
            if reachable is not None and user not in reachable:
                frappe.throw(_("{0} không cùng dự án nào với bạn: không gửi báo cáo cho họ được").format(user))
            people.append(user)
    parsed = parse_filters(spec, filters)
    stored = json.dumps({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in parsed.items()}, ensure_ascii=False)
    fields = {"title": (values.get("title") or spec.title).strip()[:140], "file_format": values.get("file_format") or "PDF",
              "frequency": values.get("frequency") or WEEKLY, "weekday": values.get("weekday") or WEEKDAYS[0],
              "day_of_month": cint(values.get("day_of_month") or 1), "hour": cint(values.get("hour", 7)),
              "is_active": cint(values.get("is_active", 1)), "filters": stored,
              "recipients": [{"user": u} for u in people]}
    if name:
        doc = frappe.get_doc("PM Report Subscription", name)
        _assert_mine(doc)
        doc.update(fields)
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "PM Report Subscription", "report": report, "owner_user": frappe.session.user,
                              **fields})
        doc.insert(ignore_permissions=True)
    return {"name": doc.name}


def remove(name) -> dict:
    doc = frappe.get_doc("PM Report Subscription", name)
    _assert_mine(doc)
    frappe.delete_doc("PM Report Subscription", name, ignore_permissions=True)
    return {"deleted": name}


# --- sending ----------------------------------------------------------------------------------------------------------

def is_due(row, now) -> bool:
    now = get_datetime(now)
    if not cint(row.is_active) or cint(row.hour) != now.hour:
        return False
    if row.last_sent_on and (now - get_datetime(row.last_sent_on)).total_seconds() < 20 * 3600:
        return False
    if row.frequency == WEEKLY:
        return WEEKDAYS.index(row.weekday or WEEKDAYS[0]) == now.weekday()
    if row.frequency == MONTHLY:
        return cint(row.day_of_month or 1) == now.day
    return True


def build(slug: str, filters, file_format: str) -> tuple[str, bytes, dict]:
    """(file name, content, result) of a report run as the current user."""
    from project_manager.project_manager.services.reports import output

    if file_format == "Excel":
        result, applied = output.prepare(slug, filters, output.MAX_EXPORT_ROWS)
        content, extension = output.to_xlsx(result, applied), "xlsx"
    else:
        result, applied = output.prepare(slug, filters, output.MAX_PRINT_ROWS)
        content, extension = output.to_pdf(result, applied), "pdf"
    return f"bao-cao-{slug}-{getdate(now_datetime()).isoformat()}.{extension}", content, result


def send(name, now=None) -> dict:
    """Send one subscription now, to each recipient as themselves. {sent, emailed: [users], skipped: {user: reason}}."""
    doc = frappe.get_doc("PM Report Subscription", name)
    filters = json.loads(doc.filters or "{}")
    from project_manager.project_manager.services.alerts import email_ready

    sent, emailed, skipped = [], [], {}
    mail = email_ready()
    caller = frappe.session.user
    try:
        for row in doc.recipients:
            frappe.set_user(row.user)
            policy.clear_cache()
            try:
                file_name, content, result = build(doc.report, filters, doc.file_format)
            except frappe.PermissionError:
                skipped[row.user] = _("không có quyền xem báo cáo")
                continue
            except Exception as e:
                log_exception(f"Gửi báo cáo theo lịch {doc.name} cho {row.user}")
                skipped[row.user] = str(e)[:200]
                continue
            finally:
                frappe.set_user(caller)
                policy.clear_cache()
            subject = _("Báo cáo: {0}").format(doc.title or result["title"])
            link = f"/pm/bao-cao/{doc.report}"
            email = frappe.db.get_value("User", row.user, "email")
            if email and mail:
                frappe.sendmail(recipients=[email], subject=subject,
                                message=_("<p>Báo cáo <b>{0}</b> ({1} dòng) gửi theo lịch, kèm tệp {2}.</p>"
                                          "<p>Xem trên hệ thống: {3}</p>").format(
                                    frappe.utils.escape_html(result["title"]), result["total"], file_name,
                                    frappe.utils.get_url(link)),
                                attachments=[{"fname": file_name, "fcontent": content}], delayed=True,
                                reference_doctype="PM Report Subscription", reference_name=str(doc.name))
                emailed.append(row.user)
            notify.notify_user(row.user, subject, link, "PM Report Subscription", str(doc.name))
            sent.append(row.user)
    finally:
        frappe.set_user(caller)
        policy.clear_cache()
    doc.db_set({"last_sent_on": get_datetime(now) if now else now_datetime(),
                "last_error": "; ".join(f"{u}: {why}" for u, why in skipped.items())[:1000] or None},
               update_modified=False)
    return {"sent": sent, "emailed": emailed, "skipped": skipped}


def send_due(now=None) -> int:
    """Send every subscription due this hour. Returns how many were sent."""
    now = get_datetime(now) if now else now_datetime()
    count = 0
    for row in frappe.get_all("PM Report Subscription", filters={"is_active": 1}, fields=FIELDS, limit_page_length=0):
        if is_due(row, now):
            send(row.name, now)
            frappe.db.commit()
            count += 1
    return count


def queue_due():
    """The hourly scheduler entry: the sending runs on the long queue."""
    frappe.enqueue("project_manager.project_manager.services.reports.schedule.send_due", queue="long",
                   job_id="pm-report-subscriptions", deduplicate=True)
