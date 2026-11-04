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


def activity_query(user):
    return _query(user, "`tabPM Activity`.`project`")


def snapshot_query(user):
    return _query(user, "`tabPM Snapshot`.`project`")


def assignment_query(user):
    return _task_query(user, "tabPM Task Assignment", "task")


def progress_entry_query(user):
    return _task_query(user, "tabPM Progress Entry", "task")


def gate_query(user):
    return _task_query(user, "tabPM Gate Requirement", "task")


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


has_activity_permission = _read_only(lambda doc, ptype, user: _scoped(doc, user, ptype))
has_snapshot_permission = _read_only(lambda doc, ptype, user: _scoped(doc, user, ptype))
has_assignment_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))
has_progress_entry_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))
has_gate_permission = _read_only(lambda doc, ptype, user: _task_scoped(doc, user, ptype, doc.task))


def _form_scoped(doc, ptype, user) -> bool:
    if _task_scoped(doc, user, ptype, doc.task):
        return True
    user = user or frappe.session.user
    return doc.owner == user and project_in(get_access(user).read, doc.project)


has_form_submission_permission = _read_only(lambda doc, ptype, user: _form_scoped(doc, ptype, user))
