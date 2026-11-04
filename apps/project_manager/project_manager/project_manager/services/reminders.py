"""Daily reminders (07:00): the work each person is responsible for that is due soon or already late.

One notification per person and day, not one per task: "3 việc sắp đến hạn, 2 việc quá hạn". Who is reminded: the
live accountable (Chịu trách nhiệm chính) and responsible (Thực hiện) people of each open leaf task. The rules of M7
(escalation, quiet hours, teams) replace this; until then it is the simple safety net the plan asks for in M2.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.services.notify import notify_user, sent_today

MY_TASKS = "/pm/viec-cua-toi"


def due_work(today=None, soon_days: int | None = None) -> dict:
    """{user: {"late": n, "soon": n}} of open leaf tasks ending by today + soon_days."""
    today = today or nowdate()
    if soon_days is None:
        soon_days = cint(frappe.db.get_single_value("PM Settings", "due_soon_days") or 2)
    rows = frappe.db.sql(
        f"""select a.user, sum(date(t.exp_end_date) < %(today)s) as late, sum(date(t.exp_end_date) >= %(today)s) as soon
            from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
            where a.is_active = 1 and a.state in %(states)s and a.raci in %(roles)s and ifnull(a.user, '') != ''
              and t.is_group = 0 and t.status not in ('{C.COMPLETED}', '{C.CANCELLED}', '{C.REVIEW}')
              and t.exp_end_date is not null and date(t.exp_end_date) <= %(limit)s
            group by a.user""",
        {"today": today, "limit": add_days(today, soon_days), "states": C.LIVE_STATES,
         "roles": (C.ACCOUNTABLE, C.RESPONSIBLE)}, as_dict=True)
    return {r.user: {"late": cint(r.late), "soon": cint(r.soon)} for r in rows}


def message(late: int, soon: int) -> str:
    parts = []
    if late:
        parts.append(_("{0} việc quá hạn").format(late))
    if soon:
        parts.append(_("{0} việc sắp đến hạn").format(soon))
    return _("Bạn có {0}").format(_(" và ").join(parts))


def send_daily() -> int:
    """Scheduler (07:00). Returns the number of people notified."""
    if not cint(frappe.db.get_single_value("PM Settings", "daily_reminders")):
        return 0
    sent = 0
    enabled = set(frappe.get_all("User", filters={"enabled": 1}, pluck="name"))
    for user, counts in due_work().items():
        if user not in enabled:
            continue
        subject = message(counts["late"], counts["soon"])
        if sent_today(user, subject):
            continue
        if notify_user(user, subject, MY_TASKS):
            sent += 1
    frappe.db.commit()
    return sent
