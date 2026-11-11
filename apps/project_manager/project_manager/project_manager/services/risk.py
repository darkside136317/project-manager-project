"""Sức khỏe (health) of tasks, groups and projects: Xanh / Vàng / Đỏ, read from the forecast of M4.

* An open leaf: its slip is the number of working days between its planned end and its forecast end.
  Đỏ when it slips more than max(red_slip_days, 10% of its duration), or its SPI is under 0.8 once a quarter of its
  time has passed, or it is on the critical path and slips at all. Vàng when it slips, or SPI is under 0.95, or it is
  stalled (started, no progress report for stalled_days). Xanh otherwise; a finished or cancelled task is Xanh.
* A group and the project: the same reading of their own forecast (against the planned end; the project against its
  main baseline, else its contract end) and SPI, and never better than their worst critical leaf: a late critical
  task delays everything after it.
* Worse shows at once; better only once it has held health_hold_days days in a row (the candidate and the day it was
  first seen are kept; every evaluation, nightly at the latest, checks them).

Computed right after the forecast (services/schedule.refresh), so it is as fresh as the forecast.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from project_manager.project_manager import constants as C

GREEN, YELLOW, RED = "Xanh", "Vàng", "Đỏ"
RANK = {"": -1, None: -1, GREEN: 0, YELLOW: 1, RED: 2}
SPI_RED, SPI_YELLOW, SPI_FROM_SHARE = 0.8, 0.95, 0.25
OPEN = (C.OPEN, C.WORKING, C.REVIEW, "Overdue", "Pending Review")


def settings() -> frappe._dict:
    single = frappe.get_cached_doc("PM Settings")
    return frappe._dict(red_days=cint(single.get("red_slip_days")) or 3, stalled_days=cint(single.get("stalled_days")) or 5,
                        hold_days=max(1, cint(single.get("health_hold_days")) or 3))


def classify(slip: int | None, duration: int, spi: float | None, critical: bool, stalled: bool, limits) -> tuple:
    """(level, reasons) of one task, group or project."""
    reasons = []
    level = GREEN
    red_slip = max(limits.red_days, round(0.1 * max(1, duration)))
    if slip is not None and slip > 0:
        if slip > red_slip or critical:
            level = RED
            reasons.append(_("dự báo trễ {0} ngày{1}").format(slip, _(", trên đường găng") if critical else ""))
        else:
            level = YELLOW
            reasons.append(_("dự báo trễ {0} ngày").format(slip))
    if spi is not None:
        if spi < SPI_RED:
            level = RED
            reasons.append(_("SPI {0}").format(f"{spi:.2f}"))
        elif spi < SPI_YELLOW:
            level = max(level, YELLOW, key=RANK.get)
            reasons.append(_("SPI {0}").format(f"{spi:.2f}"))
    if stalled:
        level = max(level, YELLOW, key=RANK.get)
        reasons.append(_("không cập nhật tiến độ"))
    return level, reasons


def settle(current, candidate, since, raw, today, hold_days) -> tuple:
    """(level shown, candidate, candidate since) after an evaluation that found `raw`."""
    if not current or RANK[raw] > RANK[current]:
        return raw, None, None  # first reading, or worse: at once
    if RANK[raw] == RANK[current]:
        return current, None, None
    if candidate == raw and since and (getdate(today) - getdate(since)).days >= hold_days - 1:
        return raw, None, None  # better, and it held long enough
    if candidate == raw and since:
        return current, candidate, since
    return current, raw, getdate(today)


def evaluate(project: str, net=None, plan: dict | None = None, forecast: dict | None = None, today=None) -> dict:
    """Health of every task of the project and of the project; writes what changed. Returns the project's."""
    from project_manager.project_manager.services import schedule

    today = getdate(today or nowdate())
    net = net or schedule.Network(project)
    limits = settings()
    calendar = net.calendar
    now = calendar.index(today, forward=False)
    for source in ((plan or {}).get("tasks", {}), (forecast or {}).get("tasks", {})):  # the figures just computed
        for name, values in source.items():
            if name in net.rows:
                net.rows[name].update(values)
    extra = {row.name: row for row in frappe.db.sql(
        """select name, pm_health, pm_health_candidate, pm_health_since, pm_last_progress_on, pm_health_reason,
                  pm_forecast_slip, pm_stalled
           from `tabTask` where project = %s""", project, as_dict=True)}
    stale_before = today - timedelta(days=limits.stalled_days)

    def figures(name, row):
        critical = cint(row.pm_is_critical)
        end = row.pm_forecast_end
        if row.status in (C.COMPLETED, C.CANCELLED) or not row.exp_end_date or not end:
            return None
        slip = calendar.index(end, forward=False) - calendar.index(row.exp_end_date, forward=False)
        span = net.span(row) if not row.is_group else _group_span(calendar, row)
        duration = span[1] if span else 1
        spi = None
        if span and not row.is_group:
            share = schedule._planned_share(calendar, span[0], span[1], now)
            if share >= SPI_FROM_SHARE:
                spi = round(flt(row.progress) / 100 / share, 2)
        info = extra.get(name) or frappe._dict()
        last = info.pm_last_progress_on
        stalled = (not row.is_group and 0 < flt(row.progress) < 100
                   and bool(last) and getdate(last) < stale_before)
        return frappe._dict(slip=slip, duration=duration, spi=spi, critical=bool(critical), stalled=stalled)

    raw, reasons, slips, stalls = {}, {}, {}, {}
    for name, row in net.rows.items():
        if row.is_group:
            continue
        found = figures(name, row)
        if found is None:
            raw[name], reasons[name], slips[name], stalls[name] = GREEN, [], 0, False
            continue
        raw[name], reasons[name] = classify(found.slip, found.duration, found.spi, found.critical, found.stalled, limits)
        slips[name], stalls[name] = max(0, found.slip), found.stalled
    worst_critical = _worst_critical_below(net, raw)
    for name, row in net.rows.items():
        if not row.is_group:
            continue
        found = figures(name, row)
        level, why = (GREEN, []) if found is None else classify(found.slip, found.duration, None, False, False, limits)
        child = worst_critical.get(name)
        if child and RANK[raw[child]] > RANK[level]:
            level = raw[child]
            why = [*why, _("việc găng {0}").format(net.rows[child].pm_wbs_code or net.rows[child].subject)]
        raw[name], reasons[name], slips[name], stalls[name] = level, why, max(0, found.slip) if found else 0, False

    updates = {}
    for name, level in raw.items():
        info = extra.get(name) or frappe._dict()
        shown, candidate, since = settle(info.pm_health, info.pm_health_candidate, info.pm_health_since, level, today,
                                         limits.hold_days)
        values = {"pm_health": shown, "pm_health_candidate": candidate,
                  "pm_health_since": since.isoformat() if since else None,
                  "pm_health_reason": "; ".join(reasons[name]) if shown == level else (info.pm_health_reason or None),
                  "pm_forecast_slip": slips[name], "pm_stalled": 1 if stalls[name] else 0}
        changed = {k: v for k, v in values.items() if _differs(info.get(k), v)}
        if changed:
            updates[name] = changed
    schedule._write_columns(updates)
    return _project(project, net, raw, forecast, limits, today)


def _group_span(calendar, row):
    if not (row.exp_start_date and row.exp_end_date):
        return None
    start = calendar.index(row.exp_start_date)
    return start, max(1, calendar.index(row.exp_end_date, forward=False) - start + 1)


def _worst_critical_below(net, raw: dict) -> dict:
    """{group: its worst open critical leaf} (any depth)."""
    out = {}
    for name, row in net.rows.items():
        if row.is_group or not cint(row.pm_is_critical) or row.status in (C.COMPLETED, C.CANCELLED):
            continue
        parent = row.parent_task
        while parent and parent in net.rows:
            best = out.get(parent)
            if best is None or RANK[raw[name]] > RANK[raw[best]]:
                out[parent] = name
            parent = net.rows[parent].parent_task
    return out


def _differs(old, new) -> bool:
    if isinstance(new, int) and not isinstance(new, bool):
        return cint(old) != new
    old = old.isoformat() if hasattr(old, "isoformat") else old
    return str(old or "") != str(new or "")


def _project(project, net, raw, forecast, limits, today) -> dict:
    from project_manager.project_manager.services import schedule

    info = frappe.db.get_value("Project", project, ["pm_health", "pm_health_candidate", "pm_health_since",
                                                    "pm_health_reason", "pm_forecast_end", "pm_spi"], as_dict=True)
    summary = schedule.summary(project)
    slip = summary["forecast_slip"]
    spi = flt((forecast or {}).get("spi", info.pm_spi)) or None
    duration = 1
    if summary.get("plan_end"):
        starts = [r.exp_start_date for r in net.rows.values() if r.exp_start_date]
        if starts:
            first = net.calendar.index(min(starts))
            duration = max(1, net.calendar.index(summary["plan_end"], forward=False) - first + 1)
    level, why = classify(slip, duration, spi if spi and spi > 0 else None, False, False, limits)
    critical = [name for name, row in net.rows.items()
                if not row.is_group and cint(row.pm_is_critical) and row.status not in (C.COMPLETED, C.CANCELLED)]
    worst = max(critical, key=lambda n: RANK[raw[n]], default=None)
    if worst and RANK[raw[worst]] > RANK[level]:
        level = raw[worst]
        why.append(_("việc găng {0}").format(net.rows[worst].pm_wbs_code or net.rows[worst].subject))
    shown, candidate, since = settle(info.pm_health, info.pm_health_candidate, info.pm_health_since, level, today,
                                     limits.hold_days)
    before = info.pm_health
    reason = "; ".join(why) if shown == level else info.pm_health_reason
    frappe.db.set_value("Project", project, {"pm_health": shown, "pm_health_candidate": candidate,
                                             "pm_health_since": since, "pm_health_reason": reason or None},
                        update_modified=False)
    if before and shown != before:
        from project_manager.project_manager.services import activity, alerts

        activity.record("Project", project, "Trạng thái", _("Sức khỏe dự án: {0} → {1}{2}").format(
            before, shown, f" ({reason})" if reason else ""))
        alerts.health_changed(project, before, shown, reason or "")
    return {"health": shown, "raw": level, "reason": reason, "changed": bool(before) and shown != before}
