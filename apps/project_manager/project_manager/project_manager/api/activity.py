"""The discussion of a task or a project: comments, @mentions, following, search. Rules: services/timeline.py."""

import frappe
from frappe.utils import cint

from project_manager.project_manager.services import search_index, timeline
from project_manager.project_manager.services.errors import retry_on_deadlock
from project_manager.project_manager.services.ui import assert_staff


@frappe.whitelist()
def feed(reference_doctype, reference_name, before=None, limit=30, kind=None):
    assert_staff()
    return timeline.feed(reference_doctype, reference_name, before, limit, kind or None)


@frappe.whitelist()
def entry(name):
    assert_staff()
    return timeline.entry(name)


@frappe.whitelist()
def people(reference_doctype, reference_name, search=""):
    assert_staff()
    return timeline.people(reference_doctype, reference_name, search)


@frappe.whitelist(methods=["POST"])
def post(reference_doctype, reference_name, content="", media=None, client_uuid=None):
    assert_staff()
    return retry_on_deadlock(lambda: timeline.post(reference_doctype, reference_name, content, media, client_uuid))


@frappe.whitelist(methods=["POST"])
def hide(name):
    assert_staff()
    return timeline.hide(name)


@frappe.whitelist(methods=["POST"])
def follow(reference_doctype, reference_name, watching=1):
    assert_staff()
    return timeline.follow(reference_doctype, reference_name, bool(cint(watching)))


@frappe.whitelist(methods=["POST"])
def mark_read(reference_doctype, reference_name, upto):
    assert_staff()
    timeline.target(reference_doctype, reference_name)
    return timeline.mark_read(reference_doctype, reference_name, upto)


@frappe.whitelist()
def search(query, project=None, kind=None, limit=20):
    assert_staff()
    try:
        return search_index.search(query, project or None, kind or None, limit)
    except search_index.SearchUnavailable as error:
        frappe.throw(str(error), title=frappe._("Tìm kiếm"))
