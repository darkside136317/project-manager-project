"""Danh mục dự án (portfolio): every running project the user may read, on one screen.

v1 (M7), for each project: health and why, progress against the plan, SPI, the forecast end against the target (main
baseline, else the contract), the current phase, open alerts, late work. Totals by health on top.
v2 (M9) adds: the share of work finished on time over the last 4 weeks, the members overloaded this week, the trend of
the progress over the last 8 weeks (daily snapshots), and the columns of the industry layers (hook
pm_portfolio_columns: the construction layer adds the cost against the value of the work done, the materials over
their norm).
"""

from datetime import timedelta

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import get_access, has_capability
from project_manager.project_manager.services import baseline, rollup, schedule, workload
from project_manager.project_manager.services import performance as perf

LIVE = ("Chuẩn bị", "Đang thực hiện", "Tạm dừng")
FIELDS = ["name", "project_name", "pm_code", "pm_state", "percent_complete", "expected_start_date", "expected_end_date",
          "pm_manager", "pm_spi", "pm_forecast_end", "pm_health", "pm_health_reason", "pm_current_phase",
          "pm_primary_baseline"]
HEALTH_ORDER = {"Đỏ": 0, "Vàng": 1, "Xanh": 2}
MAX_PROJECTS = 300


def portfolio(state: str | None = None, health: str | None = None) -> dict:
    filters = {"pm_is_template": 0, "pm_state": state if state else ["in", LIVE]}
    if health:
        filters["pm_health"] = health
    rows = frappe.get_list("Project", filters=filters, fields=FIELDS, order_by="project_name asc",
                           limit_page_length=MAX_PROJECTS)
    names = [r.name for r in rows]
    late, alerts, phases, managers = {}, {}, {}, {}
    if names:
        late = dict(frappe.db.sql(f"""select project, count(*) from `tabTask` where project in %(n)s and is_group = 0
                                      and pm_is_overdue = 1 and status not in ('{C.COMPLETED}', '{C.CANCELLED}')
                                      group by project""", {"n": tuple(names)}))
        alerts = dict(frappe.db.sql("""select project, count(*) from `tabPM Alert` where project in %(n)s
                                       and state = 'Đang mở' group by project""", {"n": tuple(names)}))
        current = [r.pm_current_phase for r in rows if r.pm_current_phase]
        if current:
            phases = {t.name: t for t in frappe.get_all(
                "Task", filters={"name": ["in", current]}, fields=["name", "subject", "pm_wbs_code", "pm_gate_state"])}
        people = {r.pm_manager for r in rows if r.pm_manager}
        if people:
            managers = dict(frappe.get_all("User", filters={"name": ["in", list(people)]},
                                           fields=["name", "full_name"], as_list=True))
    today = nowdate()
    on_time = _on_time(names)
    overloaded = _overloaded(names)
    trends = _trends(names)
    extra = {}
    for path in frappe.get_hooks("pm_portfolio_columns") or []:
        for project, values in (frappe.get_attr(path)(names) or {}).items():
            extra.setdefault(project, {}).update(values)
    ends = schedule.targets(rows)
    curves = baseline.curves_of(rows)
    totals = {"Đỏ": 0, "Vàng": 0, "Xanh": 0, "": 0}
    for row in rows:
        points = curves.get(row.name)
        row["planned_progress"] = flt(baseline.interpolate(points, today) if points else rollup.planned_progress(
            row.expected_start_date, row.expected_end_date), 1)
        row["target_end"] = ends[row.name]["target_end"]
        row["forecast_slip"] = ends[row.name]["forecast_slip"]
        phase = phases.get(row.pm_current_phase)
        row["phase"] = f"{phase.pm_wbs_code or ''} {phase.subject}".strip() if phase else None
        row["phase_waiting"] = bool(phase and phase.pm_gate_state == "Chờ duyệt")
        row["alerts_open"] = cint(alerts.get(row.name))
        row["late"] = cint(late.get(row.name))
        row["manager_name"] = managers.get(row.pm_manager)
        row["on_time_rate"] = on_time.get(row.name)
        row["overloaded"] = overloaded.get(row.name, 0)
        row["trend"] = trends.get(row.name, [])
        row["extra"] = extra.get(row.name, {})
        totals[row.pm_health or ""] = totals.get(row.pm_health or "", 0) + 1
    rows.sort(key=lambda r: (HEALTH_ORDER.get(r.pm_health, 3), -cint(r.alerts_open), r.project_name or ""))
    return {"rows": rows, "totals": totals, "alerts_open": sum(cint(r.alerts_open) for r in rows),
            "all_projects": get_access().read is None, "can_view_all": has_capability("portfolio.view_all"),
            "truncated": len(rows) >= MAX_PROJECTS}


def _on_time(projects) -> dict:
    """{project: share of the leaf tasks finished in the last 4 weeks that were on time}."""
    if not projects:
        return {}
    first, last = perf.period_of("4w")
    rows = frappe.db.sql("""select project, count(*) as done, sum(date(act_end_date) <= date(exp_end_date)) as on_time
                            from `tabTask` where project in %(p)s and is_group = 0 and status = 'Completed'
                              and act_end_date between %(first)s and %(last)s group by project""",
                         {"p": tuple(projects), "first": first, "last": last}, as_dict=True)
    return {r.project: round(cint(r.on_time) / cint(r.done), 3) for r in rows if cint(r.done)}


def _overloaded(projects) -> dict:
    """{project: members overloaded this week (by all their work)}."""
    if not projects:
        return {}
    members = frappe.get_all("PM Project Member", filters={"project": ["in", projects], "is_active": 1},
                             fields=["project", "user"], limit_page_length=0)
    users = {m.user for m in members}
    first = workload.monday(nowdate())
    last = first + timedelta(days=6)
    found = {u: days for u, days in workload.loads(workload.assignments(users), first, last).items() if u in users}
    caps = workload.capacity(users, first, last)
    over = {u for u, days in found.items()
            if sum(s for d in days.values() for _i, s in d) > workload.OVERLOAD * sum(caps.get(u, {}).values())}
    out = {}
    for member in members:
        if member.user in over:
            out[member.project] = out.get(member.project, 0) + 1
    return out


def _trends(projects, points: int = 8) -> dict:
    """{project: [progress at the end of each of the last weeks]} from the daily snapshots."""
    if not projects:
        return {}
    since = getdate(nowdate()) - timedelta(days=7 * points)
    out = {}
    for row in frappe.get_all("PM Snapshot", filters={"project": ["in", projects], "task": ["is", "not set"],
                                                      "snapshot_date": [">=", since]},
                              fields=["project", "snapshot_date", "progress"], order_by="snapshot_date asc",
                              limit_page_length=0):
        week = workload.monday(row.snapshot_date).isoformat()
        series = out.setdefault(row.project, {})
        series[week] = round(flt(row.progress), 1)  # the last day of each week wins
    return {p: list(series.values())[-points:] for p, series in out.items()}

