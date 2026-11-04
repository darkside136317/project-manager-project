"""Views over the work: my tasks, a project's Kanban board, who does what, one task in full.

Everything here reads through the project scope: lists go through frappe.get_list (permission_query_conditions) or
add policy.project_sql / assigned_task_sql to their SQL, so a person never sees a task they could not open.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import (
    assigned_task_sql,
    get_access,
    has_project_capability,
    is_assigned,
    project_sql,
    teams_of,
)
from project_manager.project_manager.services import assignments, progress

KANBAN_LIMIT = 500
CARD_FIELDS = ["name", "subject", "status", "progress", "exp_start_date", "exp_end_date", "pm_wbs_code", "pm_accountable",
               "pm_reviewer", "pm_is_overdue", "pm_delay_days", "pm_delay_reason", "pm_node_type", "parent_task",
               "pm_last_progress_on", "priority"]


def _full_names(users) -> dict:
    users = {u for u in users if u}
    return dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
                               as_list=True)) if users else {}


def my_tasks(done: int = 0, start: int = 0, limit: int = 100) -> dict:
    """The caller's live assignments (theirs or their team's), the ones waiting for an answer first, then the late ones,
    then by deadline. `done=1` lists the finished ones instead (newest first)."""
    user = frappe.session.user
    access = get_access()
    teams = tuple(teams_of(user)) or ("",)
    limit = max(1, min(cint(limit) or 100, 200))
    if cint(done):
        state_filter, order = "a.state = %(done)s", "a.ended_on desc"
    else:
        state_filter = "a.state in %(live)s"
        order = f"(a.state = '{C.PENDING}') desc, t.pm_is_overdue desc, t.exp_end_date is null, t.exp_end_date asc"
    rows = frappe.db.sql(
        f"""select a.name as assignment, a.raci, a.state, a.team, a.assigned_by, a.assigned_on, a.note,
                   t.name, t.subject, t.status, t.progress, t.exp_start_date, t.exp_end_date, t.pm_wbs_code,
                   t.pm_is_overdue, t.pm_delay_days, t.project, t.is_group, t.pm_reviewer, p.project_name
            from `tabPM Task Assignment` a
            join `tabTask` t on t.name = a.task
            join `tabProject` p on p.name = t.project
            where a.is_active = 1 and {state_filter} and (a.user = %(user)s or a.team in %(teams)s)
              and {project_sql(access.read, 't.project') or '1=1'}
            order by {order} limit %(start)s, %(limit)s""",
        {"user": user, "teams": teams, "live": C.LIVE_STATES, "done": C.DONE, "start": max(0, cint(start)),
         "limit": limit + 1}, as_dict=True)
    more = len(rows) > limit
    rows = rows[:limit]
    names = _full_names(r.assigned_by for r in rows)
    for row in rows:
        row["status_label"] = C.STATUS_LABELS.get(row.status, row.status)
        row["assigned_by_name"] = names.get(row.assigned_by) or row.assigned_by
    counts = frappe.db.sql(
        f"""select sum(a.state = '{C.PENDING}') as pending, sum(t.pm_is_overdue = 1) as late,
                   sum(t.exp_end_date is not null and date(t.exp_end_date) between %(today)s and %(soon)s) as soon,
                   count(*) as total
            from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
            where a.is_active = 1 and a.state in %(live)s and (a.user = %(user)s or a.team in %(teams)s)
              and {project_sql(access.read, 't.project') or '1=1'}""",
        {"user": user, "teams": teams, "live": C.LIVE_STATES, "today": nowdate(), "soon": add_days(nowdate(), 2)},
        as_dict=True)[0]
    return {"rows": rows, "more": more, "counts": {k: cint(v) for k, v in counts.items()}}


def kanban(project: str, accountable: str | None = None, parent: str | None = None, search: str | None = None,
           late: int = 0) -> dict:
    """Leaf tasks of a project in their status columns (at most KANBAN_LIMIT cards)."""
    frappe.get_doc("Project", project).check_permission("read")
    filters = [["Task", "project", "=", project], ["Task", "is_group", "=", 0], ["Task", "status", "!=", C.CANCELLED]]
    if accountable:
        filters.append(["Task", "pm_accountable", "=", accountable])
    if cint(late):
        filters.append(["Task", "pm_is_overdue", "=", 1])
    if search:
        filters.append(["Task", "subject", "like", f"%{search.strip()}%"])
    if parent:
        path = frappe.db.get_value("Task", parent, "pm_path")
        if path:
            filters.append(["Task", "pm_path", "like", path.replace("%", r"\%").replace("_", r"\_") + ".%"])
    rows = frappe.get_list("Task", filters=filters, fields=CARD_FIELDS, order_by="pm_path asc",
                           limit_page_length=KANBAN_LIMIT + 1)
    more = len(rows) > KANBAN_LIMIT
    rows = rows[:KANBAN_LIMIT]
    names = _full_names(r.pm_accountable for r in rows)
    for row in rows:
        row["accountable_name"] = names.get(row.pm_accountable)
    columns = [{"status": s, "label": C.STATUS_LABELS[s]} for s in (C.OPEN, C.WORKING, C.REVIEW, C.COMPLETED)]
    return {"columns": columns, "cards": rows, "more": more,
            "can_move": has_project_capability(project, "task.update", "plan.edit", "task.assign")}


def who_does_what(project: str) -> dict:
    """Per person or team: live assignments by role, late and due-soon work, answers still awaited, last report."""
    frappe.get_doc("Project", project).check_permission("read")
    access = get_access()
    sees_all = access.read_tasks is None or project in access.read_tasks
    own = "" if sees_all else " and " + assigned_task_sql(frappe.session.user, "t.name")
    rows = frappe.db.sql(
        f"""select ifnull(a.user, '') as user, ifnull(a.team, '') as team,
                   count(*) as assignments,
                   sum(a.raci = %(a)s) as accountable, sum(a.raci = %(r)s) as responsible,
                   sum(a.state = %(pending)s) as pending,
                   sum(t.status not in %(closed)s) as open,
                   sum(t.pm_is_overdue = 1) as late,
                   sum(t.status not in %(closed)s and t.exp_end_date is not null
                       and date(t.exp_end_date) between %(today)s and %(soon)s) as soon
            from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
            where a.project = %(project)s and a.is_active = 1 and a.state in %(live)s{own}
            group by a.user, a.team order by late desc, open desc""",
        {"project": project, "a": C.ACCOUNTABLE, "r": C.RESPONSIBLE, "pending": C.PENDING, "live": C.LIVE_STATES,
         "closed": (C.COMPLETED, C.CANCELLED), "today": nowdate(), "soon": add_days(nowdate(), 7)}, as_dict=True)
    names = _full_names(r.user for r in rows)
    reported = dict(frappe.db.sql("""select reporter, max(creation) from `tabPM Progress Entry`
                                     where project = %s group by reporter""", project))
    for row in rows:
        row["who"] = _("đội {0}").format(row.team) if row.team else (names.get(row.user) or row.user)
        row["last_report"] = reported.get(row.user) if row.user else None  # their own last report in this project
        for key in ("assignments", "accountable", "responsible", "pending", "open", "late", "soon"):
            row[key] = cint(row[key])
    unassigned = frappe.db.sql(
        f"""select count(*) from `tabTask` t where t.project = %s and t.is_group = 0 and t.status not in %s
            and ifnull(t.pm_accountable, '') = ''{own}""", (project, (C.COMPLETED, C.CANCELLED)))[0][0]
    delays = frappe.db.sql(
        f"""select ifnull(t.pm_delay_source, '') as source, count(*) as tasks, sum(t.pm_delay_days) as days
            from `tabTask` t where t.project = %s and t.is_group = 0 and t.pm_is_overdue = 1{own}
            group by t.pm_delay_source order by tasks desc""", project, as_dict=True)
    return {"rows": rows, "unassigned": cint(unassigned), "delays": delays, "sees_all": sees_all}


def task_detail(task: str) -> dict:
    """One task: its fields, where it sits in the tree, who holds it, its reports and timeline, what the caller may do."""
    doc = frappe.get_doc("Task", task)
    doc.check_permission("read")
    project = doc.project
    ancestors = []
    if doc.pm_path and "." in doc.pm_path:
        parts = doc.pm_path.split(".")
        paths = [".".join(parts[:i]) for i in range(1, len(parts))]
        ancestors = frappe.db.sql("""select name, subject, pm_wbs_code from `tabTask`
                                     where project = %s and pm_path in %s order by pm_path""", (project, tuple(paths)),
                                  as_dict=True)
    fields = ["name", "subject", "description", "status", "progress", "is_group", "exp_start_date", "exp_end_date",
              "act_start_date", "act_end_date", "pm_wbs_code", "pm_level", "pm_node_type", "pm_accountable",
              "pm_reviewer", "pm_is_overdue", "pm_delay_days", "pm_delay_reason", "pm_delay_source", "pm_delay_note",
              "pm_last_progress_on", "priority", "task_weight", "pm_rollup_weight", "parent_task", "project"]
    data = {f: doc.get(f) for f in fields}
    data["status_label"] = C.STATUS_LABELS.get(doc.status, doc.status)
    data["project_name"] = frappe.db.get_value("Project", project, "project_name") if project else None
    names = _full_names([doc.pm_accountable, doc.pm_reviewer])
    data["accountable_name"] = names.get(doc.pm_accountable)
    data["reviewer_name"] = names.get(doc.pm_reviewer)
    timeline = frappe.get_list("PM Activity", filters={"reference_doctype": "Task", "reference_name": task,
                                                       "is_deleted": 0},
                               fields=["name", "activity_type", "actor", "content", "creation", "data"],
                               order_by="name desc", limit_page_length=50)
    actor_names = _full_names(r.actor for r in timeline)
    for row in timeline:
        row["actor_name"] = actor_names.get(row.actor) or row.actor
    can_write = frappe.has_permission("Task", "write", doc=doc)
    may = lambda *caps: bool(project) and has_project_capability(project, *caps)  # noqa: E731
    return {
        "task": data, "ancestors": ancestors, "assignments": assignments.of_task(task),
        "reports": progress.history(task, 20), "timeline": timeline,
        "children": frappe.db.count("Task", {"parent_task": task}),
        "can": {
            "update": bool(can_write and not doc.is_group and may(*progress.UPDATE_CAPABILITIES)),
            "plan": may("plan.edit"), "assign": may("task.assign"),
            "dates": may("plan.edit", "task.assign"),
            "review": doc.status == C.REVIEW and (doc.pm_reviewer == frappe.session.user or may("task.approve")),
        },
        "mine": is_assigned(task),
        "delay_reasons": frappe.get_all("PM Delay Reason", filters={"is_active": 1}, pluck="name",
                                        order_by="sort_order asc, name asc"),
        "delay_sources": frappe.get_all("PM Delay Source", filters={"is_active": 1}, pluck="name",
                                        order_by="sort_order asc, name asc"),
        "raci_roles": list(C.RACI_ROLES),
    }
