"""Alerts, notification choices, the portfolio and phase gates. Rules live in services/alerts.py, portfolio.py,
phases.py."""

import frappe

from project_manager.project_manager.services import alerts, phases, portfolio as portfolio_service
from project_manager.project_manager.services.ui import assert_staff


@frappe.whitelist()
def mine(state="open", limit=100):
    assert_staff()
    return alerts.mine(state, limit)


@frappe.whitelist()
def of_project(project, state="open"):
    assert_staff()
    return alerts.of_project(project, state)


@frappe.whitelist(methods=["POST"])
def acknowledge(name, note=""):
    assert_staff()
    return alerts.acknowledge(name, note)


@frappe.whitelist()
def preference():
    assert_staff()
    return alerts.my_preference()


@frappe.whitelist(methods=["POST"])
def save_preference(values):
    assert_staff()
    return alerts.save_preference(frappe.parse_json(values) if isinstance(values, str) else values)


@frappe.whitelist()
def portfolio(state=None, health=None):
    assert_staff()
    return portfolio_service.portfolio(state or None, health or None)


@frappe.whitelist()
def phase_state(project):
    assert_staff()
    if not frappe.has_permission("Project", "read", project):
        raise frappe.PermissionError
    return phases.state(project)


@frappe.whitelist(methods=["POST"])
def pass_phase(phase, note=""):
    assert_staff()
    return phases.pass_phase(phase, note)
