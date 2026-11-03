"""DocType description for the generic SPA screens."""

import frappe

from project_manager.project_manager.services.ui import describe


@frappe.whitelist()
def get_doctype_ui(doctype):
    """Fields (limited to what the user may read/write), layout, list columns and permissions."""
    return describe(doctype)
