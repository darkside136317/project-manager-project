"""Progress roll-up: a group's progress, dates and status come from its children, the project's from its roots.

Incremental, so that saving one task never rescans a 20 000-task project:

1. mark_dirty(task) — on save of a task (Task mixin) its parent is added to the Redis set pm_rollup:<project> and a
   job pm-rollup:<project> is queued on the "pm" queue, both after the commit (deduplicated: one job per project).
2. process(project) — takes the dirty parents and recomputes them level by level, bottom-up: one GROUP BY query per
   level aggregates the children (weight, weighted progress, earliest start, latest end, status counts); only rows
   whose values change are written (plain UPDATEs: no document save, no hooks); the parents of changed groups form
   the next level. The project's percent_complete comes last.
3. A 5-minute sweeper picks up dirty sets whose job was skipped; a nightly reconcile recomputes every running project
   from scratch and reports how many values it had to correct (it should be 0).

Weights: a leaf's weight comes from the project's method (constants.ROLLUP_METHODS): its duration in days, its
task_weight, or 1. Node types that do not count (milestones) weigh 0. A group's weight is the sum of its children's,
so the project figure is the same however deep the tree is.
"""

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.services.errors import retry_on_deadlock

QUEUE = "pm"
MAX_PASSES = 5
ROLLUP_FIELDS = ("progress", "pm_rollup_weight", "exp_start_date", "exp_end_date", "status", "parent_task", "project",
                 "task_weight", "pm_node_type", "is_group")


def _key(project: str) -> str:
    return f"pm_rollup:{project}"


# --- weights ------------------------------------------------------------------------------------------------------------

def _not_counted() -> set:
    memo = getattr(frappe.local, "pm_not_counted", None)
    if memo is None:
        memo = frappe.local.pm_not_counted = set(frappe.get_all("PM Node Type", filters={"counts_in_rollup": 0}, pluck="name"))
    return memo


def leaf_weight(task, method: str) -> float:
    """Weight of a leaf task under `method` (0 for node types that do not count, e.g. milestones)."""
    if task.get("pm_node_type") and task.pm_node_type in _not_counted():
        return 0.0
    if task.get("status") == C.CANCELLED:
        return 0.0
    if method == C.ROLLUP_WEIGHT:
        return max(0.0, flt(task.get("task_weight"))) or 1.0
    if method == C.ROLLUP_EQUAL:
        return 1.0
    start, end = task.get("exp_start_date"), task.get("exp_end_date")
    if start and end:
        return float(max(1, (getdate(end) - getdate(start)).days + 1))
    return 1.0


def method_of(project: str) -> str:
    return frappe.db.get_value("Project", project, "pm_rollup_method") or C.ROLLUP_DURATION


# --- marking --------------------------------------------------------------------------------------------------------

def changed(doc) -> bool:
    """Does this save of a task matter to the roll-up?"""
    before = doc.get_doc_before_save()
    return before is None or any(before.get(f) != doc.get(f) for f in ROLLUP_FIELDS)


def mark_dirty(doc) -> None:
    """After the commit: the task's parent (and its old parent when it moved) must be recomputed."""
    project = doc.get("project")
    if not project:
        return
    parents = {doc.get("parent_task") or ""}
    before = doc.get_doc_before_save()
    if before is not None and (before.get("parent_task") or "") != (doc.get("parent_task") or ""):
        parents.add(before.get("parent_task") or "")
    if before is not None and before.get("project") and before.project != project:
        _schedule(before.project, {before.get("parent_task") or ""})
    _schedule(project, parents)


def _schedule(project: str, parents: set) -> None:
    def push():
        frappe.cache.sadd(_key(project), *parents)
        frappe.enqueue("project_manager.project_manager.services.rollup.process", queue=QUEUE, project=project,
                       job_id=f"pm-rollup:{project}", deduplicate=True, enqueue_after_commit=False)
    frappe.db.after_commit.add(push)


# --- processing -----------------------------------------------------------------------------------------------------

def process(project: str) -> int:
    """Recompute the dirty groups of a project (bottom-up) and the project itself. Returns rows written."""
    written = 0
    for _ in range(MAX_PASSES):
        members = frappe.cache.smembers(_key(project))
        if not members:
            break
        frappe.cache.srem(_key(project), *members)
        dirty = {m.decode() if isinstance(m, bytes) else m for m in members}
        try:
            written += retry_on_deadlock(lambda: _recompute(project, dirty))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.cache.sadd(_key(project), *dirty)  # the sweeper tries again
            raise
    return written


def recompute(project: str, parents) -> int:
    """Recompute `parents` (task names; "" = the project's roots) and everything above them, now."""
    return _recompute(project, set(parents))


def _recompute(project: str, dirty: set) -> int:
    method = method_of(project)
    written = _refresh_leaf_weights(project, method, {p for p in dirty if p})
    roots_dirty = "" in dirty
    level = {p for p in dirty if p}
    while level:
        groups = frappe.db.sql(
            """select name, parent_task, progress, pm_rollup_weight, exp_start_date, exp_end_date, status
               from `tabTask` where name in %(names)s""", {"names": tuple(level)}, as_dict=True)
        aggregates = _aggregate(project, [g.name for g in groups])
        parents = set()
        for group in groups:
            new = aggregates.get(group.name)
            if new is None:  # no children any more: a leaf again, nothing to aggregate
                continue
            if _differs(group, new):
                _write(group.name, new)
                written += 1
            parents.add(group.parent_task or "")
        roots_dirty = roots_dirty or "" in parents
        level = {p for p in parents if p}
    if roots_dirty or written:
        written += _write_project(project)
    return written


def _refresh_leaf_weights(project: str, method: str, parents: set) -> int:
    """Leaves under the dirty groups get their weight for the current method (cheap: indexed by parent)."""
    if not parents:
        return 0
    rows = frappe.db.sql(
        """select name, pm_node_type, status, task_weight, exp_start_date, exp_end_date, pm_rollup_weight
           from `tabTask` where project = %(project)s and parent_task in %(parents)s and is_group = 0""",
        {"project": project, "parents": tuple(parents)}, as_dict=True)
    count = 0
    for row in rows:
        weight = leaf_weight(row, method)
        if abs(flt(row.pm_rollup_weight) - weight) > 1e-9:
            frappe.db.sql("update `tabTask` set pm_rollup_weight = %s where name = %s", (weight, row.name))
            count += 1
    return count


def _aggregate(project: str, names: list) -> dict:
    """{group: values} from the direct children of each group, in one query."""
    if not names:
        return {}
    rows = frappe.db.sql(
        f"""select parent_task,
                   sum(ifnull(pm_rollup_weight, 0)) as weight,
                   sum(ifnull(pm_rollup_weight, 0) * ifnull(progress, 0)) as weighted,
                   count(*) as children,
                   min(exp_start_date) as start, max(exp_end_date) as end,
                   sum(status in ('{C.COMPLETED}', '{C.CANCELLED}')) as closed,
                   sum(status = '{C.CANCELLED}') as cancelled,
                   sum(ifnull(progress, 0) > 0 or status = '{C.WORKING}') as started
            from `tabTask` where project = %(project)s and parent_task in %(names)s group by parent_task""",
        {"project": project, "names": tuple(names)}, as_dict=True)
    out = {}
    for row in rows:
        weight = flt(row.weight)
        progress = round(flt(row.weighted) / weight, 2) if weight else (100.0 if row.closed == row.children else 0.0)
        if row.closed == row.children and row.cancelled < row.children:
            status = C.COMPLETED
            progress = 100.0
        elif row.cancelled == row.children:
            status = C.CANCELLED
        elif row.started or progress > 0:
            status = C.WORKING
        else:
            status = C.OPEN
        out[row.parent_task] = frappe._dict(progress=progress, pm_rollup_weight=weight, exp_start_date=row.start,
                                             exp_end_date=row.end, status=status)
    return out


def _same_date(a, b) -> bool:
    return (getdate(a) if a else None) == (getdate(b) if b else None)


def _differs(current, new) -> bool:
    return (abs(flt(current.progress) - new.progress) > 0.005
            or abs(flt(current.pm_rollup_weight) - new.pm_rollup_weight) > 1e-9
            or current.status != new.status
            or (new.exp_start_date and not _same_date(current.exp_start_date, new.exp_start_date))
            or (new.exp_end_date and not _same_date(current.exp_end_date, new.exp_end_date)))


def _write(name: str, new) -> None:
    values = {"progress": new.progress, "pm_rollup_weight": new.pm_rollup_weight, "status": new.status}
    if new.exp_start_date:
        values["exp_start_date"] = new.exp_start_date
    if new.exp_end_date:
        values["exp_end_date"] = new.exp_end_date
    frappe.db.set_value("Task", name, values, update_modified=False)


def _write_project(project: str) -> int:
    row = frappe.db.sql(
        """select sum(ifnull(pm_rollup_weight, 0)) as weight, sum(ifnull(pm_rollup_weight, 0) * ifnull(progress, 0)) as weighted
           from `tabTask` where project = %s and ifnull(parent_task, '') = ''""", project, as_dict=True)[0]
    percent = round(flt(row.weighted) / flt(row.weight), 2) if flt(row.weight) else 0.0
    if abs(flt(frappe.db.get_value("Project", project, "percent_complete")) - percent) <= 0.005:
        return 0
    frappe.db.set_value("Project", project, "percent_complete", percent, update_modified=False)
    return 1


# --- background jobs ------------------------------------------------------------------------------------------------

def sweep() -> int:
    """Every 5 minutes: projects with dirty groups whose job did not run (deduplicated while one was running)."""
    count = 0
    for key in frappe.cache.get_keys("pm_rollup:"):
        project = key.decode().split("pm_rollup:", 1)[1] if isinstance(key, bytes) else key.split("pm_rollup:", 1)[1]
        frappe.enqueue("project_manager.project_manager.services.rollup.process", queue=QUEUE, project=project,
                       job_id=f"pm-rollup:{project}", deduplicate=True)
        count += 1
    return count


def reconcile(project: str) -> int:
    """Recompute a whole project from its leaves upwards; returns how many values had drifted (should be 0)."""
    rows = frappe.db.sql(
        """select name, parent_task, is_group, pm_level from `tabTask` where project = %s""", project, as_dict=True)
    if not rows:
        return _write_project(project)
    groups = {r.name for r in rows if r.is_group}
    parents_of_leaves = {r.parent_task or "" for r in rows if not r.is_group}
    fixed = _refresh_leaf_weights(project, method_of(project), {p for p in parents_of_leaves if p})
    # deepest groups first, so each level aggregates children that are already right
    by_level = sorted((r for r in rows if r.name in groups), key=lambda r: -cint(r.pm_level))
    levels = {}
    for row in by_level:
        levels.setdefault(cint(row.pm_level), []).append(row.name)
    for level in sorted(levels, reverse=True):
        names = levels[level]
        aggregates = _aggregate(project, names)
        current = {g.name: g for g in frappe.db.sql(
            """select name, progress, pm_rollup_weight, exp_start_date, exp_end_date, status from `tabTask`
               where name in %(names)s""", {"names": tuple(names)}, as_dict=True)}
        for name in names:
            new = aggregates.get(name)
            if new is not None and _differs(current[name], new):
                _write(name, new)
                fixed += 1
    return fixed + _write_project(project)


def reconcile_all() -> dict:
    """Nightly: every project that is not closed. Returns {project: corrections} for the ones that drifted."""
    drifted = {}
    for project in frappe.get_all("Project", filters={"pm_state": ["not in", ["Đóng", "Hủy"]], "pm_is_template": 0},
                                  pluck="name"):
        fixed = retry_on_deadlock(lambda p=project: reconcile(p))
        frappe.db.commit()
        if fixed:
            drifted[project] = fixed
    if drifted:
        frappe.log_error(title="Rollup reconcile corrected values", message=frappe.as_json(drifted))
    return drifted


# --- overdue flags and daily snapshots ------------------------------------------------------------------------------

def overdue_state(task) -> tuple[int, int]:
    """(pm_is_overdue, pm_delay_days) of a task today."""
    end = task.get("exp_end_date")
    if not end or task.get("status") in C.CLOSED_STATUSES or flt(task.get("progress")) >= 100:
        return 0, 0
    days = (getdate(nowdate()) - getdate(end)).days
    return (1, days) if days > 0 else (0, 0)


def refresh_overdue_flags() -> int:
    """Daily (and cheap: two set-based UPDATEs): lateness of every open task as of today."""
    today = nowdate()
    frappe.db.sql(
        f"""update `tabTask` set pm_is_overdue = 1, pm_delay_days = datediff(%(today)s, date(exp_end_date))
            where exp_end_date is not null and date(exp_end_date) < %(today)s and ifnull(progress, 0) < 100
              and status not in ('{C.COMPLETED}', '{C.CANCELLED}')""", {"today": today})
    late = frappe.db.sql("select row_count()")[0][0] or 0
    frappe.db.sql(
        f"""update `tabTask` set pm_is_overdue = 0, pm_delay_days = 0
            where pm_is_overdue = 1 and (exp_end_date is null or date(exp_end_date) >= %(today)s
                  or ifnull(progress, 0) >= 100 or status in ('{C.COMPLETED}', '{C.CANCELLED}'))""", {"today": today})
    frappe.db.commit()
    return late


def planned_progress(start, end, today=None) -> float:
    """Linear plan between two dates (the baseline curve replaces this in M4)."""
    if not start or not end:
        return 0.0
    start, end, today = getdate(start), getdate(end), getdate(today or nowdate())
    if today <= start:
        return 0.0
    if today >= end:
        return 100.0
    return round((today - start).days * 100.0 / max(1, (end - start).days), 2)


def take_snapshots(day=None) -> int:
    """Daily: progress of every running project and of its top-level phases (the S-curve's history)."""
    day = getdate(day or nowdate())
    written = 0
    projects = frappe.get_all("Project", filters={"pm_state": ["not in", ["Đóng", "Hủy"]], "pm_is_template": 0},
                              fields=["name", "percent_complete", "expected_start_date", "expected_end_date"])
    for project in projects:
        counts = frappe.db.sql(
            f"""select count(*) as total, sum(status = '{C.COMPLETED}') as done, sum(pm_is_overdue = 1) as late
                from `tabTask` where project = %s and is_group = 0""", project.name, as_dict=True)[0]
        written += _snapshot(project.name, None, day, project.percent_complete,
                             planned_progress(project.expected_start_date, project.expected_end_date, day), counts)
        for phase in frappe.get_all("Task", filters={"project": project.name, "pm_level": 1},
                                    fields=["name", "progress", "exp_start_date", "exp_end_date"]):
            written += _snapshot(project.name, phase.name, day, phase.progress,
                                 planned_progress(phase.exp_start_date, phase.exp_end_date, day), None)
    frappe.db.commit()
    return written


def _snapshot(project, task, day, progress, planned, counts) -> int:
    filters = {"project": project, "task": task or ("is", "not set"), "snapshot_date": day}
    values = {"progress": flt(progress), "planned_progress": planned}
    if counts:
        values.update(total_tasks=cint(counts.total), completed_tasks=cint(counts.done), overdue_tasks=cint(counts.late))
    existing = frappe.db.get_value("PM Snapshot", filters, "name")
    if existing:
        frappe.db.set_value("PM Snapshot", existing, values, update_modified=False)
        return 0
    frappe.get_doc({"doctype": "PM Snapshot", "project": project, "task": task, "snapshot_date": day, **values}).insert(
        ignore_permissions=True)
    return 1
