"""Lịch trình of a project: dependencies, the critical path, moving dates with what follows them, the forecast.

The network, in working days (services/workdays.py, services/cpm.py):

* A leaf task is an activity lasting its planned working days, not starting before its planned start. Tasks without
  dates and cancelled tasks are left out. A milestone (PM Node Type.is_milestone) takes no time.
* A group is two zero-length points, its start and its finish, with its children in between. A link to or from a group
  (one phase after another) then needs no special case. A group may only be a predecessor by its finish (FS, FF): "its
  start" is the earliest of its children, which the network does not know beforehand.

Three things are computed from it:

* the plan (`refresh`, in the background): total float and critical path of the planned dates, and how far a planned
  start ignores its dependencies (pm_conflict_days), written only where they changed;
* a move (`preview`, `apply`): the dates of a task, or a whole group shifted, and the tasks after it that would then
  break a dependency, pushed just enough. Tasks are never pulled earlier by themselves, a task already finished never
  moves, and a date that breaks a dependency is corrected, with a note. Nothing is written by a preview;
* the forecast (`forecast`): when the work will really end, from today: what is done keeps its actual dates, work under
  way runs at the pace it has shown, what has not started cannot start before today and still waits for its predecessors.

The pace is r = 0.6 x progress of the last 14 days per working day + 0.4 x progress since it started per working day.
Without any pace yet, the planned duration applies; the rest of a slow task is capped at 5 times its duration, so that
one stalled task does not throw the project's forecast off by years (the stall itself is an alert, M7).

A change made on the plan itself (a link, a move, a baseline) is recomputed in the same request, so the screen shows it at
once. Any other change of dates, status or progress marks the project (Redis set, deduplicated job on the "pm" queue,
after the commit); a sweeper picks up what was missed and every night all running projects are recomputed.
"""

from math import ceil

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import (
    assert_project_capability,
    get_access,
    has_project_capability,
)
from project_manager.project_manager.services import activity, jobs, rollup
from project_manager.project_manager.services.cpm import FF, FS, SF, SS, Activity, CycleError, Link, forward, order, solve
from project_manager.project_manager.services.errors import retry_on_deadlock
from project_manager.project_manager.services.notify import notify_user
from project_manager.project_manager.services.workdays import calendar_of

QUEUE = "pm"
DIRTY = "pm_cpm_dirty"
GANTT_LIMIT = 20000
PACE_DAYS = 14
MAX_STRETCH = 5
MOVE_CAPABILITIES = ("plan.edit", "task.assign")
TASK_COLUMNS = """name, subject, parent_task, is_group, status, progress, exp_start_date, exp_end_date, act_start_date,
    act_end_date, pm_node_type, pm_wbs_code, pm_rollup_weight, pm_total_float, pm_is_critical, pm_conflict_days,
    pm_forecast_end, pm_spi, pm_accountable, pm_path, task_weight"""


def _milestones() -> set:
    memo = getattr(frappe.local, "pm_milestone_types", None)
    if memo is None:
        memo = frappe.local.pm_milestone_types = set(frappe.get_all("PM Node Type", filters={"is_milestone": 1}, pluck="name"))
    return memo


class Network:
    """The project's tasks and links, as they are in the database now."""

    def __init__(self, project: str):
        self.project = project
        self.calendar = calendar_of(project)
        self.rows = {row.name: row for row in frappe.db.sql(
            f"select {TASK_COLUMNS} from `tabTask` where project = %s and status != %s",
            (project, C.CANCELLED), as_dict=True)}
        self.dependencies = frappe.get_all("PM Task Dependency", filters={"project": project},
                                           fields=["name", "predecessor", "successor", "dep_type", "lag_days"],
                                           limit_page_length=0)
        self.milestones = _milestones()

    def span(self, row) -> tuple | None:
        """(start point, working days) of a leaf's plan, None when it has no dates. A milestone sits at the end of its
        day: a task finishing that same day does not conflict with it."""
        first, last = row.exp_start_date or row.exp_end_date, row.exp_end_date or row.exp_start_date
        if not first:
            return None
        if row.pm_node_type in self.milestones:
            return self.calendar.index(last, forward=False) + 1, 0
        start = self.calendar.index(first)
        return start, max(1, self.calendar.index(last, forward=False) - start + 1)

    def start_key(self, name):
        return (name, "S") if self.rows[name].is_group else name

    def finish_key(self, name):
        return (name, "F") if self.rows[name].is_group else name

    def graph(self, leaf, every: bool = False) -> tuple[dict, list]:
        """Activities and links. `leaf(row, span)` makes the activity of a task that has dates; `every` also keeps the
        tasks without dates (for checking circles, which do not depend on dates)."""
        activities, links = {}, []
        for name, row in self.rows.items():
            if row.is_group:
                activities[(name, "S")] = Activity(0)
                activities[(name, "F")] = Activity(0)
                links.append(Link((name, "S"), (name, "F"), FS, 0))
            else:
                span = self.span(row)
                if span is not None or every:
                    activities[name] = leaf(row, span)
        for name, row in self.rows.items():
            parent = self.rows.get(row.parent_task) if row.parent_task else None
            if parent is None or not parent.is_group or self.start_key(name) not in activities:
                continue
            links.append(Link((parent.name, "S"), self.start_key(name), FS, 0))
            links.append(Link(self.finish_key(name), (parent.name, "F"), FS, 0))
        for dep in self.dependencies:
            if dep.predecessor not in self.rows or dep.successor not in self.rows:
                continue
            pred = self.start_key(dep.predecessor) if dep.dep_type in (SS, SF) and not self.rows[dep.predecessor].is_group \
                else self.finish_key(dep.predecessor)
            succ = self.start_key(dep.successor) if dep.dep_type in (FS, SS) else self.finish_key(dep.successor)
            if pred in activities and succ in activities:
                links.append(Link(pred, succ, dep.dep_type, cint(dep.lag_days)))
        return activities, links

    def last_day(self, finish: int):
        """The day something finishing at this point ends on."""
        return self.calendar.date_at(finish - 1)

    def first_day(self, start: int, finish: int):
        """The day something occupying these points starts on (a milestone is on its own day)."""
        return self.calendar.date_at(start) if finish > start else self.calendar.date_at(finish - 1)


def _plain_activity(_row, span) -> Activity:
    return Activity(span[1], not_before=span[0])


# --- the plan: float, critical path, conflicts ------------------------------------------------------------------------

def compute_plan(net: Network) -> dict:
    activities, links = net.graph(_plain_activity)
    result = solve(activities, links)
    out = {}
    for name, row in net.rows.items():
        key = net.finish_key(name)
        if key not in activities:
            continue
        spare = result.total_float[key]
        conflict = 0
        if not row.is_group:
            conflict = max(0, result.start[name] - net.span(row)[0])
        out[name] = {"pm_total_float": spare, "pm_is_critical": 1 if spare <= 0 else 0, "pm_conflict_days": conflict}
    finishes = [result.finish[key] for key in activities if not isinstance(key, tuple)]
    return {"tasks": out, "end": net.last_day(max(finishes)) if finishes else None}


# --- the forecast -------------------------------------------------------------------------------------------------------

def _recent_progress(project: str, since) -> dict:
    """{task: progress at the start of the period}, for the tasks reported on since then."""
    first = {}
    for row in frappe.db.sql(
            """select task, progress_before from `tabPM Progress Entry`
               where project = %s and entry_date >= %s order by name asc""", (project, since), as_dict=True):
        first.setdefault(row.task, flt(row.progress_before))
    return first


def remaining_days(row, span_days: int, started_on, today, calendar, window_start: dict) -> int:
    """Working days this work under way still needs, from the pace it has shown."""
    progress = flt(row.progress)
    if row.status == C.REVIEW or progress >= 100:
        return 1
    period_start = add_days(today, -(PACE_DAYS - 1))
    recent = progress - window_start[row.name] if row.name in window_start else 0.0
    pace = 0.6 * max(0.0, recent) / max(1, calendar.count(period_start, today))
    pace += 0.4 * progress / max(1, calendar.count(started_on, today))
    planned = max(1, ceil(max(1, span_days) * (100 - progress) / 100))
    if pace <= 0:
        return planned
    return max(1, min(ceil((100 - progress) / pace), MAX_STRETCH * max(1, span_days) + 1))


def _planned_share(calendar, start, days: int, today_index: int) -> float:
    """Share of a plan that should be done by the end of today."""
    if days <= 0:
        return 1.0 if today_index + 1 >= start else 0.0
    return min(1.0, max(0.0, (today_index - start + 1) / days))


def compute_forecast(net: Network, today=None) -> dict:
    today = getdate(today or nowdate())
    calendar = net.calendar
    now = calendar.index(today)
    window = _recent_progress(net.project, add_days(today, -(PACE_DAYS - 1)))

    def leaf(row, span):
        start, days = span
        if row.status == C.COMPLETED:
            finish = calendar.index(row.act_end_date or row.exp_end_date or row.exp_start_date, forward=False) + 1
            begun = min(calendar.index(row.act_start_date) if row.act_start_date else start, finish)
            return Activity(finish - begun, fixed_start=begun, fixed_finish=finish)
        if row.status in (C.WORKING, C.REVIEW) or flt(row.progress) > 0 or row.act_start_date:
            started_on = row.act_start_date or row.exp_start_date or today
            if getdate(started_on) > today:
                started_on = today
            begun = min(calendar.index(started_on), now)
            return Activity(0, fixed_start=begun, min_finish=now + remaining_days(row, days, started_on, today, calendar, window))
        return Activity(days, not_before=max(start, now if days else now + 1))

    activities, links = net.graph(leaf)
    start, finish = forward(activities, links)
    out = {}
    earned = planned = 0.0
    baseline = _baseline_spans(net)
    for name, row in net.rows.items():
        key = net.finish_key(name)
        if key not in activities or (row.is_group and not (row.exp_start_date or row.exp_end_date)):
            continue
        values = {"pm_forecast_end": net.last_day(finish[key]).isoformat(), "pm_spi": 0.0}
        if not row.is_group:
            span = net.span(row)
            share = _planned_share(calendar, span[0], span[1], calendar.index(today, forward=False))
            if share > 0:
                values["pm_spi"] = round(flt(row.progress) / 100 / share, 2)
            weight = flt(row.pm_rollup_weight)
            reference = baseline.get(name, span)
            earned += weight * flt(row.progress) / 100
            planned += weight * _planned_share(calendar, reference[0], reference[1], calendar.index(today, forward=False))
        out[name] = values
    finishes = [finish[key] for key in activities if not isinstance(key, tuple)]
    return {"tasks": out, "end": net.last_day(max(finishes)) if finishes else None,
            "spi": round(earned / planned, 2) if planned else 0.0}


def _baseline_spans(net: Network) -> dict:
    """{task: (first working day, working days)} of the project's main baseline: what SPI is measured against."""
    name = frappe.db.get_value("Project", net.project, "pm_primary_baseline")
    if not name:
        return {}
    out = {}
    for row in frappe.db.sql("select task, start_date, end_date from `tabPM Baseline Task` where baseline = %s and is_group = 0",
                             name, as_dict=True):
        if row.start_date and row.end_date:
            first = net.calendar.index(row.start_date)
            out[row.task] = (first, max(1, net.calendar.index(row.end_date, forward=False) - first + 1))
    return out


# --- writing what was computed ------------------------------------------------------------------------------------------

def _same(stored, new) -> bool:
    if isinstance(new, str):
        return str(stored or "")[:10] == new
    return abs(flt(stored) - flt(new)) < 0.005


def _write_columns(updates: dict) -> None:
    """{task: {column: value}}, in statements of 300 rows."""
    names = list(updates)
    for chunk in range(0, len(names), 300):
        batch = names[chunk:chunk + 300]
        columns = sorted({column for name in batch for column in updates[name]})
        parts = []
        for column in columns:
            cases = " ".join(f"when {frappe.db.escape(name)} then {_sql_value(updates[name][column])}"
                             for name in batch if column in updates[name])
            parts.append(f"`{column}` = case name {cases} else `{column}` end")
        in_list = ", ".join(frappe.db.escape(name) for name in batch)
        frappe.db.sql(f"update `tabTask` set {', '.join(parts)} where name in ({in_list})")


def _sql_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return frappe.db.escape(str(value))


def refresh(project: str, today=None) -> int:
    """Recompute a project's plan, forecast and health. Returns the number of tasks whose figures changed."""
    net = Network(project)
    if not net.rows:
        frappe.db.set_value("Project", project, {"pm_plan_end": None, "pm_forecast_end": None, "pm_spi": 0}, update_modified=False)
        return 0
    try:
        plan = compute_plan(net)
        forecast = compute_forecast(net, today=today)
    except CycleError as error:  # refused when links are added: only a direct database change can get here
        frappe.log_error(title=f"Circular dependency in {project}", message=str(error))
        return 0
    updates = {}
    for name, row in net.rows.items():
        changed = {}
        for values in (plan["tasks"].get(name), forecast["tasks"].get(name)):
            for column, value in (values or {}).items():
                if not _same(row.get(column), value):
                    changed[column] = value
        if changed:
            updates[name] = changed
    _write_columns(updates)
    frappe.db.set_value("Project", project, {
        "pm_plan_end": plan["end"], "pm_forecast_end": forecast["end"], "pm_spi": forecast["spi"]}, update_modified=False)
    from project_manager.project_manager.services import risk

    try:
        risk.evaluate(project, net, plan, forecast, today)  # health follows the forecast it reads
    except Exception:
        frappe.log_error(f"Sức khỏe dự án {project}", frappe.get_traceback())
    return len(updates)


def mark(project: str) -> None:
    """After the commit: this project's plan and forecast must be recomputed."""
    if not project:
        return

    def push():
        frappe.cache.sadd(DIRTY, project)
        jobs.enqueue_once("project_manager.project_manager.services.schedule.process", f"pm-cpm:{project}", QUEUE,
                          project=project, enqueue_after_commit=False)
    frappe.db.after_commit.add(push)


def _dirty() -> set:
    return {m.decode() if isinstance(m, bytes) else m for m in frappe.cache.smembers(DIRTY)}


def process(project: str) -> None:
    for _attempt in range(3):
        if project not in _dirty():
            return
        frappe.cache.srem(DIRTY, project)
        try:
            retry_on_deadlock(lambda: refresh(project))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.cache.sadd(DIRTY, project)  # the sweeper tries again
            raise


def sweep() -> int:
    """Every 5 minutes: projects marked whose job did not run."""
    projects = _dirty()
    for project in projects:
        frappe.enqueue("project_manager.project_manager.services.schedule.process", queue=QUEUE, project=project,
                       job_id=f"pm-cpm:{project}", deduplicate=True)
    return len(projects)


def refresh_all() -> int:
    """Every night: today moved on, so every running project's forecast moves too."""
    count = 0
    for project in frappe.get_all("Project", filters={"pm_state": ["not in", ["Đóng", "Hủy"]], "pm_is_template": 0}, pluck="name"):
        retry_on_deadlock(lambda p=project: refresh(p))
        frappe.db.commit()
        count += 1
    return count


# --- dependencies -------------------------------------------------------------------------------------------------------

def _label(row) -> str:
    return f"{row.pm_wbs_code or ''} {row.subject}".strip()


def _link_rules(net: Network, predecessor: str, successor: str, kind: str) -> None:
    """The rules of one link, but the circle (which needs the whole network)."""
    if kind not in (FS, SS, FF, SF):
        frappe.throw(_("Kiểu phụ thuộc không hợp lệ: {0}").format(kind))
    if predecessor == successor:
        frappe.throw(_("Công việc không thể phụ thuộc vào chính nó"))
    before, after = net.rows.get(predecessor), net.rows.get(successor)
    if not before or not after:
        frappe.throw(_("Hai công việc phải thuộc cùng một dự án và chưa bị hủy"))
    if before.pm_path and after.pm_path and (after.pm_path.startswith(before.pm_path + ".") or before.pm_path.startswith(after.pm_path + ".")):
        frappe.throw(_("Không đặt phụ thuộc giữa một nhóm và công việc nằm trong nhóm đó"))
    if before.is_group and kind in (SS, SF):
        frappe.throw(_("Nhóm công việc chỉ làm việc trước theo kiểu FS hoặc FF"))


def _check_dependency(net: Network, predecessor: str, successor: str, kind: str, ignore=None) -> None:
    _link_rules(net, predecessor, successor, kind)
    before, after = net.rows[predecessor], net.rows[successor]
    trial = frappe._dict(name="(mới)", predecessor=predecessor, successor=successor, dep_type=kind, lag_days=0)
    net.dependencies = [d for d in net.dependencies if d.name != ignore] + [trial]
    try:
        order(*net.graph(lambda _row, _span: Activity(0), every=True))
    except CycleError:
        frappe.throw(_("Không thêm được: {0} đã phụ thuộc vào {1}, sẽ thành một vòng tròn").format(_label(before), _label(after)),
                     title=_("Phụ thuộc vòng tròn"))


def check_many(net: Network, links: list[dict]) -> tuple[list, list]:
    """Many links to add at once ({"predecessor", "successor", "kind"}): (the ones that keep every rule, [(link, why)]).
    The circle is checked once for all of them; only when they close one are they tried one by one."""
    kept, skipped = [], []
    for link in links:
        try:
            _link_rules(net, link["predecessor"], link["successor"], link["kind"])
        except frappe.ValidationError as e:
            frappe.clear_last_message()
            skipped.append((link, str(e)))
            continue
        kept.append(link)
    base = net.dependencies
    net.dependencies = base + [frappe._dict(name=f"(mới {i})", predecessor=l["predecessor"], successor=l["successor"],
                                            dep_type=l["kind"], lag_days=0) for i, l in enumerate(kept)]
    try:
        order(*net.graph(lambda _row, _span: Activity(0), every=True))
        return kept, skipped
    except CycleError:
        net.dependencies = base
    out = []
    for link in kept:
        try:
            _check_dependency(net, link["predecessor"], link["successor"], link["kind"])
            out.append(link)
        except frappe.ValidationError as e:
            frappe.clear_last_message()
            skipped.append((link, str(e)))
    return out, skipped


def add_dependency(predecessor: str, successor: str, kind: str = FS, lag: int = 0) -> dict:
    project = frappe.db.get_value("Task", successor, "project")
    if not project or frappe.db.get_value("Task", predecessor, "project") != project:
        frappe.throw(_("Hai công việc phải thuộc cùng một dự án và chưa bị hủy"))
    assert_project_capability(project, "plan.edit")
    if frappe.db.exists("PM Task Dependency", {"predecessor": predecessor, "successor": successor}):
        frappe.throw(_("Đã có phụ thuộc giữa hai công việc này"))
    net = Network(project)
    _check_dependency(net, predecessor, successor, kind)
    doc = frappe.get_doc({"doctype": "PM Task Dependency", "predecessor": predecessor, "successor": successor,
                          "dep_type": kind, "lag_days": cint(lag)})
    doc.insert(ignore_permissions=True)
    activity.record("Task", successor, "Thay đổi", _("Thêm phụ thuộc: sau {0} ({1}{2})").format(
        _label(net.rows[predecessor]), kind, _lag_text(lag)), data={"dependency": doc.name})
    refresh(project)
    return {"name": doc.name}


def _lag_text(lag) -> str:
    return f"{cint(lag):+d}" if cint(lag) else ""


def update_dependency(name, kind: str, lag: int = 0) -> dict:
    doc = frappe.get_doc("PM Task Dependency", cint(name))
    assert_project_capability(doc.project, "plan.edit")
    _check_dependency(Network(doc.project), doc.predecessor, doc.successor, kind, ignore=doc.name)
    frappe.db.set_value("PM Task Dependency", doc.name, {"dep_type": kind, "lag_days": cint(lag)})
    activity.record("Task", doc.successor, "Thay đổi", _("Đổi phụ thuộc thành {0}{1}").format(kind, _lag_text(lag)),
                    data={"dependency": doc.name})
    refresh(doc.project)
    return {"name": doc.name}


def remove_dependency(name) -> dict:
    doc = frappe.get_doc("PM Task Dependency", cint(name))
    assert_project_capability(doc.project, "plan.edit")
    label = _label(frappe.db.get_value("Task", doc.predecessor, ["subject", "pm_wbs_code"], as_dict=True))
    frappe.delete_doc("PM Task Dependency", doc.name, ignore_permissions=True)
    activity.record("Task", doc.successor, "Thay đổi", _("Bỏ phụ thuộc: sau {0}").format(label), data={"predecessor": doc.predecessor})
    refresh(doc.project)
    return {"name": doc.name, "deleted": True}


def of_task(task: str) -> dict:
    """What comes before and after a task, and where it stands on the critical path."""
    info = frappe.get_doc("Task", task)
    info.check_permission("read")

    def rows(field, other):
        links = frappe.get_all("PM Task Dependency", filters={field: task}, fields=["name", other, "dep_type", "lag_days"],
                               order_by="name asc", limit_page_length=0)
        names = {link[other] for link in links}
        labels = {t.name: t for t in frappe.get_all("Task", filters={"name": ["in", list(names)]},
                                                    fields=["name", "subject", "pm_wbs_code", "status"])} if names else {}
        for link in links:
            found = labels.get(link[other])
            link["task"] = link[other]
            link["label"] = _label(found) if found else link[other]
            link["status"] = found.status if found else None
        return links

    return {"predecessors": rows("successor", "predecessor"), "successors": rows("predecessor", "successor"),
            "can_edit": has_project_capability(info.project, "plan.edit"), "total_float": cint(info.pm_total_float),
            "critical": cint(info.pm_is_critical), "conflict_days": cint(info.pm_conflict_days),
            "forecast_end": info.pm_forecast_end}


def search_tasks(project: str, text: str = "", exclude: str | None = None) -> list[dict]:
    """Tasks to pick as a predecessor or successor."""
    frappe.get_doc("Project", project).check_permission("read")
    like = f"%{(text or '').strip()}%"
    rows = frappe.get_list("Task", filters={"project": project, "status": ["!=", C.CANCELLED]},
                           or_filters={"subject": ["like", like], "pm_wbs_code": ["like", like]},
                           fields=["name", "subject", "pm_wbs_code"], order_by="pm_path asc", limit_page_length=20)
    return [{"value": r.name, "label": _label(r)} for r in rows if r.name != exclude]


# --- moving dates -------------------------------------------------------------------------------------------------------

def _reachable(seeds, links) -> set:
    following = {}
    for link in links:
        following.setdefault(link.pred, []).append(link.succ)
    seen, stack = set(seeds), list(seeds)
    while stack:
        for succ in following.get(stack.pop(), ()):
            if succ not in seen:
                seen.add(succ)
                stack.append(succ)
    return seen


def _rearranged(net: Network, overrides: dict, seeds=None) -> dict:
    """The dates after a change: {task: (start point, finish point)} of every leaf with dates, and the plan's end."""
    def closed(row):
        return row.status == C.COMPLETED

    activities, links = net.graph(lambda row, span: Activity(overrides.get(row.name, span)[1],
                                                             not_before=overrides.get(row.name, span)[0]))
    touched = _reachable(list(overrides) + list(seeds or ()), links)
    for name, row in net.rows.items():
        if row.is_group or name not in activities:
            continue
        current = net.span(row)
        if closed(row) or name not in touched:
            activities[name] = Activity(current[1], fixed_start=current[0], fixed_finish=current[0] + current[1])
    start, finish = forward(activities, links)
    return {key: (start[key], finish[key]) for key in activities if not isinstance(key, tuple)}


def _result(net: Network, source: str | None, overrides: dict, seeds=None) -> dict:
    spans = {name: net.span(row) for name, row in net.rows.items() if not row.is_group}
    before_points = {name: span for name, span in spans.items() if span}
    after = _rearranged(net, overrides, seeds)
    changes = []
    for name, (start, finish) in after.items():
        was = before_points[name]
        if (start, finish) == (was[0], was[0] + was[1]):
            continue
        row = net.rows[name]
        changes.append({"name": name, "label": _label(row), "path": row.pm_path or "", "direct": name in overrides,
                        "from_start": net.first_day(was[0], was[0] + was[1]).isoformat(),
                        "from_end": net.last_day(was[0] + was[1]).isoformat(),
                        "to_start": net.first_day(start, finish).isoformat(),
                        "to_end": net.last_day(finish).isoformat(),
                        "days": start - was[0], "person": row.pm_accountable})
    changes.sort(key=lambda c: c["path"])
    clamped = [name for name, wanted in overrides.items() if name in after and after[name][0] != wanted[0]]
    now_end = max((span[0] + span[1] for span in before_points.values()), default=None)
    new_end = max((finish for _start, finish in after.values()), default=None)
    contract = frappe.db.get_value("Project", net.project, "expected_end_date")
    plan_end_after = net.last_day(new_end) if new_end is not None else None
    people = frappe.get_all("PM Task Assignment", filters={"task": ["in", [c["name"] for c in changes]], "is_active": 1,
                                                           "state": ["in", C.LIVE_STATES]}, pluck="task") if changes else []
    return {
        "task": source, "changes": changes, "total": len(changes), "clamped": bool(clamped),
        "plan_end_before": net.last_day(now_end).isoformat() if now_end is not None else None,
        "plan_end_after": plan_end_after.isoformat() if plan_end_after else None,
        "contract_end": str(contract) if contract else None,
        "over_contract": bool(contract and plan_end_after and plan_end_after > getdate(contract)),
        "reason_required": bool(people),
    }


def _overrides(net: Network, task: str, start=None, end=None) -> dict:
    row = net.rows.get(task)
    if not row:
        frappe.throw(_("Công việc này đã hủy hoặc không thuộc dự án"))
    calendar = net.calendar
    if row.is_group:
        if not start or not row.exp_start_date:
            frappe.throw(_("Nhóm chỉ dời được cả khối: hãy chọn ngày bắt đầu mới"))
        delta = calendar.index(start) - calendar.index(row.exp_start_date)
        prefix = (row.pm_path or "") + "."
        moved = {}
        for name, child in net.rows.items():
            if child.is_group or not (child.pm_path or "").startswith(prefix) or child.status == C.COMPLETED:
                continue
            span = net.span(child)
            if span:
                moved[name] = (span[0] + delta, span[1])
        return moved
    if row.status == C.COMPLETED:
        frappe.throw(_("Công việc đã xong: không dời ngày kế hoạch nữa"))
    current = net.span(row)
    if row.pm_node_type in net.milestones:
        day = start or end
        if not day and not current:
            frappe.throw(_("Hãy chọn ngày"))
        return {task: (calendar.index(day, forward=False) + 1 if day else current[0], 0)}
    first = calendar.index(start) if start else (current[0] if current else None)
    if first is None:
        frappe.throw(_("Hãy chọn ngày bắt đầu"))
    if end:
        return {task: (first, max(1, calendar.index(end, forward=False) - first + 1))}
    return {task: (first, current[1] if current else 1)}


def _load_for_move(task: str, lock: bool = False) -> Network:
    project = frappe.db.get_value("Task", task, "project")
    if not project:
        frappe.throw(_("Công việc chưa thuộc dự án nào"))
    assert_project_capability(project, *MOVE_CAPABILITIES)
    if lock:  # moves in one project take turns
        frappe.db.sql("select name from `tabProject` where name = %s for update", project)
    return Network(project)


def preview(task: str, start=None, end=None) -> dict:
    """What moving this task would do. Nothing is written."""
    net = _load_for_move(task)
    return _result(net, task, _overrides(net, task, start, end))


def apply(task: str, start=None, end=None, reason: str = "") -> dict:
    """Move the task and push what depends on it."""
    net = _load_for_move(task, lock=True)
    result = _result(net, task, _overrides(net, task, start, end))
    _commit_changes(net, result, reason, net.rows[task])
    return result


def conflicts_preview(project: str) -> dict:
    """What it takes to make the plan respect every dependency."""
    assert_project_capability(project, *MOVE_CAPABILITIES)
    net = Network(project)
    return _result(net, None, {}, _conflicted(net))


def conflicts_apply(project: str, reason: str = "") -> dict:
    assert_project_capability(project, *MOVE_CAPABILITIES)
    frappe.db.sql("select name from `tabProject` where name = %s for update", project)
    net = Network(project)
    result = _result(net, None, {}, _conflicted(net))
    _commit_changes(net, result, reason, None)
    return result


def _conflicted(net: Network) -> list:
    return [name for name, values in compute_plan(net)["tasks"].items() if values["pm_conflict_days"] > 0]


def _commit_changes(net: Network, result: dict, reason: str, source) -> None:
    reason = (reason or "").strip()
    if result["reason_required"] and not reason:
        frappe.throw(_("Việc đã giao cho người thực hiện: hãy ghi lý do đổi ngày"), title=_("Thiếu lý do"))
    if not result["changes"]:
        return
    method = rollup.method_of(net.project)
    updates, parents, entries, people = {}, set(), [], {}
    now = now_datetime()
    user = frappe.session.user
    for change in result["changes"]:
        row = net.rows[change["name"]]
        moved = frappe._dict(row, exp_start_date=change["to_start"], exp_end_date=change["to_end"])
        overdue, delay = rollup.overdue_state(moved)
        updates[change["name"]] = {
            "exp_start_date": change["to_start"], "exp_end_date": change["to_end"], "pm_is_overdue": overdue,
            "pm_delay_days": delay, "pm_rollup_weight": rollup.leaf_weight(moved, method), "modified": str(now),
            "modified_by": user}
        parents.add(row.parent_task or "")
        cause = "" if change["direct"] or not source else _("theo {0}").format(_label(source))
        text = _("Đổi hạn: {0} → {1}").format(frappe.utils.formatdate(change["from_end"], "dd/MM/yyyy"),
                                                frappe.utils.formatdate(change["to_end"], "dd/MM/yyyy"))
        text = ". ".join(part for part in (text, cause, f"{_('Lý do')}: {reason}" if reason else "") if part)
        entries.append(("Task", change["name"], "Đổi hạn", text, {"from": [change["from_start"], change["from_end"]],
                                                                  "to": [change["to_start"], change["to_end"]], "reason": reason}))
        if change["person"] and change["person"] != user:
            people[change["person"]] = people.get(change["person"], 0) + 1
    _write_columns(updates)
    activity.record_many(net.project, entries)
    for person, count in people.items():
        link = f"/pm/du-an/{net.project}/gantt"
        notify_user(person, _("Kế hoạch đổi: hạn của {0} việc của bạn đã dời").format(count), link, "Project", net.project)
    rollup.schedule(net.project, parents)
    refresh(net.project)


# --- what the screens read ----------------------------------------------------------------------------------------------

def summary(project: str) -> dict:
    """The plan in a few figures, for the overview and the Gantt."""
    info = frappe.db.get_value("Project", project, ["expected_end_date", "pm_plan_end", "pm_forecast_end", "pm_spi",
                                                    "pm_primary_baseline"], as_dict=True)
    baseline = frappe.db.get_value("PM Baseline", info.pm_primary_baseline, ["title", "end_date"], as_dict=True) if info.pm_primary_baseline else None
    counts = frappe.db.sql(
        f"""select sum(pm_is_critical = 1 and status not in ('{C.COMPLETED}', '{C.CANCELLED}')) as critical,
                   sum(pm_conflict_days > 0 and status not in ('{C.COMPLETED}', '{C.CANCELLED}')) as conflicts,
                   sum(exp_start_date is null and exp_end_date is null and status != '{C.CANCELLED}') as unscheduled
            from `tabTask` where project = %s and is_group = 0""", project, as_dict=True)[0]
    calendar = calendar_of(project)
    target = (baseline.end_date if baseline else None) or info.expected_end_date

    def slip(day) -> int | None:
        if not day or not target:
            return None
        return calendar.index(day, forward=False) - calendar.index(target, forward=False)

    return {
        "contract_end": info.expected_end_date, "plan_end": info.pm_plan_end, "forecast_end": info.pm_forecast_end,
        "baseline_end": baseline.end_date if baseline else None, "baseline_title": baseline.title if baseline else None,
        "baseline": info.pm_primary_baseline, "spi": flt(info.pm_spi), "critical": cint(counts.critical),
        "conflicts": cint(counts.conflicts), "unscheduled": cint(counts.unscheduled),
        "links": frappe.db.count("PM Task Dependency", {"project": project}), "forecast_slip": slip(info.pm_forecast_end),
        "plan_slip": slip(info.pm_plan_end),
    }


GANTT_FIELDS = ["name", "subject", "pm_wbs_code", "pm_level", "is_group", "parent_task", "exp_start_date", "exp_end_date",
                "progress", "status", "pm_is_critical", "pm_total_float", "pm_node_type", "pm_forecast_end",
                "pm_conflict_days", "pm_accountable", "pm_is_overdue"]


def _day(value) -> str | None:
    return str(value)[:10] if value else None


def gantt(project: str, baseline: str | None = None) -> dict:
    """Every visible task of a project in tree order, compactly: `columns` names the values of each row."""
    frappe.get_doc("Project", project).check_permission("read")
    access = get_access()
    tasks = frappe.get_list("Task", filters={"project": project, "status": ["!=", C.CANCELLED]}, fields=GANTT_FIELDS,
                            order_by="pm_path asc", limit_page_length=GANTT_LIMIT + 1)
    more = len(tasks) > GANTT_LIMIT
    tasks = tasks[:GANTT_LIMIT]
    baselines = frappe.get_all("PM Baseline", filters={"project": project}, fields=["name", "title", "is_primary", "baseline_no"],
                               order_by="baseline_no desc", limit_page_length=0)
    chosen = baseline or next((b.name for b in baselines if b.is_primary), None)
    if chosen and chosen not in {b.name for b in baselines}:
        chosen = None
    planned = {}
    if chosen:
        for row in frappe.db.sql("select task, start_date, end_date from `tabPM Baseline Task` where baseline = %s", chosen, as_dict=True):
            planned[row.task] = (_day(row.start_date), _day(row.end_date))
    milestones = _milestones()
    visible = {t.name for t in tasks}
    people = {t.pm_accountable for t in tasks if t.pm_accountable}
    names = dict(frappe.get_all("User", filters={"name": ["in", list(people)]}, fields=["name", "full_name"], as_list=True)) if people else {}
    rows = []
    days = []
    for t in tasks:
        start, end = _day(t.exp_start_date), _day(t.exp_end_date)
        base = planned.get(t.name, (None, None))
        days += [d for d in (start, end, base[0], base[1], _day(t.pm_forecast_end)) if d]
        rows.append([t.name, t.subject, t.pm_wbs_code or "", cint(t.pm_level), cint(t.is_group),
                     t.parent_task if t.parent_task in visible else None, start or end, end or start, flt(t.progress),
                     t.status, cint(t.pm_is_critical), cint(t.pm_total_float), 1 if t.pm_node_type in milestones else 0,
                     _day(t.pm_forecast_end), cint(t.pm_conflict_days), names.get(t.pm_accountable), cint(t.pm_is_overdue),
                     base[0], base[1]])
    links = [[d.name, d.predecessor, d.successor, d.dep_type, cint(d.lag_days)]
             for d in frappe.get_all("PM Task Dependency", filters={"project": project},
                                     fields=["name", "predecessor", "successor", "dep_type", "lag_days"], limit_page_length=0)
             if d.predecessor in visible and d.successor in visible]
    calendar = calendar_of(project)
    days_off = calendar.between(add_days(min(days), -14), add_days(max(days), 60)) if days else []
    return {
        "columns": ["name", "subject", "code", "level", "group", "parent", "start", "end", "progress", "status", "critical",
                    "float", "milestone", "forecast", "conflict", "who", "late", "base_start", "base_end"],
        "rows": rows, "links": links, "more": more, "days_off": days_off, "today": nowdate(), "baselines": baselines,
        "baseline": chosen, "summary": summary(project),
        "flat": access.read_tasks is not None and project not in access.read_tasks,
        "can": {"plan": has_project_capability(project, "plan.edit"),
                "dates": has_project_capability(project, *MOVE_CAPABILITIES)},
    }


def calendar_view(project: str, first, last) -> dict:
    """The work planned in a period, and its days off."""
    frappe.get_doc("Project", project).check_permission("read")
    first, last = getdate(first), getdate(last)
    if (last - first).days > 370:
        frappe.throw(_("Chỉ xem được tối đa một năm một lần"))
    common = [["Task", "project", "=", project], ["Task", "is_group", "=", 0], ["Task", "status", "!=", C.CANCELLED]]
    fields = ["name", "subject", "pm_wbs_code", "exp_start_date", "exp_end_date", "status", "progress", "pm_is_critical",
              "pm_is_overdue", "pm_accountable", "pm_node_type"]
    tasks = frappe.get_list("Task", filters=[*common, ["Task", "exp_start_date", "<=", f"{last} 23:59:59"],
                                             ["Task", "exp_end_date", ">=", f"{first} 00:00:00"]],
                            fields=fields, order_by="exp_start_date asc", limit_page_length=1000)
    tasks += frappe.get_list("Task", filters=[*common, ["Task", "exp_start_date", "is", "not set"],  # only a deadline
                                              ["Task", "exp_end_date", "between", [str(first), str(last)]]],
                             fields=fields, order_by="exp_end_date asc", limit_page_length=1000)
    milestones = _milestones()
    people = {t.pm_accountable for t in tasks if t.pm_accountable}
    names = dict(frappe.get_all("User", filters={"name": ["in", list(people)]}, fields=["name", "full_name"], as_list=True)) if people else {}
    for task in tasks:
        task["start"], task["end"] = _day(task.exp_start_date or task.exp_end_date), _day(task.exp_end_date)
        task["who"] = names.get(task.pm_accountable)
        task["milestone"] = 1 if task.pm_node_type in milestones else 0
    return {"tasks": tasks, "days_off": calendar_of(project).between(first, last), "today": nowdate()}

