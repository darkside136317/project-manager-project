"""Scheduling: dependencies, the Gantt, moving dates, the calendar, baselines.
Rules live in services/schedule.py and services/baseline.py."""

import frappe
from frappe.utils import cint

from project_manager.project_manager.services import baseline as baselines
from project_manager.project_manager.services import schedule
from project_manager.project_manager.services.errors import retry_on_deadlock
from project_manager.project_manager.services.ui import assert_staff


@frappe.whitelist()
def gantt(project, baseline=None):
    assert_staff()
    return schedule.gantt(project, baseline or None)


@frappe.whitelist()
def calendar(project, first, last):
    assert_staff()
    return schedule.calendar_view(project, first, last)


@frappe.whitelist()
def dependencies(task):
    assert_staff()
    return schedule.of_task(task)


@frappe.whitelist()
def search_tasks(project, txt="", exclude=None):
    assert_staff()
    return schedule.search_tasks(project, txt, exclude or None)


@frappe.whitelist(methods=["POST"])
def add_dependency(predecessor, successor, kind="FS", lag=0):
    assert_staff()
    return schedule.add_dependency(predecessor, successor, kind, cint(lag))


@frappe.whitelist(methods=["POST"])
def update_dependency(name, kind, lag=0):
    assert_staff()
    return schedule.update_dependency(name, kind, cint(lag))


@frappe.whitelist(methods=["POST"])
def remove_dependency(name):
    assert_staff()
    return schedule.remove_dependency(name)


@frappe.whitelist(methods=["POST"])
def preview_move(task, start=None, end=None):
    assert_staff()
    return schedule.preview(task, start or None, end or None)


@frappe.whitelist(methods=["POST"])
def apply_move(task, start=None, end=None, reason=""):
    assert_staff()
    return retry_on_deadlock(lambda: schedule.apply(task, start or None, end or None, reason))


@frappe.whitelist()
def preview_conflicts(project):
    assert_staff()
    return schedule.conflicts_preview(project)


@frappe.whitelist(methods=["POST"])
def apply_conflicts(project, reason=""):
    assert_staff()
    return retry_on_deadlock(lambda: schedule.conflicts_apply(project, reason))


@frappe.whitelist()
def list_baselines(project):
    assert_staff()
    return baselines.list_baselines(project)


@frappe.whitelist(methods=["POST"])
def capture_baseline(project, title="", note=""):
    assert_staff()
    return baselines.capture(project, title, note)


@frappe.whitelist(methods=["POST"])
def set_primary_baseline(name):
    assert_staff()
    return baselines.set_primary(name)


@frappe.whitelist(methods=["POST"])
def remove_baseline(name):
    assert_staff()
    return baselines.remove(name)


@frappe.whitelist()
def compare_baseline(name, late_only=0):
    assert_staff()
    return baselines.compare(name, late_only)
