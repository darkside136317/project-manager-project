"""Budgets and earned value, risks, issues, change requests, closing a project and its dossier. Rules live in
services/budget.py, control.py, closing.py."""

import frappe

from project_manager.project_manager.services import budget, closing, control
from project_manager.project_manager.services.ui import assert_staff


# --- budget -------------------------------------------------------------------------------------------------------------
@frappe.whitelist()
def budget_overview(project):
    assert_staff()
    return budget.overview(project)


@frappe.whitelist(methods=["POST"])
def budget_save(project, title="", lines=None, note="", name=None):
    assert_staff()
    return budget.save_draft(project, title, lines, note, name or None)


@frappe.whitelist(methods=["POST"])
def budget_revise(project):
    assert_staff()
    return budget.start_from_current(project)


@frappe.whitelist(methods=["POST"])
def budget_approve(name, note=""):
    assert_staff()
    return budget.approve(name, note)


@frappe.whitelist(methods=["POST"])
def budget_discard(name):
    assert_staff()
    return budget.discard(name)


# --- risks, issues, change requests -------------------------------------------------------------------------------------
@frappe.whitelist()
def register(project):
    assert_staff()
    return control.register(project)


@frappe.whitelist(methods=["POST"])
def save_risk(project, values, name=None):
    assert_staff()
    return control.save_risk(project, values, name or None)


@frappe.whitelist(methods=["POST"])
def risk_happened(name, note=""):
    assert_staff()
    return control.risk_happened(name, note)


@frappe.whitelist(methods=["POST"])
def save_issue(project, values, name=None):
    assert_staff()
    return control.save_issue(project, values, name or None)


@frappe.whitelist(methods=["POST"])
def save_change(project, values, tasks=None, name=None):
    assert_staff()
    return control.save_change(project, values, tasks, name or None)


@frappe.whitelist(methods=["POST"])
def submit_change(name):
    assert_staff()
    return control.submit_change(name)


@frappe.whitelist(methods=["POST"])
def decide_change(name, approve, note=""):
    assert_staff()
    return control.decide(name, frappe.utils.cint(approve), note)


@frappe.whitelist(methods=["POST"])
def cancel_change(name):
    assert_staff()
    return control.cancel_change(name)


# --- closing ------------------------------------------------------------------------------------------------------------
@frappe.whitelist()
def closing_check(project):
    assert_staff()
    return closing.check(project)


@frappe.whitelist(methods=["POST"])
def close_project(project, note=""):
    assert_staff()
    return closing.close(project, note)


@frappe.whitelist(methods=["POST"])
def reopen_project(project, note=""):
    assert_staff()
    return closing.reopen(project, note)


@frappe.whitelist(methods=["POST"])
def request_dossier(project):
    assert_staff()
    return closing.request_dossier(project)
