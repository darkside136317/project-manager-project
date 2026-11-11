"""Danh mục dự án (portfolio) v1: every running project the user may read, on one screen.

For each: health and why, progress against the plan, SPI, the forecast end against the target (main baseline, else the
contract), the current phase, open alerts, late work. Totals by health on top. The portfolio v2 of M9 adds
resources and performance.
"""

import frappe
from frappe.utils import cint, flt, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import get_access, has_capability
from project_manager.project_manager.services import baseline, rollup, schedule

LIVE = ("Chuẩn bị", "Đang thực hiện", "Tạm dừng")
FIELDS = ["name", "project_name", "pm_code", "pm_state", "percent_complete", "expected_start_date", "expected_end_date",
          "pm_manager", "pm_spi", "pm_forecast_end", "pm_health", "pm_health_reason", "pm_current_phase"]
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
    totals = {"Đỏ": 0, "Vàng": 0, "Xanh": 0, "": 0}
    for row in rows:
        summary = schedule.summary(row.name)
        row["planned_progress"] = flt(baseline.planned_on(row.name, today, rollup.planned_progress(
            row.expected_start_date, row.expected_end_date)), 1)
        row["target_end"] = summary["baseline_end"] or summary["contract_end"]
        row["forecast_slip"] = summary["forecast_slip"]
        phase = phases.get(row.pm_current_phase)
        row["phase"] = f"{phase.pm_wbs_code or ''} {phase.subject}".strip() if phase else None
        row["phase_waiting"] = bool(phase and phase.pm_gate_state == "Chờ duyệt")
        row["alerts_open"] = cint(alerts.get(row.name))
        row["late"] = cint(late.get(row.name))
        row["manager_name"] = managers.get(row.pm_manager)
        totals[row.pm_health or ""] = totals.get(row.pm_health or "", 0) + 1
    rows.sort(key=lambda r: (HEALTH_ORDER.get(r.pm_health, 3), -cint(r.alerts_open), r.project_name or ""))
    return {"rows": rows, "totals": totals, "alerts_open": sum(cint(r.alerts_open) for r in rows),
            "all_projects": get_access().read is None, "can_view_all": has_capability("portfolio.view_all"),
            "truncated": len(rows) >= MAX_PROJECTS}
