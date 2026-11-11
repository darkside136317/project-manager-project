"""Frappe permission hooks: the project scope of policy.py applied to every list query and every document check.

* `permission_query_conditions` — SQL appended to every list query (get_list, reports, /api/resource, link search).
* `has_permission` — single-document checks. Frappe v16: a falsy result (None included) DENIES; True defers to DocPerm.

DocPerm still decides what a role may do with a kind of data; these hooks narrow it to the user's projects, to the
tasks they may see (a member whose role sees "Chỉ việc được giao" sees only the tasks assigned to them or to their
team), and, for structural changes, to the capability their project role gives. Administrators are never narrowed.
"""

import frappe

from project_manager.project_manager.policy import (
    can_see_task,
    get_access,
    has_capability,
    has_project_capability,
    project_in,
    project_sql,
    task_sql,
)

READ_LIKE = frozenset({"read", "print", "export", "report", "email", "share", "select"})


def project_of(doc) -> str | None:
    """The project a record belongs to (None for a project that does not exist yet)."""
    if doc.doctype == "Project":
        return None if doc.is_new() else doc.name
    if doc.get("project"):
        return doc.project
    if doc.doctype == "Task" and doc.get("parent_task"):
        return frappe.db.get_value("Task", doc.parent_task, "project")
    if doc.get("task"):
        return frappe.db.get_value("Task", doc.task, "project")
    return None


# --- query conditions -------------------------------------------------------------------------------------------------

def _query(user, column: str) -> str:
    access = get_access(user)
    if access.kind == "admin":
        return ""
    return project_sql(access.read, column)


def _task_query(user, table: str, task_column: str) -> str:
    access = get_access(user)
    if access.kind == "admin":
        return ""
    return task_sql(access, f"`{table}`.`{task_column}`", f"`{table}`.`project`")


def project_query(user):
    return _query(user, "`tabProject`.`name`")


def task_query(user):
    return _task_query(user, "tabTask", "name")


def project_member_query(user):
    return _query(user, "`tabPM Project Member`.`project`")


def entry_sql(access, table: str) -> str:
    """Rows that may belong to a task (timeline entries, photos, documents): the task's visibility when they do,
    the project's read scope when they do not."""
    tasks = task_sql(access, f"`{table}`.`task`", f"`{table}`.`project`")
    projects = project_sql(access.read, f"`{table}`.`project`")
    if not tasks and not projects:
        return ""
    without = f"`{table}`.`task` IS NULL" + (f" AND {projects}" if projects else "")
    within = f"`{table}`.`task` IS NOT NULL" + (f" AND {tasks}" if tasks else "")
    return f"(({without}) OR ({within}))"


def _entry_query(user, table: str) -> str:
    access = get_access(user)
    if access.kind == "admin":
        return ""
    return entry_sql(access, table)


def activity_query(user):
    return _entry_query(user, "tabPM Activity")


def media_query(user):
    return _entry_query(user, "tabPM Media")


def document_query(user):
    return _entry_query(user, "tabPM Document")


def document_version_query(user):
    return _entry_query(user, "tabPM Document Version")


def follow_query(user):
    """Each user sees only what they follow."""
    access = get_access(user)
    if access.kind == "admin":
        return ""
    return f"`tabPM Follow`.`user` = {frappe.db.escape(access.user)}"


def snapshot_query(user):
    return _query(user, "`tabPM Snapshot`.`project`")


def assignment_query(user):
    return _task_query(user, "tabPM Task Assignment", "task")


def progress_entry_query(user):
    return _task_query(user, "tabPM Progress Entry", "task")


def gate_query(user):
    return _task_query(user, "tabPM Gate Requirement", "task")


def dependency_query(user):
    return _task_query(user, "tabPM Task Dependency", "successor")


def baseline_query(user):
    return _query(user, "`tabPM Baseline`.`project`")


def baseline_task_query(user):
    return _task_query(user, "tabPM Baseline Task", "task")


def baseline_curve_query(user):
    return _query(user, "`tabPM Baseline Curve`.`project`")


def form_submission_query(user):
    """Forms of the tasks the user sees, and always the user's own (a project-level form has no task)."""
    access = get_access(user)
    if access.kind == "admin":
        return ""
    table = "`tabPM Form Submission`"
    scoped = task_sql(access, f"{table}.`task`", f"{table}.`project`")
    if not scoped:
        return ""
    own = f"{table}.`owner` = {frappe.db.escape(access.user)}"
    projects = project_sql(access.read, f"{table}.`project`")
    return f"({scoped} OR ({own}{' AND ' + projects if projects else ''}))"


# --- has_permission ---------------------------------------------------------------------------------------------------

def _scoped(doc, user, ptype) -> bool:
    """Reading within the read scope, everything else within the write scope."""
    user = user or frappe.session.user
    access = get_access(user)
    if access.kind == "admin":
        return True
    if access.kind == "guest":
        return False
    project = project_of(doc)
    return project_in(access.read if ptype in READ_LIKE else access.write, project)


def _task_scoped(doc, user, ptype, task: str | None) -> bool:
    """Rows of a task: the user must see that task; changes need the write scope of its project too."""
    user = user or frappe.session.user
    access = get_access(user)
    if access.kind == "admin":
        return True
    if access.kind == "guest":
        return False
    project = project_of(doc)
    if task and not can_see_task(task, project, user):
        return False
    if not task and not project_in(access.read_tasks, project):
        return False  # a new task: only where the user sees every task
    return ptype in READ_LIKE or project_in(access.write, project)


def has_project_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if get_access(user).kind == "admin":
        return True
    if doc.is_new() or ptype == "create":
        return has_capability("project.create", user=user)
    if ptype == "delete":
        return False  # only administrators delete a project (with everything in it)
    if ptype not in READ_LIKE and not has_project_capability(doc.name, "project.edit", user=user):
        return False
    return _scoped(doc, user, ptype)


def has_task_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if not _task_scoped(doc, user, ptype, None if doc.is_new() else doc.name):
        return False
    if ptype in ("create", "delete") and get_access(user).kind != "admin":
        return has_project_capability(project_of(doc), "plan.edit", user=user)
    return True


def has_project_member_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if not _scoped(doc, user, ptype):
        return False
    if ptype not in READ_LIKE and get_access(user).kind != "admin":
        return has_project_capability(doc.project, "project.members", user=user)
    return True


def _read_only(scope_check):
    """Rows the services write (ignore_permissions); through the API they can only be read."""
    def check(doc, ptype="read", user=None):
        return ptype in READ_LIKE and scope_check(doc, ptype, user)
    return check


def _entry_scoped(doc, user, ptype) -> bool:
    task = doc.get("task")
    return _task_scoped(doc, user, ptype, task) if task else _scoped(doc, user, ptype)


def _own_follow(doc, user) -> bool:
    user = user or frappe.session.user
    return get_access(user).kind == "admin" or doc.user == user


has_activity_permission = _read_only(lambda doc, ptype, user: _entry_scoped(doc, user, ptype))
has_media_permission = _read_only(lambda doc, ptype, user: _entry_scoped(doc, user, ptype))
has_document_permission = _read_only(lambda doc, ptype, user: _entry_scoped(doc, user, ptype))
has_document_version_permission = _read_only(lambda doc, ptype, user: _entry_scoped(doc, user, ptype))
has_follow_permission = _read_only(lambda doc, ptype, user: _own_follow(doc, user))
has_snapshot_permission = _read_only(lambda doc, ptype, user: _scoped(doc, user, ptype))
has_assignment_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))
has_progress_entry_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))
has_gate_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))
has_dependency_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.successor))
has_baseline_permission = _read_only(lambda doc, ptype, user: _scoped(doc, user, ptype))
has_baseline_task_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))
has_baseline_curve_permission = _read_only(lambda doc, ptype, user: _scoped(doc, user, ptype))


def _form_scoped(doc, ptype, user) -> bool:
    if _task_scoped(doc, user, ptype, doc.task):
        return True
    user = user or frappe.session.user
    return doc.owner == user and project_in(get_access(user).read, doc.project)


has_form_submission_permission = _read_only(lambda doc, ptype, user: _form_scoped(doc, ptype, user))


# --- for industry layers ------------------------------------------------------------------------------------------------
# A layer's DocTypes with a `project` (and maybe a `task`) column use these in its own hooks.py, the same way the
# core's do.

def scope_condition(user, doctype: str) -> str:
    """Rows of the projects the user may read."""
    return _query(user, f"`tab{doctype}`.`project`")


def entry_condition(user, doctype: str) -> str:
    """Rows tied to a task follow the task's visibility, the rest the project's."""
    return _entry_query(user, f"tab{doctype}")


def scoped(doc, ptype="read", user=None) -> bool:
    """Read within the read scope, change within the write scope."""
    return _scoped(doc, user, ptype)


def entry_scoped(doc, ptype="read", user=None) -> bool:
    return _entry_scoped(doc, user, ptype)


read_only = _read_only


def alert_query(user):
    return _entry_query(user, "tabPM Alert")


def preference_query(user):
    """Each person sees their own notification choices."""
    access = get_access(user)
    if access.kind == "admin":
        return ""
    return f"`tabPM Notification Preference`.`user` = {frappe.db.escape(access.user)}"


has_alert_permission = _read_only(lambda doc, ptype, user: _entry_scoped(doc, user, ptype))
has_preference_permission = _read_only(lambda doc, ptype, user: get_access(user).kind == "admin"
                                       or doc.user == (user or frappe.session.user))


# --- ERPNext's stock and buying documents (M8) --------------------------------------------------------------------------------
# A store keeper of project A works with A's site store, A's requests and stock entries, not B's. Moving stock between
# two stores needs the right on both. Not narrowed: administrators, people outside the app (ERPNext's own role rules
# apply), holders of stock.cross_project (and of finance.view_all for the buying documents).

def _stock_free(user, doctype) -> bool:
    from project_manager.project_manager import constants as C
    from project_manager.project_manager.policy import is_staff

    if not is_staff(user) or get_access(user).kind == "admin":
        return True
    codes = ("stock.cross_project", "finance.view_all") if doctype in C.BUYING_SCOPED else ("stock.cross_project",)
    return has_capability(*codes, user=user)


def stock_query(user, doctype=None):
    from project_manager.project_manager import constants as C

    user = user or frappe.session.user
    if not doctype or doctype not in C.STOCK_SCOPED or _stock_free(user, doctype):
        return ""
    return project_sql(get_access(user).read, f"`tab{doctype}`.`{C.STOCK_SCOPED[doctype]}`")


WAREHOUSE_FIELDS = ("from_warehouse", "to_warehouse", "set_warehouse", "set_from_warehouse", "s_warehouse", "t_warehouse",
                    "warehouse", "rejected_warehouse")


def stores_of(doc) -> set:
    """Every warehouse a document moves stock in or out of (its header and its rows)."""
    found = {doc.get(f) for f in WAREHOUSE_FIELDS}
    for row in doc.get("items") or []:
        found |= {row.get(f) for f in WAREHOUSE_FIELDS}
    return {w for w in found if w}


def has_stock_permission(doc, ptype="read", user=None):
    from project_manager.project_manager import constants as C

    user = user or frappe.session.user
    if doc.doctype not in C.STOCK_SCOPED or _stock_free(user, doc.doctype):
        return True
    project = doc.get(C.STOCK_SCOPED[doc.doctype])
    if ptype in READ_LIKE:
        return bool(project) and project_in(get_access(user).read, project)
    needed = ("material.request", "stock.manage") if doc.doctype == "Material Request" else ("stock.manage",)
    projects = {project}
    if doc.doctype != "Warehouse":
        stores = stores_of(doc)
        owners = dict(frappe.get_all("Warehouse", filters={"name": ["in", list(stores)]}, fields=["name", "pm_project"],
                                     as_list=True)) if stores else {}
        projects |= {owners.get(store) for store in stores}  # a store of no project (the main store) is not theirs
    return all(p and has_project_capability(p, *needed, user=user) for p in projects)

