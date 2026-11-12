"""Projects as the SPA shows them: the list, a project's overview, creating one (empty or from a template), its members.

A template is an ordinary project with pm_is_template = 1: its WBS is copied into the new project in a few statements
(tree.bulk_insert), its dates shifted so the template's start falls on the new project's start. Templates are not
counted as running projects (snapshots, reconcile, lists of work).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import extensions
from project_manager.project_manager.policy import (
    assert_capability,
    assert_project_capability,
    clear_cache,
    get_access,
    has_project_capability,
)
from project_manager.project_manager.services import activity, baseline, control, gates, rollup, schedule, tree
from project_manager.project_manager.services import phases as phase_gates

MANAGER_ROLE = "Quản lý dự án"
LIST_FIELDS = ["name", "project_name", "pm_code", "pm_state", "percent_complete", "expected_start_date",
               "expected_end_date", "pm_manager", "pm_is_template", "pm_rollup_method", "company", "pm_forecast_end", "pm_spi",
               "pm_health", "pm_health_reason", "pm_current_phase"]
EDITABLE = ("project_name", "pm_code", "pm_state", "expected_start_date", "expected_end_date", "pm_manager",
            "pm_rollup_method", "pm_is_template", "notes", "pm_holiday_list")
MAX_PAGE = 200


def rollup_choices() -> list[str]:
    """Ways to compute a project's progress: the core's, then those of the installed layers."""
    return [*C.ROLLUP_METHODS, *(m for m in extensions.rollup_methods() if m not in C.ROLLUP_METHODS)]


def list_projects(state: str | None = None, search: str | None = None, templates: int = 0, start: int = 0,
                  limit: int = 50) -> dict:
    filters = {"pm_is_template": 1 if cint(templates) else 0}
    if state:
        filters["pm_state"] = state
    or_filters = None
    if search:
        like = f"%{search.strip()}%"
        or_filters = {"project_name": ["like", like], "pm_code": ["like", like], "name": ["like", like]}
    limit = max(1, min(cint(limit) or 50, MAX_PAGE))
    rows = frappe.get_list("Project", filters=filters, or_filters=or_filters, fields=LIST_FIELDS,
                           order_by="modified desc", start=max(0, cint(start)), page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    names = [r.name for r in rows]
    counts = {}
    if names:
        for row in frappe.db.sql(
                f"""select project, count(*) as total, sum(status = '{C.COMPLETED}') as done,
                           sum(pm_is_overdue = 1) as late
                    from `tabTask` where project in %(names)s and is_group = 0 and status != '{C.CANCELLED}'
                    group by project""", {"names": tuple(names)}, as_dict=True):
            counts[row.project] = row
    managers = {r.pm_manager for r in rows if r.pm_manager}
    full_names = dict(frappe.get_all("User", filters={"name": ["in", list(managers)]}, fields=["name", "full_name"],
                                     as_list=True)) if managers else {}
    for row in rows:
        c = counts.get(row.name) or {}
        row["tasks"] = cint(c.get("total"))
        row["done"] = cint(c.get("done"))
        row["late"] = cint(c.get("late"))
        row["planned_progress"] = baseline.planned_on(row.name, nowdate(), rollup.planned_progress(row.expected_start_date, row.expected_end_date))
        row["manager_name"] = full_names.get(row.pm_manager)
    from project_manager.project_manager.policy import has_capability

    return {"rows": rows, "more": more, "can_create": has_capability("project.create")}


def overview(project: str) -> dict:
    doc = frappe.get_doc("Project", project)
    doc.check_permission("read")
    access = get_access()
    sees_all = access.read_tasks is None or project in access.read_tasks
    task_filter = "" if sees_all else " and " + _assigned_condition()
    leaf = frappe.db.sql(
        f"""select count(*) as total, sum(status = '{C.COMPLETED}') as done, sum(status = '{C.WORKING}') as working,
                   sum(status = '{C.REVIEW}') as review, sum(status = '{C.OPEN}') as open,
                   sum(pm_is_overdue = 1) as late,
                   sum(status not in ('{C.COMPLETED}', '{C.CANCELLED}') and exp_end_date is not null
                       and date(exp_end_date) between %(today)s and %(soon)s) as soon
            from `tabTask` t where project = %(project)s and is_group = 0 and status != '{C.CANCELLED}'{task_filter}""",
        {"project": project, "today": nowdate(), "soon": add_days(nowdate(), 7)}, as_dict=True)[0]
    phases = frappe.get_list("Task", filters={"project": project, "pm_level": 1},
                             fields=["name", "subject", "progress", "status", "exp_start_date", "exp_end_date",
                                     "pm_wbs_code", "pm_is_overdue", "is_group", "pm_health", "pm_gate_state",
                                     "pm_gate_mode", "pm_node_type"],
                             order_by="pm_sort asc", limit_page_length=50) if sees_all else []
    for phase in phases:
        phase["planned_progress"] = rollup.planned_progress(phase.exp_start_date, phase.exp_end_date)
        phase["pm_gate_mode"] = phase_gates.mode_of(phase) if phase.is_group else None  # with the node type's default
    curve = frappe.get_all("PM Snapshot", filters={"project": project, "task": ("is", "not set"),
                                                   "snapshot_date": [">=", add_days(nowdate(), -180)]},
                           fields=["snapshot_date", "progress", "planned_progress"], order_by="snapshot_date asc",
                           limit_page_length=0)
    delays = frappe.db.sql(
        f"""select ifnull(pm_delay_source, '') as source, ifnull(pm_delay_reason, '') as reason, count(*) as tasks,
                   sum(pm_delay_days) as days
            from `tabTask` t where project = %s and is_group = 0 and pm_is_overdue = 1{task_filter}
            group by pm_delay_source, pm_delay_reason order by tasks desc limit 20""", project, as_dict=True)
    pending = frappe.db.count("PM Task Assignment", {"project": project, "is_active": 1, "state": C.PENDING})
    forms_waiting = frappe.db.count("PM Form Submission", {"project": project, "state": C.SUB_SUBMITTED})
    recent = frappe.get_list("PM Activity", filters={"project": project, "is_deleted": 0},
                             fields=["name", "reference_doctype", "reference_name", "task", "activity_type", "actor",
                                     "content", "creation"], order_by="name desc", limit_page_length=20)
    _names(recent, "actor")
    tasks = {r.task for r in recent if r.task}
    labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", list(tasks)]}, fields=["name", "subject", "pm_wbs_code"])} if tasks else {}
    for row in recent:
        row["task_label"] = labels.get(row.task)
    return {
        "project": {f: doc.get(f) for f in LIST_FIELDS + ["notes", "percent_complete"]},
        "planned_progress": baseline.planned_on(project, nowdate(), rollup.planned_progress(doc.expected_start_date, doc.expected_end_date)),
        "schedule": schedule.summary(project),
        "tasks": {k: cint(v) for k, v in leaf.items()},
        "phases": phases, "curve": baseline.curve_for_chart(project, curve), "delays": delays, "pending_acceptance": pending, "forms_waiting": forms_waiting,
        "recent": recent,
        "health": {"level": doc.get("pm_health"), "reason": doc.get("pm_health_reason")},
        "gate": phase_gates.state(project) if sees_all else None,
        "alerts_open": len(frappe.get_list("PM Alert", filters={"project": project, "state": "Đang mở"}, pluck="name",
                                           limit_page_length=500)),
        "sees_all_tasks": sees_all,
        "can": {cap: has_project_capability(project, cap) for cap in
                ("project.edit", "project.members", "plan.edit", "task.assign", "task.update", "task.approve",
                 "finance.view", "budget.manage", "risk.manage", "change.request", "change.approve")},
        "control": control.summary(project) if sees_all else None,
    }


def _assigned_condition() -> str:
    from project_manager.project_manager.policy import assigned_task_sql

    return assigned_task_sql(frappe.session.user, "t.name")


def _names(rows, field: str, target: str = "actor_name") -> None:
    users = {r.get(field) for r in rows if r.get(field)}
    names = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
                                as_list=True)) if users else {}
    for row in rows:
        row[target] = names.get(row.get(field)) or row.get(field)


# --- create / change ------------------------------------------------------------------------------------------------

def _clean(values: dict) -> dict:
    values = {k: v for k, v in (values or {}).items() if k in EDITABLE}
    if "project_name" in values:
        values["project_name"] = (values["project_name"] or "").strip()
    if values.get("pm_rollup_method") and values["pm_rollup_method"] not in rollup_choices():
        frappe.throw(_("Cách tính tiến độ không hợp lệ"))
    return values


def create(values: dict, template: str | None = None) -> dict:
    """A new project; with `template`, its WBS is copied from that template project."""
    assert_capability("project.create")
    values = _clean(values)
    if not values.get("project_name"):
        frappe.throw(_("Hãy nhập tên dự án"))
    source = None
    if template:
        source = frappe.get_doc("Project", template)
        source.check_permission("read")
        if not source.pm_is_template:
            frappe.throw(_("{0} không phải dự án mẫu").format(template))
    values.setdefault("pm_manager", frappe.session.user)
    values.setdefault("pm_rollup_method", (source.pm_rollup_method if source else None)
                      or frappe.db.get_single_value("PM Settings", "default_rollup_method") or C.ROLLUP_DURATION)
    if source and values.get("expected_start_date") and not values.get("expected_end_date") \
            and source.expected_start_date and source.expected_end_date:
        values["expected_end_date"] = add_days(values["expected_start_date"],
                                               date_diff(source.expected_end_date, source.expected_start_date))
    doc = frappe.get_doc({"doctype": "Project", "company": frappe.defaults.get_global_default("company"),
                          "status": "Open", "percent_complete_method": "Manual", **values})
    doc.insert(ignore_permissions=True)
    _ensure_manager(doc.name, doc.pm_manager)
    copied = copy_wbs(source, doc) if source else 0
    activity.record("Project", doc.name, "Hệ thống", _("Tạo dự án") + (_(" từ mẫu {0}: {1} công việc").format(
        source.project_name, copied) if source else ""), data={"template": template, "tasks": copied})
    return {"name": doc.name, "tasks": copied}


def _ensure_manager(project: str, user: str | None) -> None:
    if not user or user in ("Administrator", "Guest") or not frappe.db.exists("PM Project Role", MANAGER_ROLE):
        return
    if frappe.db.exists("PM Project Member", {"project": project, "user": user, "project_role": MANAGER_ROLE}):
        return
    frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": user, "project_role": MANAGER_ROLE,
                    "is_active": 1}).insert(ignore_permissions=True)
    clear_cache()


def copy_wbs(source, target) -> int:
    """Copy the template's tasks into `target`, dates shifted by (target start − template start)."""
    rows = frappe.db.sql(
        """select name, parent_task, subject, description, is_group, priority, task_weight, exp_start_date,
                  exp_end_date, pm_node_type
           from `tabTask` where project = %s and status != %s order by pm_path""", (source.name, C.CANCELLED), as_dict=True)
    if not rows:
        return 0
    anchor = source.expected_start_date or min((r.exp_start_date for r in rows if r.exp_start_date), default=None)
    shift = date_diff(target.expected_start_date, anchor) if anchor and target.expected_start_date else 0
    known = {r.name for r in rows}
    nodes = []
    for row in rows:
        nodes.append({"key": row.name, "parent_key": row.parent_task if row.parent_task in known else None,
                      "subject": row.subject, "description": row.description, "is_group": row.is_group,
                      "priority": row.priority, "task_weight": row.task_weight, "pm_node_type": row.pm_node_type,
                      "exp_start_date": add_days(row.exp_start_date, shift) if row.exp_start_date else None,
                      "exp_end_date": add_days(row.exp_end_date, shift) if row.exp_end_date else None})
    names = tree.bulk_insert(target.name, nodes)
    copies = dict(zip((n["key"] for n in nodes), names))
    gates.copy_to(copies)
    for dep in frappe.get_all("PM Task Dependency", filters={"project": source.name},
                              fields=["predecessor", "successor", "dep_type", "lag_days"], limit_page_length=0):
        if dep.predecessor in copies and dep.successor in copies:
            frappe.get_doc({"doctype": "PM Task Dependency", "predecessor": copies[dep.predecessor], "successor": copies[dep.successor],
                            "dep_type": dep.dep_type, "lag_days": dep.lag_days}).insert(ignore_permissions=True)
    schedule.mark(target.name)
    return len(names)


def update(project: str, values: dict) -> dict:
    doc = frappe.get_doc("Project", project)
    assert_project_capability(project, "project.edit")
    values = _clean(values)
    method_before = doc.pm_rollup_method
    doc.update(values)
    doc.save(ignore_permissions=True)
    if doc.pm_manager:
        _ensure_manager(project, doc.pm_manager)
    if doc.pm_rollup_method != method_before:
        frappe.enqueue("project_manager.project_manager.services.rollup.reconcile", queue=rollup.QUEUE,
                       project=project, enqueue_after_commit=True)
    return {f: doc.get(f) for f in LIST_FIELDS}


# --- members --------------------------------------------------------------------------------------------------------

MEMBER_FIELDS = ["name", "user", "full_name", "project_role", "is_active", "valid_from", "valid_to", "note"]


def members(project: str) -> dict:
    frappe.get_doc("Project", project).check_permission("read")
    rows = frappe.get_all("PM Project Member", filters={"project": project}, fields=MEMBER_FIELDS,
                          order_by="is_active desc, project_role asc, full_name asc", limit_page_length=0)
    today = getdate(nowdate())
    for row in rows:
        row["current"] = bool(row.is_active and (not row.valid_from or getdate(row.valid_from) <= today)
                              and (not row.valid_to or getdate(row.valid_to) >= today))
    return {"rows": rows, "can_manage": has_project_capability(project, "project.members"),
            "roles": frappe.get_all("PM Project Role", pluck="name", order_by="name asc")}


def add_member(project: str, user: str, project_role: str, valid_from=None, valid_to=None, note: str = "") -> dict:
    assert_project_capability(project, "project.members")
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw(_("Tài khoản {0} không hoạt động").format(user))
    doc = frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": user, "project_role": project_role,
                          "full_name": frappe.utils.get_fullname(user), "is_active": 1, "valid_from": valid_from or None,
                          "valid_to": valid_to or None, "note": note or None})
    doc.insert(ignore_permissions=True)
    activity.record("Project", project, "Thay đổi", _("Thêm {0} vào dự án với vai trò {1}").format(
        doc.full_name or user, project_role), data={"member": doc.name})
    clear_cache()
    return doc.as_dict()


def set_member(name: str, values: dict) -> dict:
    doc = frappe.get_doc("PM Project Member", name)
    assert_project_capability(doc.project, "project.members")
    allowed = {k: v for k, v in (values or {}).items() if k in ("project_role", "is_active", "valid_from", "valid_to",
                                                                  "note")}
    if "is_active" in allowed and not cint(allowed["is_active"]) and doc.user == frappe.session.user \
            and doc.project_role == MANAGER_ROLE:
        frappe.throw(_("Không tự gỡ vai trò quản lý dự án của chính mình"))
    doc.update(allowed)
    doc.save(ignore_permissions=True)
    activity.record("Project", doc.project, "Thay đổi", _("Đổi vai trò, hiệu lực của {0}").format(doc.full_name or doc.user),
                    data={"member": doc.name, **{k: str(v) for k, v in allowed.items()}})
    clear_cache()
    return doc.as_dict()


def candidates(project: str, txt: str = "") -> list[dict]:
    """Enabled staff accounts to add to the project (search by name or e-mail)."""
    assert_project_capability(project, "project.members")
    like = f"%{(txt or '').strip()}%"
    return frappe.db.sql(
        """select name, full_name from `tabUser`
           where enabled = 1 and user_type = 'System User' and name not in ('Administrator', 'Guest')
             and (name like %(like)s or full_name like %(like)s)
           order by full_name limit 20""", {"like": like}, as_dict=True)
