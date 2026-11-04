"""Work on tasks: my tasks, Kanban, who does what, one task in full, assignments and progress reports.
Rules live in services/work.py, services/assignments.py and services/progress.py."""

import frappe
from frappe.utils import cint

from project_manager.project_manager.services import assignments, progress, work
from project_manager.project_manager.services.errors import retry_on_deadlock
from project_manager.project_manager.services.ui import assert_staff


@frappe.whitelist()
def my_tasks(done=0, start=0, limit=100):
    assert_staff()
    return work.my_tasks(done, start, limit)


@frappe.whitelist()
def kanban(project, accountable=None, parent=None, search=None, late=0):
    assert_staff()
    return work.kanban(project, accountable or None, parent or None, search or None, late)


@frappe.whitelist()
def who_does_what(project):
    assert_staff()
    return work.who_does_what(project)


@frappe.whitelist()
def detail(task):
    assert_staff()
    return work.task_detail(task)


@frappe.whitelist(methods=["POST"])
def assign(task, raci, user=None, team=None, note=""):
    assert_staff()
    return {"name": retry_on_deadlock(lambda: assignments.assign(task, raci, user or None, team or None, note))}


@frappe.whitelist(methods=["POST"])
def respond(assignment, accept, reason=""):
    assert_staff()
    return assignments.respond(cint(assignment), bool(cint(accept)), reason)


@frappe.whitelist(methods=["POST"])
def revoke(assignment, reason):
    assert_staff()
    return assignments.revoke(cint(assignment), reason)


@frappe.whitelist(methods=["POST"])
def report(task, progress_value, note="", delay_reason=None, delay_source=None, delay_note=None, man_days=None,
           client_uuid=None):
    assert_staff()
    return retry_on_deadlock(lambda: progress.report(task, progress_value, note, delay_reason or None,
                                                     delay_source or None, delay_note or None, man_days,
                                                     client_uuid or None))


@frappe.whitelist(methods=["POST"])
def review(task, approve, note=""):
    assert_staff()
    return progress.review(task, bool(cint(approve)), note)


@frappe.whitelist(methods=["POST"])
def move(task, status, note="", delay_reason=None, delay_source=None, delay_note=None):
    assert_staff()
    return retry_on_deadlock(lambda: progress.move(task, status, note, delay_reason or None, delay_source or None,
                                                   delay_note or None))
