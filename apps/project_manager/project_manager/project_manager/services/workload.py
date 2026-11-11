"""Khối lượng công việc (workload) of people, week by week, against what they can give (capacity).

* Capacity: one person-day on each working day of the company's calendar (its Holiday List), less the periods of
  PM Resource Capacity (leave 0 %, part time 50 %...).
* Demand: each open leaf task of a running project takes, on each of its working days, its load (Task.pm_load_pct,
  100 % when empty or 0) shared out among the people doing it (Thực hiện); with nobody doing it, the accountable person
  carries it. A task already late puts what is left of it (1 − progress, in working days) on the days from today.
* Utilization = demand / capacity per week; above OVERLOAD (120 %) a person is overloaded (alert "Quá tải công việc"),
  above BUSY (80 %) busy. A person overloaded by the work of two or more projects is a conflict between projects;
  the industry layers add theirs (hook pm_conflicts: machines booked twice...).
* Who sees whose workload: themselves, the leaders of their teams, those with perf.view_project in a project they
  work on (the load of the other projects shows as "Dự án khác"), those with perf.view_all.
"""

import math
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import get_access, has_capability, project_in
from project_manager.project_manager.services import workdays

OVERLOAD, BUSY = 1.2, 0.8
MAX_WEEKS = 12
LIVE = ("Chuẩn bị", "Đang thực hiện")
OTHER = "Dự án khác"
SPA = "/pm/khoi-luong-cong-viec"


def monday(day):
    day = getdate(day)
    return day - timedelta(days=day.weekday())


def company_calendar():
    company = frappe.defaults.get_global_default("company")
    name = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
    memo = getattr(frappe.local, "pm_calendars", None)
    if memo is None:
        memo = frappe.local.pm_calendars = {}
    key = f"company:{name}"
    if key not in memo:
        rows = frappe.get_all("Holiday", filters={"parent": name, "parenttype": "Holiday List"},
                              fields=["holiday_date", "weekly_off"], limit_page_length=0) if name else []
        memo[key] = workdays.WorkCalendar((r.holiday_date for r in rows), workdays._weekly_off(rows))
    return memo[key]


def _days(first, last):
    day, one = getdate(first), timedelta(days=1)
    while day <= getdate(last):
        yield day
        day += one


# --- capacity and demand ------------------------------------------------------------------------------------------------

def capacity(users, first, last) -> dict:
    """{user: {day: share of a person-day}} on the working days of the period."""
    calendar = company_calendar()
    working = [d for d in _days(first, last) if calendar.is_working(d)]
    out = {user: {day: 1.0 for day in working} for user in users}
    if not users:
        return out
    for row in frappe.get_all("PM Resource Capacity", filters={"user": ["in", list(users)], "from_date": ["<=", last],
                                                               "to_date": [">=", first]},
                              fields=["user", "from_date", "to_date", "capacity_pct"], limit_page_length=0):
        for day in _days(max(getdate(row.from_date), getdate(first)), min(getdate(row.to_date), getdate(last))):
            if day in out[row.user]:
                out[row.user][day] = min(out[row.user][day], flt(row.capacity_pct) / 100)
    return out


def assignments(users=None) -> list:
    """Live person assignments (accountable or doing) on the open leaf tasks of running projects. With `users`: every
    holder of the tasks these people hold (who carries a task depends on all of them)."""
    params = {"live": LIVE, "states": C.LIVE_STATES, "roles": (C.ACCOUNTABLE, C.RESPONSIBLE),
              "closed": (C.COMPLETED, C.CANCELLED)}
    narrow = ""
    if users is not None:
        if not users:
            return []
        narrow = """ and a.task in (select b.task from `tabPM Task Assignment` b where b.user in %(users)s
                                    and b.is_active = 1 and b.state in %(states)s and b.raci in %(roles)s)"""
        params["users"] = tuple(users)
    return frappe.db.sql(f"""select a.user, a.raci, t.name as task, t.project, t.subject, t.pm_wbs_code, t.exp_start_date,
                                    t.exp_end_date, t.progress, t.pm_load_pct, p.project_name
                             from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
                             join `tabProject` p on p.name = t.project
                             where a.is_active = 1 and a.state in %(states)s and ifnull(a.user, '') != ''
                               and a.raci in %(roles)s and t.is_group = 0 and t.status not in %(closed)s
                               and t.exp_start_date is not null and t.exp_end_date is not null
                               and p.pm_is_template = 0 and ifnull(p.pm_state, 'Chuẩn bị') in %(live)s{narrow}""",
                         params, as_dict=True)


def loads(rows, first, last, today=None) -> dict:
    """{user: {day: [(task row, share)]}} of the period."""
    today = getdate(today or nowdate())
    calendar = company_calendar()
    by_task = {}
    for row in rows:
        by_task.setdefault(row.task, []).append(row)
    out = {}
    for task, holders in by_task.items():
        doing = [h for h in holders if h.raci == C.RESPONSIBLE]
        carriers = doing or [h for h in holders if h.raci == C.ACCOUNTABLE]
        info = holders[0]
        load = (flt(info.pm_load_pct) or 100) / 100  # empty (0): the whole day
        if not carriers:
            continue
        start, end = getdate(info.exp_start_date), getdate(info.exp_end_date)
        if end < today:  # late: what is left of it, from today
            length = max(1, calendar.count(start, end))
            left = max(1, math.ceil((1 - flt(info.progress) / 100) * length))
            begin = calendar.index(today)
            days = [calendar.date_at(begin + k) for k in range(left)]
        else:
            days = [d for d in _days(max(start, getdate(first)), min(end, getdate(last))) if calendar.is_working(d)]
        share = load / len({c.user for c in carriers})
        for day in days:
            if getdate(first) <= day <= getdate(last):
                for user in {c.user for c in carriers}:
                    out.setdefault(user, {}).setdefault(day, []).append((info, share))
    return out


def level(utilization: float) -> str:
    return "Quá tải" if utilization > OVERLOAD else "Bận" if utilization > BUSY else "Vừa sức" if utilization > 0 else "Rảnh"


# --- who may see whom -----------------------------------------------------------------------------------------------------

def scope(viewer: str | None = None) -> frappe._dict:
    """What a viewer may see of other people's work: everything; the people of the teams they lead (in the projects
    they can read); everyone's work in the projects where they hold perf.view_project."""
    from project_manager.project_manager.policy import capabilities_in

    viewer = viewer or frappe.session.user
    access = get_access(viewer)
    if access.kind == "admin" or has_capability("perf.view_all", user=viewer):
        return frappe._dict(all=True, people=set(), projects=set(), read=None)
    led = frappe.get_all("PM Team", filters={"leader": viewer, "is_active": 1}, pluck="name")
    people = {viewer} | set(frappe.get_all("PM Team Member", filters={"parent": ["in", led or [""]],
                                                                      "parenttype": "PM Team"}, pluck="user"))
    member_of = set(frappe.get_all("PM Project Member", filters={"user": viewer, "is_active": 1}, pluck="project"))
    projects = {p for p in (member_of | (access.read or set())) if "perf.view_project" in capabilities_in(p, viewer)}
    return frappe._dict(all=False, people={p for p in people if p}, projects=projects, read=access.read, led=set(led))


def may_see_pair(seen, user: str, project: str) -> bool:
    """May the viewer see this person's work in this project?"""
    if seen.all:
        return True
    if project in seen.projects:
        return True
    return user in seen.people and project_in(seen.read, project)


def visible_people(seen) -> set | None:
    """The people whose rows the viewer gets (None: everyone with work)."""
    if seen.all:
        return None
    members = set(frappe.get_all("PM Project Member", filters={"project": ["in", list(seen.projects) or [""]],
                                                               "is_active": 1}, pluck="user"))
    return seen.people | members


# --- the screens -----------------------------------------------------------------------------------------------------------

def overview(start=None, weeks: int = 6, team: str | None = None, project: str | None = None, today=None) -> dict:
    today = getdate(today or nowdate())
    weeks = max(1, min(cint(weeks) or 6, MAX_WEEKS))
    first = monday(start or today)
    last = first + timedelta(days=7 * weeks - 1)
    seen = scope()
    people = visible_people(seen)
    if team:
        people_in = set(frappe.get_all("PM Team Member", filters={"parent": team, "parenttype": "PM Team"}, pluck="user"))
        people = people_in if people is None else people & people_in
    if project:
        if not project_in(get_access().read, project):
            frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)
        in_project = set(frappe.get_all("PM Project Member", filters={"project": project, "is_active": 1}, pluck="user"))
        people = in_project if people is None else people & in_project
    rows = assignments(people)
    found = loads(rows, first, last, today)
    if people is not None:  # the other holders of these tasks only shared the load out
        found = {u: days for u, days in found.items() if u in people}
    users = set(found) | (people or set())
    users = {u for u in users if u and u not in ("Administrator", "Guest")}
    caps = capacity(users, first, last)
    names = dict(frappe.get_all("User", filters={"name": ["in", list(users) or [""]]}, fields=["name", "full_name"],
                                as_list=True))
    mondays = [first + timedelta(days=7 * k) for k in range(weeks)]
    out = []
    for user in sorted(users, key=lambda u: (names.get(u) or u).lower()):
        cells = []
        for week in mondays:
            days = [week + timedelta(days=k) for k in range(7)]
            cap = sum(caps.get(user, {}).get(d, 0) for d in days)
            demand, projects = 0.0, {}
            for day in days:
                for info, share in found.get(user, {}).get(day, []):
                    demand += share
                    key = info.project if may_see_pair(seen, user, info.project) else OTHER
                    projects[key] = projects.get(key, 0) + share
            utilization = demand / cap if cap else (9.99 if demand else 0)
            cells.append({"week": week.isoformat(), "capacity": round(cap, 2), "demand": round(demand, 2),
                          "utilization": round(utilization, 2), "level": level(utilization),
                          "projects": {k: round(v, 2) for k, v in projects.items()}})
        out.append({"user": user, "full_name": names.get(user) or user, "weeks": cells,
                    "peak": max((c["utilization"] for c in cells), default=0)})
    labels = dict(frappe.get_all("Project", filters={"name": ["in", list({r.project for r in rows}) or [""]]},
                                 fields=["name", "project_name"], as_list=True))
    return {"weeks": [m.isoformat() for m in mondays], "rows": out, "projects": labels,
            "conflicts": conflicts(out, first, last, seen), "thresholds": {"busy": BUSY, "overload": OVERLOAD},
            "can": {"capacity": may_set_capacity(), "all": seen.all}}


def cell(user: str, week) -> dict:
    """The tasks behind one person's week (those the viewer may see by name)."""
    seen = scope()
    people = visible_people(seen)
    if people is not None and user not in people:
        frappe.throw(_("Bạn không xem được khối lượng công việc của người này"), frappe.PermissionError)
    first = monday(week)
    last = first + timedelta(days=6)
    found = loads(assignments({user}), first, last).get(user, {})
    tasks, hidden = {}, 0.0
    for day in sorted(found):
        for info, share in found[day]:
            if not may_see_pair(seen, user, info.project):
                hidden += share
                continue
            entry = tasks.setdefault(info.task, {"task": info.task, "label": f"{info.pm_wbs_code or ''} {info.subject}".strip(),
                                                 "project": info.project, "project_name": info.project_name,
                                                 "raci": info.raci, "start": info.exp_start_date, "end": info.exp_end_date,
                                                 "progress": info.progress, "days": 0.0})
            entry["days"] += share
    caps = capacity({user}, first, last).get(user, {})
    periods = frappe.get_all("PM Resource Capacity", filters={"user": user, "from_date": ["<=", last], "to_date": [">=", first]},
                             fields=["name", "from_date", "to_date", "capacity_pct", "reason", "note"])
    return {"user": user, "full_name": frappe.db.get_value("User", user, "full_name") or user, "week": first.isoformat(),
            "capacity": round(sum(caps.values()), 2),
            "tasks": sorted(({**t, "days": round(t["days"], 2)} for t in tasks.values()), key=lambda t: -t["days"]),
            "other": round(hidden, 2), "periods": periods}


def conflicts(rows, first, last, seen=None) -> list:
    """People overloaded by the work of several projects, then what the layers report (hook pm_conflicts), kept when
    the viewer reads one of the projects at least (the others show as "Dự án khác")."""
    out = []
    for row in rows:
        for week in row["weeks"]:
            if week["utilization"] > OVERLOAD and len(week["projects"]) >= 2:
                out.append({"kind": "Người", "subject": row["full_name"], "user": row["user"], "week": week["week"],
                            "utilization": week["utilization"], "projects": week["projects"]})
    read = None if seen is None or seen.all else seen.read
    for path in frappe.get_hooks("pm_conflicts") or []:
        for entry in frappe.get_attr(path)(first, last) or []:
            projects = entry.get("projects") or {}
            known = {p: v for p, v in projects.items() if project_in(read, p)}
            if not known:
                continue
            hidden = sum(v for p, v in projects.items() if p not in known)
            out.append({**entry, "projects": {**known, **({OTHER: hidden} if hidden else {})}})
    out.sort(key=lambda c: (c["week"], c["kind"], c["subject"]))
    return out


# --- capacity periods ---------------------------------------------------------------------------------------------------------

def may_set_capacity(user: str | None = None) -> bool:
    return has_capability("users.manage", "perf.view_all", user=user)


def save_capacity(user: str, from_date, to_date, capacity_pct, reason: str = "Nghỉ phép", note: str = "", name=None) -> dict:
    if not may_set_capacity():
        frappe.throw(_("Chỉ quản trị hoặc người xem được hiệu suất của mọi người mới ghi được kỳ nghỉ, bán thời gian"),
                     frappe.PermissionError)
    values = {"user": user, "from_date": from_date, "to_date": to_date, "capacity_pct": flt(capacity_pct),
              "reason": reason, "note": (note or "").strip() or None, "set_by": frappe.session.user}
    if name:
        doc = frappe.get_doc("PM Resource Capacity", name)
        doc.update(values)
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "PM Resource Capacity", **values}).insert(ignore_permissions=True)
    return doc.as_dict()


def delete_capacity(name) -> dict:
    if not may_set_capacity():
        frappe.throw(_("Bạn không xóa được kỳ này"), frappe.PermissionError)
    frappe.delete_doc("PM Resource Capacity", name, ignore_permissions=True)
    return {"deleted": name}


# --- alert type "Quá tải công việc" (core) ----------------------------------------------------------------------------------

def overloaded(rule, today):
    """This week and the next: each person above OVERLOAD. The person and the managers of the projects behind the load
    are told (one episode per person and week)."""
    from project_manager.project_manager.services import alerts

    today = getdate(today)
    first = monday(today)
    last = first + timedelta(days=13)
    rows = assignments()
    found = loads(rows, first, last, today)
    caps = capacity(set(found), first, last)
    managers = dict(frappe.get_all("Project", filters={"name": ["in", list({r.project for r in rows}) or [""]]},
                                   fields=["name", "pm_manager"], as_list=True))
    hits = []
    for user, days in found.items():
        for week in (first, first + timedelta(days=7)):
            span = [week + timedelta(days=k) for k in range(7)]
            cap = sum(caps.get(user, {}).get(d, 0) for d in span)
            demand = sum(share for d in span for _info, share in days.get(d, []))
            if demand and demand > OVERLOAD * cap:
                projects = {info.project for d in span for info, _s in days.get(d, [])}
                name = frappe.db.get_value("User", user, "full_name") or user
                text = _("Quá tải công việc tuần {0}: {1} cần {2} ngày công, có {3} ({4} dự án)").format(
                    week.strftime("%d/%m"), name, round(demand, 1), round(cap, 1), len(projects))
                hits.append(alerts._hit("User", user, None, None, week.isoformat(), text,
                                        direct=[user, *{managers.get(p) for p in projects} - {None}]))
    return hits
