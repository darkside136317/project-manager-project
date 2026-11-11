"""Hiệu suất (performance) of people, crews and projects over a period.

Per person and project, from the tasks they answer for or do (Chịu trách nhiệm chính, Thực hiện):
* done: leaf tasks finished in the period; on time when finished by their planned end;
* late open: open tasks whose planned end is before the end of the period;
* delay: days between the planned end and the real end of the tasks finished late;
* progress reports and the man-days written in them.
Productivity (quantity per man-day) comes from the industry layers (hook pm_productivity: the construction layer reads
the site diaries and the confirmed attendance).

Who sees whom (services/workload.scope): everyone their own; the leader of a team its members; perf.view_project in a
project everyone's work in that project; perf.view_all everything. Always within the projects the viewer may read.

Each Monday the week before is kept (PM Performance Snapshot, per person and project, per project, per crew and
project): the trend of the figures that cannot be read back later (what was late at the end of a week).
"""

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import project_in
from project_manager.project_manager.services.workload import may_see_pair, monday, scope, visible_people

PERIODS = {"week": 1, "4w": 4, "quarter": 13}
KEYS = ("done", "on_time", "late_done", "open_late", "delay_days", "reports", "man_days")


def period_of(period: str | None = None, start=None, end=None, today=None) -> tuple:
    today = getdate(today or nowdate())
    if start and end:
        return getdate(start), getdate(end)
    weeks = PERIODS.get(period or "4w", 4)
    return monday(today) - timedelta(days=7 * (weeks - 1)), today


def _blank() -> dict:
    return dict.fromkeys(KEYS, 0)


def pairs(first, last, users=None, projects=None) -> dict:
    """{(user, project): figures} of the period."""
    params = {"first": first, "last": last, "roles": (C.ACCOUNTABLE, C.RESPONSIBLE), "done": C.COMPLETED,
              "closed": (C.COMPLETED, C.CANCELLED), "states": (*C.LIVE_STATES, C.DONE)}
    narrow = ""
    if users is not None:
        if not users:
            return {}
        narrow += " and a.user in %(users)s"
        params["users"] = tuple(users)
    if projects is not None:
        if not projects:
            return {}
        narrow += " and t.project in %(projects)s"
        params["projects"] = tuple(projects)
    out = {}
    for row in frappe.db.sql(f"""
            select a.user, t.project,
                   count(distinct case when t.status = %(done)s and t.act_end_date between %(first)s and %(last)s
                                       then t.name end) as done,
                   count(distinct case when t.status = %(done)s and t.act_end_date between %(first)s and %(last)s
                                        and date(t.act_end_date) <= date(t.exp_end_date) then t.name end) as on_time,
                   count(distinct case when t.status not in %(closed)s and date(t.exp_end_date) < %(last)s
                                       then t.name end) as open_late
            from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task join `tabProject` p on p.name = t.project
            where ifnull(a.user, '') != '' and a.raci in %(roles)s and a.state in %(states)s and t.is_group = 0
              and p.pm_is_template = 0{narrow}
            group by a.user, t.project""", params, as_dict=True):
        figures = _blank()
        figures.update(done=cint(row.done), on_time=cint(row.on_time), open_late=cint(row.open_late))
        figures["late_done"] = figures["done"] - figures["on_time"]
        out[(row.user, row.project)] = figures
    for row in frappe.db.sql(f"""
            select a.user, t.project, sum(datediff(t.act_end_date, t.exp_end_date)) as delay
            from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
            where ifnull(a.user, '') != '' and a.raci in %(roles)s and a.state in %(states)s and t.is_group = 0
              and t.status = %(done)s and t.act_end_date between %(first)s and %(last)s
              and date(t.act_end_date) > date(t.exp_end_date){narrow}
            group by a.user, t.project""", params, as_dict=True):
        out.setdefault((row.user, row.project), _blank())["delay_days"] = cint(row.delay)
    report_narrow = narrow.replace("a.user", "e.reporter").replace("t.project", "e.project")
    for row in frappe.db.sql(f"""
            select e.reporter as user, e.project, count(*) as reports, sum(ifnull(e.man_days, 0)) as man_days
            from `tabPM Progress Entry` e where e.entry_date between %(first)s and %(last)s{report_narrow}
            group by e.reporter, e.project""", params, as_dict=True):
        figures = out.setdefault((row.user, row.project), _blank())
        figures["reports"] = cint(row.reports)
        figures["man_days"] = flt(row.man_days, 2)
    return out


def _add(target: dict, figures: dict) -> None:
    for key in KEYS:
        target[key] = target.get(key, 0) + figures.get(key, 0)


def _rates(figures: dict) -> dict:
    done = figures.get("done", 0)
    late = figures.get("late_done", 0)
    return {**figures, "on_time_rate": round(figures.get("on_time", 0) / done, 3) if done else None,
            "avg_delay": round(figures.get("delay_days", 0) / late, 1) if late else None}


def productivity(first, last, seen) -> list:
    """The layers' rows (crew, unit, quantity, man-days), within what the viewer may see."""
    rows = []
    for path in frappe.get_hooks("pm_productivity") or []:
        rows.extend(frappe.get_attr(path)(first, last) or [])
    out = []
    for row in rows:
        if seen.all or row.get("project") in seen.projects or (row.get("team") in seen.get("led", set())
                                                              and project_in(seen.read, row.get("project"))):
            out.append(row)
    return out


def overview(period: str | None = None, start=None, end=None, project: str | None = None, team: str | None = None) -> dict:
    first, last = period_of(period, start, end)
    seen = scope()
    people = visible_people(seen)
    if team:
        members = set(frappe.get_all("PM Team Member", filters={"parent": team, "parenttype": "PM Team"}, pluck="user"))
        people = members if people is None else people & members
    found = pairs(first, last, people, [project] if project else None)
    by_user, by_project = {}, {}
    for (user, proj), figures in found.items():
        if not may_see_pair(seen, user, proj):
            continue
        _add(by_user.setdefault(user, _blank()), figures)
        _add(by_project.setdefault(proj, _blank()), figures)
    names = dict(frappe.get_all("User", filters={"name": ["in", list(by_user) or [""]]}, fields=["name", "full_name"],
                                as_list=True))
    labels = dict(frappe.get_all("Project", filters={"name": ["in", list(by_project) or [""]]},
                                 fields=["name", "project_name"], as_list=True))
    people_rows = sorted(({"user": u, "full_name": names.get(u) or u, **_rates(f)} for u, f in by_user.items()),
                         key=lambda r: (-(r["done"] + r["open_late"]), r["full_name"].lower()))
    project_rows = sorted(({"project": p, "project_name": labels.get(p) or p, **_rates(f)} for p, f in by_project.items()),
                          key=lambda r: r["project_name"])
    total = _blank()
    for figures in by_user.values():
        _add(total, figures)
    return {"first": first.isoformat(), "last": last.isoformat(), "people": people_rows, "projects": project_rows,
            "crews": _crews(productivity(first, last, seen)), "total": _rates(total),
            "scope": {"all": seen.all, "projects": sorted(seen.projects), "teams": sorted(seen.get("led", set()))}}


def _crews(rows) -> list:
    """Crew rows summed per crew and unit (quantity per man-day)."""
    out = {}
    for row in rows:
        key = (row.get("team"), row.get("uom"))
        entry = out.setdefault(key, {"team": row.get("team"), "team_name": row.get("team_name") or row.get("team"),
                                     "uom": row.get("uom"), "qty": 0.0, "man_days": 0.0, "works": set()})
        entry["qty"] += flt(row.get("qty"))
        entry["man_days"] += flt(row.get("man_days"))
        if row.get("task"):
            entry["works"].add(row["task"])
    rows = []
    for entry in out.values():
        entry["works"] = len(entry["works"])
        entry["per_man_day"] = round(entry["qty"] / entry["man_days"], 3) if entry["man_days"] else None
        entry["qty"], entry["man_days"] = round(entry["qty"], 3), round(entry["man_days"], 2)
        rows.append(entry)
    return sorted(rows, key=lambda r: (r["team_name"] or "", r["uom"] or ""))


def person(user: str, period: str | None = None, start=None, end=None) -> dict:
    """One person: per project figures, their late and finished work, the trend of the last weeks."""
    first, last = period_of(period, start, end)
    seen = scope()
    people = visible_people(seen)
    if people is not None and user not in people:
        frappe.throw(_("Bạn không xem được hiệu suất của người này"), frappe.PermissionError)
    found = {k: v for k, v in pairs(first, last, {user}).items() if may_see_pair(seen, user, k[1])}
    labels = dict(frappe.get_all("Project", filters={"name": ["in", [p for _u, p in found] or [""]]},
                                 fields=["name", "project_name"], as_list=True))
    projects = [{"project": p, "project_name": labels.get(p) or p, **_rates(f)} for (_u, p), f in found.items()]
    allowed = [p for _u, p in found]
    tasks = frappe.db.sql("""select distinct t.name, t.subject, t.pm_wbs_code, t.project, t.exp_end_date, t.act_end_date,
                                    t.status, t.progress
                             from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
                             where a.user = %(user)s and a.raci in %(roles)s and t.is_group = 0 and t.project in %(projects)s
                               and ((t.status = %(done)s and t.act_end_date between %(first)s and %(last)s)
                                    or (t.status not in %(closed)s and date(t.exp_end_date) < %(last)s))
                             order by t.exp_end_date asc limit 200""",
                          {"user": user, "roles": (C.ACCOUNTABLE, C.RESPONSIBLE), "projects": tuple(allowed) or ("",),
                           "done": C.COMPLETED, "closed": (C.COMPLETED, C.CANCELLED), "first": first, "last": last},
                          as_dict=True)
    for task in tasks:
        task["project_name"] = labels.get(task.project)
        task["late"] = bool(task.exp_end_date and (task.act_end_date or last) and
                            getdate(task.act_end_date or last) > getdate(task.exp_end_date))
    total = _blank()
    for figures in found.values():
        _add(total, figures)
    return {"user": user, "full_name": frappe.db.get_value("User", user, "full_name") or user, "first": first.isoformat(),
            "last": last.isoformat(), "total": _rates(total), "projects": projects, "tasks": tasks,
            "trend": trend("Người", user, seen)}


def trend(kind: str, subject: str, seen, weeks: int = 12) -> list:
    """The kept weeks of a person (or crew), within the projects the viewer may see."""
    since = monday(nowdate()) - timedelta(days=7 * weeks)
    out = {}
    for row in frappe.get_all("PM Performance Snapshot", filters={"kind": kind, "subject": subject,
                                                                  "week_start": [">=", since]},
                              fields=["week_start", "project", *("tasks_done", "on_time", "open_late", "delay_days")],
                              order_by="week_start asc", limit_page_length=0):
        if kind == "Người" and not may_see_pair(seen, subject, row.project):
            continue
        week = out.setdefault(str(row.week_start), {"week": str(row.week_start), "done": 0, "on_time": 0, "open_late": 0})
        week["done"] += cint(row.tasks_done)
        week["on_time"] += cint(row.on_time)
        week["open_late"] += cint(row.open_late)
    return list(out.values())


# --- the weekly snapshot ---------------------------------------------------------------------------------------------------

def snapshot_week(week_start=None) -> int:
    """Keep the figures of one week (the last one by default): per person and project, per project, per crew."""
    week = monday(week_start) if week_start else monday(nowdate()) - timedelta(days=7)
    last = week + timedelta(days=6)
    found = pairs(week, last)
    rows = []
    per_project = {}
    for (user, project), figures in found.items():
        rows.append(("Người", user, project, figures, None))
        _add(per_project.setdefault(project, _blank()), figures)
    for project, figures in per_project.items():
        rows.append(("Dự án", project, project, figures, None))
    crews = {}
    for row in productivity(week, last, frappe._dict(all=True, projects=set(), read=None)):
        entry = crews.setdefault((row.get("team"), row.get("project")), {})
        unit = entry.setdefault(row.get("uom") or "", [0.0, 0.0])
        unit[0] += flt(row.get("qty"))
        unit[1] += flt(row.get("man_days"))
    for (team, project), units in crews.items():
        rows.append(("Đội", team, project, _blank() | {"man_days": sum(u[1] for u in units.values())}, units))
    written = 0
    for kind, subject, project, figures, units in rows:
        values = {"tasks_done": figures["done"], "on_time": figures["on_time"], "open_late": figures["open_late"],
                  "delay_days": figures["delay_days"], "progress_reports": figures["reports"],
                  "man_days": figures["man_days"], "productivity": json.dumps(units, ensure_ascii=False) if units else None}
        name = frappe.db.get_value("PM Performance Snapshot", {"week_start": week, "kind": kind, "subject": subject,
                                                               "project": project}, "name")
        if name:
            frappe.db.set_value("PM Performance Snapshot", name, values, update_modified=False)
        else:
            frappe.get_doc({"doctype": "PM Performance Snapshot", "week_start": week, "kind": kind, "subject": subject,
                            "project": project, **values}).insert(ignore_permissions=True)
            written += 1
    frappe.db.commit()
    return written
