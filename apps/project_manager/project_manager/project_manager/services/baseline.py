"""Baseline: a frozen copy of the plan, to compare the work against. A project can keep several; one is the main one.

A baseline is a header, one row per task and a curve, all written in a few statements whatever the size of the project.
The curve is the planned S-curve: every leaf spreads its weight evenly over its working days, and the running total is
kept at each week's end. It is the "kế hoạch" line from then on, in the overview and in the daily snapshots. Without a
baseline the plan is the straight line between the project's dates.
"""

from bisect import bisect_right

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import assert_project_capability, has_project_capability
from project_manager.project_manager.services import activity, schedule
from project_manager.project_manager.services.queries import reserve_ids
from project_manager.project_manager.services.workdays import calendar_of

MAX_COMPARE_ROWS = 500
TASK_FIELDS = ("name", "baseline", "project", "task", "is_group", "start_date", "end_date", "weight", "progress", "owner", "modified_by",
               "creation", "modified", "docstatus", "idx")
CURVE_FIELDS = ("name", "baseline", "project", "point_date", "planned_progress", "owner", "modified_by", "creation", "modified", "docstatus", "idx")


def curve_points(rows, calendar) -> list[tuple]:
    """[(date, cumulative planned %)] at each week's end, from leaves given as _dicts with start_date, end_date, weight."""
    spans = []
    total = 0.0
    for row in rows:
        weight = flt(row.weight)
        if row.is_group or weight <= 0 or not row.end_date:
            continue
        first = calendar.index(row.start_date or row.end_date)
        last = max(first, calendar.index(row.end_date, forward=False))
        spans.append((first, last, weight / (last - first + 1)))
        total += weight
    if not spans or total <= 0:
        return []
    begin = min(s[0] for s in spans)
    end = max(s[1] for s in spans)
    rate = [0.0] * (end - begin + 2)
    for first, last, per_day in spans:
        rate[first - begin] += per_day
        rate[last - begin + 1] -= per_day
    points, current, done = [], 0.0, 0.0
    for offset in range(end - begin + 1):
        current += rate[offset]
        done += current
        day = calendar.date_at(begin + offset)
        following = calendar.date_at(begin + offset + 1)
        if offset == 0 or offset == end - begin or day.isocalendar()[1] != following.isocalendar()[1]:
            points.append((day, min(100.0, round(done * 100 / total, 2))))
    return points


def capture(project: str, title: str = "", note: str = "") -> dict:
    """Freeze the plan as it stands. The first baseline of a project becomes its main one."""
    assert_project_capability(project, "plan.edit")
    frappe.db.sql("select name from `tabProject` where name = %s for update", project)
    rows = frappe.db.sql(
        """select name as task, is_group, exp_start_date as start_date, exp_end_date as end_date,
                  pm_rollup_weight as weight, progress
           from `tabTask` where project = %s and status != %s and exp_end_date is not null""",
        (project, C.CANCELLED), as_dict=True)
    if not [row for row in rows if not row.is_group]:
        frappe.throw(_("Chưa có công việc nào có ngày để chụp baseline"))
    number = cint(frappe.db.sql("select max(baseline_no) from `tabPM Baseline` where project = %s", project)[0][0]) + 1
    leaves = [row for row in rows if not row.is_group]
    first_baseline = number == 1 or not frappe.db.get_value("Project", project, "pm_primary_baseline")
    now, user = now_datetime(), frappe.session.user
    doc = frappe.get_doc({
        "doctype": "PM Baseline", "project": project, "baseline_no": number, "title": (title or "").strip() or _("Baseline {0}").format(number),
        "is_primary": 1 if first_baseline else 0, "taken_on": now, "taken_by": user, "note": (note or "").strip() or None,
        "start_date": min(getdate(row.start_date or row.end_date) for row in leaves),
        "end_date": max(getdate(row.end_date) for row in leaves),
        "task_count": len(leaves), "total_weight": sum(flt(row.weight) for row in leaves)})
    doc.insert(ignore_permissions=True)
    frappe.db.bulk_insert("PM Baseline Task", TASK_FIELDS, [
        (number, doc.name, project, row.task, cint(row.is_group), getdate(row.start_date) if row.start_date else None,
         getdate(row.end_date), flt(row.weight), flt(row.progress), user, user, now, now, 0, 0)
        for number, row in zip(reserve_ids("PM Baseline Task", len(rows)), rows)], chunk_size=500)
    points = curve_points(rows, calendar_of(project))
    frappe.db.bulk_insert("PM Baseline Curve", CURVE_FIELDS, [
        (number, doc.name, project, day, value, user, user, now, now, 0, 0)
        for number, (day, value) in zip(reserve_ids("PM Baseline Curve", len(points)), points)], chunk_size=500)
    if first_baseline:
        frappe.db.set_value("Project", project, "pm_primary_baseline", doc.name, update_modified=False)
    activity.record("Project", project, "Hệ thống", _("Chụp {0}: {1} công việc, kết thúc {2}").format(
        doc.title, doc.task_count, frappe.utils.formatdate(doc.end_date, "dd/MM/yyyy")), data={"baseline": doc.name})
    schedule.refresh(project)
    return {"name": doc.name, "title": doc.title, "is_primary": doc.is_primary}


def set_primary(name: str) -> dict:
    doc = frappe.get_doc("PM Baseline", name)
    assert_project_capability(doc.project, "plan.edit")
    frappe.db.sql("update `tabPM Baseline` set is_primary = (name = %s) where project = %s", (name, doc.project))
    frappe.db.set_value("Project", doc.project, "pm_primary_baseline", name, update_modified=False)
    activity.record("Project", doc.project, "Hệ thống", _("Dùng {0} làm baseline chính").format(doc.title), data={"baseline": name})
    schedule.refresh(doc.project)
    return {"name": name, "is_primary": 1}


def remove(name: str) -> dict:
    doc = frappe.get_doc("PM Baseline", name)
    assert_project_capability(doc.project, "plan.edit")
    if doc.is_primary:
        frappe.throw(_("Không xóa được baseline chính: hãy chọn baseline chính khác trước"))
    frappe.db.delete("PM Baseline Task", {"baseline": name})
    frappe.db.delete("PM Baseline Curve", {"baseline": name})
    frappe.delete_doc("PM Baseline", name, ignore_permissions=True)
    activity.record("Project", doc.project, "Hệ thống", _("Xóa {0}").format(doc.title), data={"baseline": name})
    return {"name": name, "deleted": True}


def list_baselines(project: str) -> dict:
    frappe.get_doc("Project", project).check_permission("read")
    rows = frappe.get_all("PM Baseline", filters={"project": project},
                          fields=["name", "baseline_no", "title", "is_primary", "taken_on", "taken_by", "start_date", "end_date",
                                  "task_count", "note"], order_by="baseline_no desc", limit_page_length=0)
    for row in rows:
        row["taken_by_name"] = frappe.utils.get_fullname(row.taken_by) if row.taken_by else None
    return {"rows": rows, "can_edit": has_project_capability(project, "plan.edit")}


def compare(name: str, late_only: int = 0, limit: int = MAX_COMPARE_ROWS) -> dict:
    """Task by task, the plan now against this baseline, worst slip first. Slips are in working days."""
    doc = frappe.get_doc("PM Baseline", name)
    doc.check_permission("read")
    visible = set(frappe.get_list("Task", filters={"project": doc.project}, pluck="name", limit_page_length=0))
    rows = frappe.db.sql(
        """select b.task, b.start_date, b.end_date, t.subject, t.pm_wbs_code, t.exp_start_date, t.exp_end_date, t.status,
                  t.progress, t.pm_forecast_end, t.pm_is_critical, t.pm_path
           from `tabPM Baseline Task` b join `tabTask` t on t.name = b.task
           where b.baseline = %s and b.is_group = 0""", name, as_dict=True)
    calendar = calendar_of(doc.project)

    def slip(current, planned) -> int | None:
        if not current or not planned:
            return None
        return calendar.index(current, forward=False) - calendar.index(planned, forward=False)

    out = []
    moved = later = earlier = 0
    for row in rows:
        if row.task not in visible:
            continue
        plan_slip = slip(row.exp_end_date, row.end_date)
        forecast_slip = slip(row.pm_forecast_end, row.end_date) if row.status not in C.CLOSED_STATUSES else plan_slip
        if plan_slip:
            moved += 1
        if plan_slip and plan_slip > 0:
            later += 1
        if plan_slip and plan_slip < 0:
            earlier += 1
        if cint(late_only) and not ((plan_slip or 0) > 0 or (forecast_slip or 0) > 0):
            continue
        out.append({"task": row.task, "label": f"{row.pm_wbs_code or ''} {row.subject}".strip(), "status": row.status,
                    "progress": flt(row.progress), "base_start": row.start_date, "base_end": row.end_date,
                    "start": str(row.exp_start_date)[:10] if row.exp_start_date else None,
                    "end": str(row.exp_end_date)[:10] if row.exp_end_date else None,
                    "forecast": row.pm_forecast_end, "plan_slip": plan_slip, "forecast_slip": forecast_slip,
                    "critical": cint(row.pm_is_critical)})
    out.sort(key=lambda r: (-(max(r["plan_slip"] or 0, r["forecast_slip"] or 0)), r["label"]))
    limit = max(1, min(cint(limit) or MAX_COMPARE_ROWS, MAX_COMPARE_ROWS))
    return {"baseline": name, "title": doc.title, "end_date": doc.end_date, "taken_on": doc.taken_on, "rows": out[:limit],
            "total": len(out), "moved": moved, "later": later, "earlier": earlier, "added": _added(doc, visible),
            "summary": schedule.summary(doc.project)}


def _added(doc, visible: set) -> int:
    """Leaf tasks that have appeared since the baseline was taken."""
    known = set(frappe.db.sql_list("select task from `tabPM Baseline Task` where baseline = %s", doc.name))
    leaves = frappe.get_all("Task", filters={"project": doc.project, "is_group": 0, "status": ["!=", C.CANCELLED]}, pluck="name",
                            limit_page_length=0)
    return sum(1 for name in leaves if name in visible and name not in known)


def curve_of(project: str, name: str | None = None) -> list[dict]:
    """The planned curve of a baseline (the main one by default): [{day, value}]."""
    name = name or frappe.db.get_value("Project", project, "pm_primary_baseline")
    if not name:
        return []
    return frappe.get_all("PM Baseline Curve", filters={"baseline": name}, fields=["point_date as day", "planned_progress as value"],
                          order_by="point_date asc", limit_page_length=0)


def interpolate(points: list[dict], day) -> float:
    """The planned % on a day, between the curve's points."""
    if not points:
        return 0.0
    day = getdate(day)
    days = [getdate(p["day"]) for p in points]
    position = bisect_right(days, day)
    if position == 0:
        return 0.0
    if position == len(points):
        return flt(points[-1]["value"])
    before, after = points[position - 1], points[position]
    span = (getdate(after["day"]) - getdate(before["day"])).days or 1
    share = (day - getdate(before["day"])).days / span
    return round(flt(before["value"]) + (flt(after["value"]) - flt(before["value"])) * share, 2)


def planned_on(project: str, day, fallback: float) -> float:
    """What the plan says for a project on a day: its main baseline's curve when it has one."""
    points = curve_of(project)
    return interpolate(points, day) if points else fallback


def curve_for_chart(project: str, snapshots: list[dict]) -> list[dict]:
    """Actual progress from the daily snapshots, on the plan's whole curve: the actual line stops today, the plan goes on
    to the end. Points are [{snapshot_date, progress, planned_progress}] with progress None in the future."""
    points = curve_of(project)
    if not points:
        return snapshots
    by_day = {str(row["snapshot_date"]): row for row in snapshots}
    days = sorted(set(by_day) | {str(p["day"]) for p in points})
    return [{"snapshot_date": day, "progress": by_day[day]["progress"] if day in by_day else None,
             "planned_progress": interpolate(points, day)} for day in days]

