"""Projects: list, overview, create (empty or from a template), change, members. Rules live in services/projects.py."""

import frappe

from project_manager.project_manager.services import projects
from project_manager.project_manager.services.ui import assert_staff


def _dict(value) -> dict:
    return frappe.parse_json(value) if isinstance(value, str) else (value or {})


@frappe.whitelist()
def list_projects(state=None, search=None, templates=0, start=0, limit=50):
    assert_staff()
    return projects.list_projects(state, search, templates, start, limit)


@frappe.whitelist()
def overview(project):
    assert_staff()
    return projects.overview(project)


@frappe.whitelist(methods=["POST"])
def create(values, template=None):
    assert_staff()
    return projects.create(_dict(values), template or None)


@frappe.whitelist(methods=["POST"])
def update(project, values):
    assert_staff()
    return projects.update(project, _dict(values))


@frappe.whitelist()
def members(project):
    assert_staff()
    return projects.members(project)


@frappe.whitelist(methods=["POST"])
def add_member(project, user, project_role, valid_from=None, valid_to=None, note=""):
    assert_staff()
    return projects.add_member(project, user, project_role, valid_from, valid_to, note)


@frappe.whitelist(methods=["POST"])
def set_member(name, values):
    assert_staff()
    return projects.set_member(frappe.utils.cint(name), _dict(values))


@frappe.whitelist()
def member_candidates(project, txt=""):
    assert_staff()
    return projects.candidates(project, txt)
