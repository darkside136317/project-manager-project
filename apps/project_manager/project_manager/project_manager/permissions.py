"""Frappe permission hooks: the project scope of policy.py applied to every list query and every document check.

* `permission_query_conditions` — SQL appended to every list query (get_list, reports, /api/resource, link search).
* `has_permission` — single-document checks. Frappe v16: a falsy result (None included) DENIES; True defers to DocPerm.

DocPerm still decides what a role may do with a kind of data; these hooks narrow it to the user's projects and,
for structural changes, to the capability their project role gives (creating a project, managing members, ...).
Administrators are never narrowed.
"""

import frappe

from project_manager.project_manager.policy import (
    get_access,
    has_capability,
    has_project_capability,
    project_in,
    project_sql,
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
    return None


# --- query conditions -------------------------------------------------------------------------------------------------

def _query(user, column: str, tasks: bool = False) -> str:
    access = get_access(user)
    if access.kind == "admin":
        return ""
    return project_sql(access.read_tasks if tasks else access.read, column)


def project_query(user):
    return _query(user, "`tabProject`.`name`")


def task_query(user):
    return _query(user, "`tabTask`.`project`", tasks=True)


def project_member_query(user):
    return _query(user, "`tabPM Project Member`.`project`")


def activity_query(user):
    return _query(user, "`tabPM Activity`.`project`")


# --- has_permission ---------------------------------------------------------------------------------------------------

def _scoped(doc, user, ptype, tasks: bool = False) -> bool:
    """Reading within the read scope, everything else within the write scope."""
    user = user or frappe.session.user
    access = get_access(user)
    if access.kind == "admin":
        return True
    if access.kind == "guest":
        return False
    project = project_of(doc)
    if ptype in READ_LIKE:
        return project_in(access.read_tasks if tasks else access.read, project)
    return project_in(access.write, project)


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
    if not _scoped(doc, user, ptype, tasks=True):
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


def has_activity_permission(doc, ptype="read", user=None):
    # The timeline is written by the services (ignore_permissions); through the API it is read-only.
    return ptype in READ_LIKE and _scoped(doc, user, ptype)
