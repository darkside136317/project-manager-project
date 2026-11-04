"""Who may see and do what — the single source of truth for access.

`get_access(user)` answers, for one user, in one object:

    kind          "admin" | "user" | "guest"
    read          None for every project, else the set of projects the user may see
    read_tasks    the same for the tasks inside them (None = every project's tasks); projects where the user's only
                  roles see "Chỉ việc được giao" are left out of it and listed in `assigned_only`
    assigned_only projects where the user sees only the tasks assigned to them or to one of their teams
    write         None for every project, else the set of projects whose data the user may change
    capabilities  frozenset of global capability codes (permission groups)

`capabilities_in(project, user)` gives the capabilities inside one project (project roles). The query conditions and
`has_permission` hooks (permissions.py), the APIs and the search all consume these, so a rule changes in exactly one
place. Within a request the answers are memoised; saving a permission group, a scope or a membership clears the memo.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from project_manager.project_manager import constants as C

ADMIN_ROLES = frozenset({C.ADMIN_ROLE, "System Manager", "Administrator"})


# --- per-request memo -------------------------------------------------------------------------------------------------
# frappe.local is new for every request and job; a test process keeps it, so every writer of the facts below clears it.

def _memo() -> dict:
    memo = getattr(frappe.local, "pm_policy_memo", None)
    if memo is None:
        memo = frappe.local.pm_policy_memo = {}
    return memo


def clear_cache() -> None:
    frappe.local.pm_policy_memo = {}


# --- permission groups (global) ---------------------------------------------------------------------------------------

def _profile_capabilities() -> dict:
    """{role: frozenset(capabilities)} of every permission group (the built-in defaults before the groups exist)."""
    memo = _memo()
    if "profiles" not in memo:
        profiles = {role: frozenset(caps) for role, caps in C.BUILTIN_CAPABILITIES.items()}
        if frappe.db.table_exists("PM Role Profile"):
            granted = {}
            for row in frappe.get_all("PM Role Capability", filters={"parenttype": "PM Role Profile"},
                                      fields=["parent", "capability"], limit_page_length=0):
                granted.setdefault(row.parent, set()).add(row.capability)
            for role in frappe.get_all("PM Role Profile", pluck="name", limit_page_length=0):
                profiles[role] = frozenset(granted.get(role, ()))
        memo["profiles"] = profiles
    return memo["profiles"]


def role_profiles() -> list[dict]:
    """The permission groups that can be given to a user, the built-in ones first:
    [{role, label, group, description, is_builtin, is_admin}]."""
    memo = _memo()
    if "profile_rows" not in memo:
        rows = []
        if frappe.db.table_exists("PM Role Profile"):
            rows = frappe.get_all("PM Role Profile", fields=["role", "label", "group_label", "description", "is_builtin",
                                                             "is_admin"], limit_page_length=0)
        known = {r.role for r in rows}
        rows += [frappe._dict(role=role, label=info["label"], group_label=info["group"], description=info["description"],
                              is_builtin=1, is_admin=int(role == C.ADMIN_ROLE))
                 for role, info in C.ROLE_INFO.items() if role not in known]
        order = {role: i for i, role in enumerate(C.ASSIGNABLE_ROLES)}
        rows.sort(key=lambda r: (order.get(r.role, len(order)), r.label or r.role))
        memo["profile_rows"] = [{"role": r.role, "label": r.label or r.role, "group": r.group_label or "Tác nghiệp",
                                 "description": r.description or "", "is_builtin": bool(r.is_builtin),
                                 "is_admin": bool(r.is_admin)} for r in rows]
    return memo["profile_rows"]


def assignable_roles() -> tuple:
    """The roles the app may give to a user: every permission group (never System Manager / Administrator)."""
    return tuple(p["role"] for p in role_profiles())


def is_staff(user: str | None = None) -> bool:
    """A user of the app: an administrator, or a holder of one of its permission groups."""
    user = user or frappe.session.user
    if user == "Guest":
        return False
    return is_admin(user) or bool(set(assignable_roles()).intersection(frappe.get_roles(user)))


def is_admin(user: str | None = None) -> bool:
    """Administrators of the application: every capability, every project."""
    user = user or frappe.session.user
    return user == "Administrator" or bool(ADMIN_ROLES.intersection(frappe.get_roles(user)))


def capabilities_of(user: str | None = None) -> frozenset:
    """Global capabilities: every one for an administrator, else the union of the user's permission groups."""
    user = user or frappe.session.user
    if is_admin(user):
        return C.CAPABILITY_CODES | C.ADMIN_ONLY_CAPABILITIES
    profiles = _profile_capabilities()
    granted = set()
    for role in frappe.get_roles(user):
        granted |= profiles.get(role, frozenset())
    return frozenset(granted)


def has_capability(*codes: str, user: str | None = None) -> bool:
    """True when `user` may use at least one of `codes` (global capabilities)."""
    return bool(capabilities_of(user).intersection(codes))


def assert_capability(*codes: str, user: str | None = None) -> None:
    """Raise PermissionError unless `user` may use one of `codes` (also enforced while tests run)."""
    if not has_capability(*codes, user=user):
        frappe.throw(_("Bạn không có quyền thực hiện thao tác này"), frappe.PermissionError)


def users_with_capability(code: str) -> list[str]:
    """Enabled users whose permission groups grant `code` explicitly (administrators hold everything implicitly and
    are not listed)."""
    roles = [role for role, caps in _profile_capabilities().items() if code in caps]
    if not roles:
        return []
    holders = frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent", distinct=True)
    if not holders:
        return []
    return frappe.get_all("User", filters={"name": ["in", holders], "enabled": 1}, pluck="name")


# --- project roles and memberships ------------------------------------------------------------------------------------

def project_roles() -> dict:
    """{role_name: _dict(capabilities, assigned_only, writes)} of every PM Project Role."""
    memo = _memo()
    if "project_roles" not in memo:
        roles = {}
        if frappe.db.table_exists("PM Project Role"):
            caps = {}
            for row in frappe.get_all("PM Role Capability", filters={"parenttype": "PM Project Role"},
                                      fields=["parent", "capability"], limit_page_length=0):
                caps.setdefault(row.parent, set()).add(row.capability)
            for row in frappe.get_all("PM Project Role", fields=["name", "task_visibility"], limit_page_length=0):
                granted = frozenset(caps.get(row.name, ()))
                roles[row.name] = frappe._dict(capabilities=granted,
                                               assigned_only=row.task_visibility == C.VISIBILITY_ASSIGNED,
                                               writes=bool(granted & C.WRITE_PROJECT_CAPABILITIES))
        memo["project_roles"] = roles
    return memo["project_roles"]


def memberships(user: str) -> dict:
    """{project: set(project roles)} of the user's memberships active today."""
    memo = _memo().setdefault("memberships", {})
    if user not in memo:
        result = {}
        if frappe.db.table_exists("PM Project Member"):
            today = getdate(nowdate())
            for row in frappe.get_all("PM Project Member", filters={"user": user, "is_active": 1},
                                      fields=["project", "project_role", "valid_from", "valid_to"], limit_page_length=0):
                if row.valid_from and getdate(row.valid_from) > today:
                    continue
                if row.valid_to and getdate(row.valid_to) < today:
                    continue
                result.setdefault(row.project, set()).add(row.project_role)
        memo[user] = result
    return memo[user]


# --- project scope ----------------------------------------------------------------------------------------------------

def _granted_scopes(user: str) -> list[frappe._dict]:
    """The user's PM Access and every PM Group of theirs that sets a scope, with the projects they choose."""
    if not frappe.db.table_exists("PM Access"):
        return []
    sources = []
    personal = frappe.db.get_value("PM Access", {"user": user}, ["name", "read_scope", "write_scope"], as_dict=True)
    if personal:
        sources.append(("PM Access", personal))
    groups = frappe.get_all("PM Group Member", filters={"user": user, "parenttype": "PM Group"}, pluck="parent")
    if groups:
        for group in frappe.get_all("PM Group", filters={"name": ["in", groups], "apply_scope": 1},
                                    fields=["name", "read_scope", "write_scope"]):
            sources.append(("PM Group", group))
    if not sources:
        return []
    chosen = {}
    for row in frappe.get_all("PM Access Project", fields=["parenttype", "parent", "parentfield", "project"],
                              filters={"parent": ["in", [src.name for _dt, src in sources]],
                                       "parenttype": ["in", ["PM Access", "PM Group"]]}, limit_page_length=0):
        chosen.setdefault((row.parenttype, row.parent, row.parentfield), set()).add(row.project)
    return [frappe._dict(read_scope=src.read_scope or C.READ_MEMBER, write_scope=src.write_scope or C.WRITE_MEMBER,
                         read_projects=chosen.get((doctype, src.name, "read_projects"), set()),
                         write_projects=chosen.get((doctype, src.name, "write_projects"), set()))
            for doctype, src in sources]


def get_access(user: str | None = None) -> frappe._dict:
    """See the module docstring."""
    user = user or frappe.session.user
    memo = _memo().setdefault("access", {})
    if user in memo:
        return memo[user]
    if user == "Guest":
        access = frappe._dict(user=user, kind="guest", read=set(), read_tasks=set(), assigned_only=set(), write=set(),
                              granted_write=set(), capabilities=frozenset())
    elif is_admin(user):
        access = frappe._dict(user=user, kind="admin", read=None, read_tasks=None, assigned_only=set(), write=None,
                              granted_write=set(), capabilities=capabilities_of(user))
    else:
        roles = project_roles()
        member = memberships(user)
        read = set(member)
        read_tasks = {p for p, names in member.items() if any(not roles.get(n, frappe._dict()).assigned_only for n in names)}
        write = {p for p, names in member.items() if any(roles.get(n, frappe._dict()).writes for n in names)}
        granted_write = set()
        read_all = has_capability("portfolio.view_all", user=user)
        write_all = False
        for scope in _granted_scopes(user):
            if scope.read_scope == C.READ_ALL:
                read_all = True
            elif scope.read_scope == C.READ_CHOSEN:
                read |= scope.read_projects
                read_tasks |= scope.read_projects
            if scope.write_scope == C.WRITE_SAME:
                if scope.read_scope == C.READ_ALL:
                    write_all = True
                elif scope.read_scope == C.READ_CHOSEN:
                    granted_write |= scope.read_projects
            elif scope.write_scope == C.WRITE_CHOSEN:
                granted_write |= scope.write_projects
        write |= granted_write
        access = frappe._dict(user=user, kind="user",
                              read=None if read_all else read,
                              read_tasks=None if read_all else read_tasks,
                              assigned_only=set() if read_all else read - read_tasks,
                              write=None if write_all else write,
                              granted_write=granted_write,
                              capabilities=capabilities_of(user))
        if write_all:
            access.granted_write = None
    memo[user] = access
    return access


def teams_of(user: str | None = None) -> set:
    """The active teams `user` belongs to (work given to a team is theirs too)."""
    user = user or frappe.session.user
    memo = _memo().setdefault("teams", {})
    if user not in memo:
        teams = set()
        if frappe.db.table_exists("PM Team Member"):
            names = frappe.get_all("PM Team Member", filters={"user": user, "parenttype": "PM Team"}, pluck="parent")
            if names:
                teams = set(frappe.get_all("PM Team", filters={"name": ["in", names], "is_active": 1}, pluck="name"))
        memo[user] = teams
    return memo[user]


def assigned_task_sql(user: str, task_column: str) -> str:
    """SQL condition: the task in `task_column` is actively assigned to `user` or to one of their teams."""
    owners = [f"`a`.`user` = {frappe.db.escape(user)}"]
    teams = teams_of(user)
    if teams:
        owners.append(f"`a`.`team` IN ({', '.join(frappe.db.escape(t) for t in sorted(teams))})")
    return (f"{task_column} IN (SELECT `a`.`task` FROM `tabPM Task Assignment` `a` WHERE `a`.`is_active` = 1 "
            f"AND `a`.`state` IN ('{C.PENDING}', '{C.ACCEPTED}', '{C.DONE}') AND ({' OR '.join(owners)}))")


def is_assigned(task: str, user: str | None = None) -> bool:
    """Is `task` actively assigned to `user` or to one of their teams?"""
    user = user or frappe.session.user
    filters = {"task": task, "is_active": 1, "state": ["in", [C.PENDING, C.ACCEPTED, C.DONE]]}
    if frappe.db.exists("PM Task Assignment", {**filters, "user": user}):
        return True
    teams = teams_of(user)
    return bool(teams) and bool(frappe.db.exists("PM Task Assignment", {**filters, "team": ["in", list(teams)]}))


def task_sql(access, task_column: str, project_column: str) -> str:
    """SQL condition limiting rows that belong to a task to the tasks the user may see ("" = every task)."""
    full = project_sql(access.read_tasks, project_column)
    if not access.assigned_only:
        return full
    assigned = (f"({project_sql(access.assigned_only, project_column)} AND "
                f"{assigned_task_sql(access.user, task_column)})")
    if access.read_tasks is not None and not access.read_tasks:
        return assigned
    return f"({full} OR {assigned})"


def can_see_task(task: str, project: str | None, user: str | None = None) -> bool:
    access = get_access(user)
    if access.kind == "admin" or project_in(access.read_tasks, project):
        return True
    return bool(project) and project in access.assigned_only and is_assigned(task, access.user)


def project_in(allowed, project) -> bool:
    """Is `project` within `allowed` (None = every project)?"""
    return allowed is None or (bool(project) and project in allowed)


def project_sql(allowed, column: str) -> str:
    """SQL condition limiting `column` to `allowed` ("" for every project, "1=0" for none)."""
    if allowed is None:
        return ""
    if not allowed:
        return "1=0"
    return f"{column} IN ({', '.join(frappe.db.escape(p) for p in sorted(allowed))})"


def capabilities_in(project: str, user: str | None = None) -> frozenset:
    """Capabilities of `user` inside `project`: their project roles there, everything for administrators, the write
    capabilities when a scope (not a membership) lets them change the project, and the project-level side of the
    global capabilities (seeing every performance or every cost covers this project's)."""
    user = user or frappe.session.user
    access = get_access(user)
    if access.kind == "admin":
        return C.PROJECT_CAPABILITY_CODES
    if access.kind == "guest" or not project:
        return frozenset()
    roles = project_roles()
    granted = set()
    for name in memberships(user).get(project, ()):
        granted |= roles.get(name, frappe._dict(capabilities=frozenset())).capabilities
    if project_in(access.granted_write, project):
        granted |= C.WRITE_PROJECT_CAPABILITIES - {"project.members"}
    if "perf.view_all" in access.capabilities:
        granted.add("perf.view_project")
    if "finance.view_all" in access.capabilities:
        granted.add("finance.view")
    return frozenset(granted)


def has_project_capability(project: str, *codes: str, user: str | None = None) -> bool:
    return bool(capabilities_in(project, user).intersection(codes))


def assert_project_capability(project: str, *codes: str, user: str | None = None) -> None:
    """Raise PermissionError unless `user` may use one of `codes` in `project`."""
    if not has_project_capability(project, *codes, user=user):
        frappe.throw(_("Bạn không có quyền thực hiện thao tác này trong dự án {0}").format(project or ""),
                     frappe.PermissionError)


def assert_project_writable(project: str, user: str | None = None) -> None:
    """Raise PermissionError unless the user may change data of `project`."""
    if not project_in(get_access(user).write, project):
        frappe.throw(_("Bạn không được giao sửa dữ liệu của dự án {0}").format(project or ""), frappe.PermissionError)
