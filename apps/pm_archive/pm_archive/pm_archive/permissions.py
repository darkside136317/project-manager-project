"""Who sees the archive files of a project (and their items).

* The archivist (archive.manage_all) and whoever may see every archive (archive.view_all, the director by default)
  see all of them, member of the project or not, the project closed or not.
* A member sees the files of the projects where a role of theirs holds archive.view (or archive.manage), except the
  restricted ones (Hạn chế), which only archive.manage there shows.
* Through the generic API these rows are only read: the services write them.
"""

import frappe
from project_manager.project_manager import permissions as core
from project_manager.project_manager.policy import (
    get_access,
    has_capability,
    has_project_capability,
    memberships,
    project_in,
    project_sql,
)

from pm_archive.pm_archive import constants as A


def sees_everything(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return get_access(user).kind == "admin" or has_capability(A.VIEW_ALL, A.MANAGE_ALL, user=user)


def manages_everything(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return get_access(user).kind == "admin" or has_capability(A.MANAGE_ALL, user=user)


def readable_projects(user: str | None = None):
    """None: every project's archive; else the projects whose (unrestricted) files the user reads."""
    user = user or frappe.session.user
    if sees_everything(user):
        return None
    return {p for p in memberships(user) if has_project_capability(p, A.VIEW, A.MANAGE, user=user)}


def managed_projects(user: str | None = None):
    """None: every project; else the projects where the user builds the files (archive.manage)."""
    user = user or frappe.session.user
    if manages_everything(user):
        return None
    return {p for p in memberships(user) if has_project_capability(p, A.MANAGE, user=user)}


def may_read(project: str, access_mode: str | None, user: str | None = None) -> bool:
    user = user or frappe.session.user
    if sees_everything(user):
        return True
    if project_in(managed_projects(user), project):
        return True
    return access_mode != A.RESTRICTED and project_in(readable_projects(user), project)


def may_manage(project: str, user: str | None = None) -> bool:
    return project_in(managed_projects(user), project)


def file_condition(user: str | None = None, table: str = "`tabPM Archive File`") -> str:
    """SQL: the files the user reads ("" for all)."""
    user = user or frappe.session.user
    if sees_everything(user):
        return ""
    read, manage = readable_projects(user), managed_projects(user)
    parts = []
    if read:
        parts.append(f"({table}.access_mode != {frappe.db.escape(A.RESTRICTED)} and {project_sql(read, f'{table}.project')})")
    if manage:
        parts.append(project_sql(manage, f"{table}.project"))
    return f"({' or '.join(parts)})" if parts else "1=0"


def archive_file_query(user):
    return file_condition(user)


def archive_item_query(user):
    condition = file_condition(user, "f")
    if not condition:
        return ""
    return f"`tabPM Archive Item`.archive_file in (select f.name from `tabPM Archive File` f where {condition})"


def _file_check(doc, ptype, user):
    return may_read(doc.project, doc.access_mode, user)


def _item_check(doc, ptype, user):
    mode = frappe.db.get_value("PM Archive File", doc.archive_file, "access_mode")
    return may_read(doc.project, mode, user)


has_archive_file_permission = core.read_only(_file_check)
has_archive_item_permission = core.read_only(_item_check)
