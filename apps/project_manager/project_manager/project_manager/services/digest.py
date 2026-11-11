"""Tóm tắt (digests): one notice a day for each person, one a week for each project manager, instead of a stream.

* Daily (07:00): the alerts still open that reached the person, their work due soon or late, the assignments they
  have not answered, the forms waiting for their approval. Nothing to say: nothing sent.
* Weekly (Monday 07:00): for each project they manage, progress over the week, health, SPI, the forecast against the
  baseline, alerts opened and still open.
* Each person may turn either off (PM Notification Preference); email follows the same rules as alerts.
Replaces the simple daily reminder of M2 (services/reminders.py keeps the counting).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.services import alerts, reminders
from project_manager.project_manager.services.notify import notify_user

MY_TASKS, ALERTS, PORTFOLIO = "/pm/viec-cua-toi", "/pm/canh-bao", "/pm/danh-muc-du-an"
DAILY, WEEKLY = "Tóm tắt hôm nay", "Tóm tắt tuần"


def _sent(user: str, prefix: str) -> bool:
    """Has this person had this digest today already (whatever it said)?"""
    return bool(frappe.db.exists("Notification Log", {
        "for_user": user, "subject": ["like", f"{prefix}:%"],
        "creation": [">=", get_datetime(f"{nowdate()} 00:00:00")]}))


def daily_lines(user: str, today=None, due: dict | None = None) -> list[str]:
    today = getdate(today or nowdate())
    lines = []
    opened = frappe.db.count("PM Alert", {"state": alerts.OPEN, "recipients": ["like", f'%"{user}"%']})
    if opened:
        lines.append(_("{0} cảnh báo đang mở").format(opened))
    work = (reminders.due_work(today) if due is None else due).get(user, {})
    if cint(work.get("late")):
        lines.append(_("{0} việc quá hạn").format(work["late"]))
    if cint(work.get("soon")):
        lines.append(_("{0} việc sắp đến hạn").format(work["soon"]))
    pending = frappe.db.count("PM Task Assignment", {"user": user, "state": C.PENDING, "is_active": 1})
    if pending:
        lines.append(_("{0} việc chờ bạn nhận").format(pending))
    from project_manager.project_manager.services import forms

    current = frappe.session.user
    try:
        frappe.set_user(user)  # what this person may approve, under their own permissions
        waiting = cint(forms.waiting_for_me(1)["total"])
    except Exception:
        waiting = 0
    finally:
        frappe.set_user(current)
    if waiting:
        lines.append(_("{0} biểu mẫu chờ bạn duyệt").format(waiting))
    return lines


def _people() -> set:
    users = set(frappe.get_all("PM Task Assignment", filters={"is_active": 1, "state": ["in", C.LIVE_STATES],
                                                             "user": ["is", "set"]}, pluck="user", distinct=True))
    users |= set(frappe.get_all("PM Project Member", filters={"is_active": 1}, pluck="user", distinct=True))
    return {u for u in users if u and u not in ("Administrator", "Guest")}


def daily(today=None) -> int:
    if not cint(frappe.db.get_single_value("PM Settings", "daily_reminders")):
        return 0
    today = getdate(today or nowdate())
    sent = 0
    use_email = alerts.email_ready()
    due = reminders.due_work(today)
    for user in sorted(_people()):
        if not frappe.db.get_value("User", user, "enabled") or _sent(user, DAILY):
            continue
        pref = alerts.preference(user)
        if not cint(pref.digest_daily):
            continue
        lines = daily_lines(user, today, due)
        if not lines:
            continue
        subject = f"{DAILY}: " + ", ".join(lines)
        notify_user(user, subject, ALERTS if "cảnh báo" in subject else MY_TASKS)
        if use_email and cint(pref.email):
            alerts.send_email(user, subject, MY_TASKS)
        sent += 1
    frappe.db.commit()
    return sent


def project_week(project: str, today=None) -> str:
    """One line about a project's week."""
    today = getdate(today or nowdate())
    info = frappe.db.get_value("Project", project, ["project_name", "percent_complete", "pm_health", "pm_spi",
                                                    "pm_forecast_end"], as_dict=True)
    before = frappe.db.get_value("PM Snapshot", {"project": project, "task": ["is", "not set"],
                                                 "snapshot_date": ["<=", add_days(today, -7)]},
                                 "progress", order_by="snapshot_date desc")
    gained = flt(info.percent_complete) - flt(before or 0)
    opened = frappe.db.count("PM Alert", {"project": project, "opened_on": [">=", add_days(today, -7)]})
    still = frappe.db.count("PM Alert", {"project": project, "state": alerts.OPEN})
    parts = [_("{0}: {1}% (+{2} trong tuần)").format(info.project_name, round(flt(info.percent_complete)), round(gained, 1))]
    if info.pm_health:
        parts.append(_("sức khỏe {0}").format(info.pm_health))
    if flt(info.pm_spi):
        parts.append(f"SPI {flt(info.pm_spi):.2f}")
    if info.pm_forecast_end:
        parts.append(_("dự báo xong {0}").format(getdate(info.pm_forecast_end).strftime("%d/%m/%Y")))
    parts.append(_("{0} cảnh báo mới, {1} đang mở").format(opened, still))
    return "; ".join(parts)


def weekly(today=None) -> int:
    if not cint(frappe.db.get_single_value("PM Settings", "digest_weekly")):
        return 0
    today = getdate(today or nowdate())
    projects = frappe.get_all("Project", filters={"pm_is_template": 0, "pm_state": ["in", ["Chuẩn bị", "Đang thực hiện"]],
                                                  "pm_manager": ["is", "set"]}, fields=["name", "pm_manager"])
    by_manager = {}
    for row in projects:
        by_manager.setdefault(row.pm_manager, []).append(row.name)
    sent = 0
    use_email = alerts.email_ready()
    for manager, names in by_manager.items():
        pref = alerts.preference(manager)
        if not cint(pref.digest_weekly) or _sent(manager, WEEKLY):
            continue
        lines = [project_week(name, today) for name in sorted(names)]
        subject = f"{WEEKLY}: " + " | ".join(lines)
        notify_user(manager, subject[:500], PORTFOLIO)
        if use_email and cint(pref.email):
            alerts.send_email(manager, subject, PORTFOLIO)
        sent += 1
    frappe.db.commit()
    return sent
