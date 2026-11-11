"""Workload and performance of people (services/workload.py, performance.py)."""

import frappe

from project_manager.project_manager.services import performance, workload
from project_manager.project_manager.services.ui import assert_staff


@frappe.whitelist()
def workload_overview(start=None, weeks=6, team=None, project=None):
    assert_staff()
    return workload.overview(start, weeks, team or None, project or None)


@frappe.whitelist()
def workload_cell(user, week):
    assert_staff()
    return workload.cell(user, week)


@frappe.whitelist(methods=["POST"])
def save_capacity(user, from_date, to_date, capacity_pct, reason="Nghỉ phép", note="", name=None):
    assert_staff()
    return workload.save_capacity(user, from_date, to_date, capacity_pct, reason, note, name or None)


@frappe.whitelist(methods=["POST"])
def delete_capacity(name):
    assert_staff()
    return workload.delete_capacity(name)


@frappe.whitelist()
def performance_overview(period="4w", start=None, end=None, project=None, team=None):
    assert_staff()
    return performance.overview(period, start, end, project or None, team or None)


@frappe.whitelist()
def performance_person(user, period="4w", start=None, end=None):
    assert_staff()
    return performance.person(user, period, start, end)


@frappe.whitelist()
def teams():
    """Active teams, to filter by (the names only)."""
    assert_staff()
    return frappe.get_all("PM Team", filters={"is_active": 1}, fields=["name", "team_name", "team_type"],
                          order_by="team_name asc")
