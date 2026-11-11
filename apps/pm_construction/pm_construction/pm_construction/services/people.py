"""What the construction layer adds to the M9 screens of the core (hooks pm_productivity, pm_conflicts,
pm_portfolio_columns; the core never imports this module).

* Productivity of the crews: the quantities of the site diaries (submitted or confirmed) per work item, shared among
  the crews that worked on it by their man-days (confirmed attendance sheets, lines on that work item). A crew's
  productivity is quantity / man-days, per unit.
* Conflicts: one machine booked by two projects on the same days (PMC Machine Booking).
* Portfolio columns: the actual cost against the value of the work done (only with finance.view in the project), the
  work items over their material norm (open or acknowledged alerts "Vượt định mức vật tư").
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate
from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import has_project_capability

from pm_construction.pm_construction import constants as K

BOOKED, CANCELLED = "Đã đặt", "Đã hủy"


def productivity(first, last) -> list[dict]:
    """[{"team", "team_name", "project", "task", "uom", "qty", "man_days"}] of the period."""
    quantities = frappe.db.sql("""select q.task, q.project, sum(q.qty) as qty, max(t.pmc_uom) as uom
                                  from `tabPMC Diary Quantity` q join `tabPMC Site Diary` d on d.name = q.diary
                                  join `tabTask` t on t.name = q.task
                                  where d.status in %(counted)s and q.entry_date between %(first)s and %(last)s
                                  group by q.task, q.project having sum(q.qty) > 0""",
                               {"counted": K.DIARY_COUNTED, "first": first, "last": last}, as_dict=True)
    if not quantities:
        return []
    days = frappe.db.sql("""select a.team, l.task, sum(l.man_days) as man_days
                            from `tabPMC Attendance Line` l join `tabPMC Crew Attendance` a on a.name = l.parent
                            where a.status = %(confirmed)s and a.attendance_date between %(first)s and %(last)s
                              and l.task in %(tasks)s and ifnull(a.team, '') != ''
                            group by a.team, l.task having sum(l.man_days) > 0""",
                         {"confirmed": K.SHEET_CONFIRMED, "first": first, "last": last,
                          "tasks": tuple(q.task for q in quantities)}, as_dict=True)
    by_task = {}
    for row in days:
        by_task.setdefault(row.task, []).append(row)
    names = dict(frappe.get_all("PM Team", filters={"name": ["in", list({d.team for d in days}) or [""]]},
                                fields=["name", "team_name"], as_list=True))
    out = []
    for work in quantities:
        crews = by_task.get(work.task) or []
        total = sum(flt(c.man_days) for c in crews)
        for crew in crews:  # the quantity of the work item, by the man-days of each crew
            out.append({"team": crew.team, "team_name": names.get(crew.team) or crew.team, "project": work.project,
                        "task": work.task, "uom": work.uom, "qty": flt(work.qty) * flt(crew.man_days) / total,
                        "man_days": flt(crew.man_days)})
    return out


def machine_conflicts(first, last) -> list[dict]:
    """A machine booked by two projects on overlapping days, within the period."""
    from project_manager.project_manager.services.workload import monday

    first, last = getdate(first), getdate(last)
    rows = frappe.get_all("PMC Machine Booking", filters={"status": BOOKED, "from_date": ["<=", last],
                                                          "to_date": [">=", first]},
                          fields=["name", "machine", "machine_name", "project", "from_date", "to_date"],
                          order_by="machine asc, from_date asc", limit_page_length=0)
    by_machine = {}
    for row in rows:
        by_machine.setdefault(row.machine, []).append(row)
    out = []
    for machine, bookings in by_machine.items():
        for i, a in enumerate(bookings):
            for b in bookings[i + 1:]:
                if a.project == b.project:
                    continue
                start = max(getdate(a.from_date), getdate(b.from_date), first)
                end = min(getdate(a.to_date), getdate(b.to_date), last)
                if start > end:
                    continue
                span = (end - start).days + 1
                out.append({"kind": "Máy", "subject": a.machine_name or machine, "machine": machine,
                            "week": monday(start).isoformat(), "from": start.isoformat(), "to": end.isoformat(),
                            "projects": {a.project: span, b.project: span},
                            "message": _("Máy {0} được hai dự án đặt từ {1} đến {2}").format(
                                a.machine_name or machine, start.strftime("%d/%m"), end.strftime("%d/%m"))})
    return out


def clashes(machine: str, from_date, to_date, project: str, exclude=None) -> list[dict]:
    """The bookings of other projects that overlap these days."""
    filters = {"machine": machine, "status": BOOKED, "project": ["!=", project], "from_date": ["<=", getdate(to_date)],
               "to_date": [">=", getdate(from_date)]}
    if exclude:
        filters["name"] = ["!=", exclude]
    return frappe.get_all("PMC Machine Booking", filters=filters, fields=["name", "project", "from_date", "to_date"],
                          order_by="from_date asc")


def portfolio_columns(projects) -> dict:
    """{project: {key: {"label", "value", "format", "tone"}}}."""
    if not projects:
        return {}
    out = {}
    finance = [p for p in projects if has_project_capability(p, "finance.view")]
    if finance:
        for row in frappe.db.sql("""select project, sum(ifnull(pmc_actual_cost, 0)) as actual,
                                           sum(ifnull(pmc_done_qty, 0) * ifnull(pmc_unit_price, 0)) as earned
                                    from `tabTask` where project in %(p)s and is_group = 0 and status != %(cancelled)s
                                    group by project""", {"p": tuple(finance), "cancelled": C.CANCELLED}, as_dict=True):
            if flt(row.earned) > 0 or flt(row.actual) > 0:
                ratio = flt(row.actual) / flt(row.earned) if flt(row.earned) else None
                out.setdefault(row.project, {})["cost_ratio"] = {
                    "label": _("Chi phí / giá trị làm được"), "value": None if ratio is None else round(ratio, 3),
                    "format": "percent",
                    "tone": "bad" if ratio is None or ratio > 1.05 else "warn" if ratio > 0.95 else "good"}
    for project, count in frappe.db.sql("""select project, count(distinct reference_name) from `tabPM Alert`
                                           where rule_type = %(type)s and state in ('Đang mở', 'Đã xác nhận')
                                             and project in %(p)s
                                           group by project""", {"type": K.OVER_NORM, "p": tuple(projects)}):
        out.setdefault(project, {})["over_norm"] = {"label": _("Công tác vượt định mức"), "value": count,
                                                    "format": "number", "tone": "bad" if count else None}
    return out
