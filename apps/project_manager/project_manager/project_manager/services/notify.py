"""In-app notifications (the bell of the SPA).

They are Frappe `Notification Log` rows of type "Alert": the type Frappe never e-mails, so nothing here needs an
outgoing mail account. Notifying is best effort: a failure is logged and never blocks the operation that caused it.
"""

import frappe
from frappe.utils import cint

from project_manager.project_manager.services.errors import log_exception


def notify_user(user: str, subject: str, link: str, doctype: str = "", name: str = "") -> str | None:
    """Create the notification of `user`. Returns its name, or None when it could not be created."""
    if not user or user in ("Guest", "Administrator"):
        return None
    try:
        log = frappe.get_doc({
            "doctype": "Notification Log", "for_user": user, "from_user": frappe.session.user,
            "type": "Alert", "subject": subject[:500], "link": link,
            "document_type": doctype or None, "document_name": name or None,
        })
        log.insert(ignore_permissions=True)
        return log.name
    except Exception:
        log_exception("Notification failed", f"{doctype} {name} -> {user}")
        return None


def notify_capability(capability: str, subject: str, link: str, doctype: str = "", name: str = "") -> int:
    """Notify every holder of a global capability (except the one who caused it)."""
    from project_manager.project_manager.policy import users_with_capability

    sent = 0
    for user in users_with_capability(capability):
        if user != frappe.session.user and notify_user(user, subject, link, doctype, name):
            sent += 1
    return sent


def sent_today(user: str, subject: str) -> bool:
    """Has this exact notification already been created today? (a daily job must not repeat itself)"""
    return bool(frappe.db.exists("Notification Log", {
        "for_user": user, "subject": subject, "creation": [">=", frappe.utils.get_datetime(f"{frappe.utils.nowdate()} 00:00:00")]}))


def unread_count(user: str | None = None) -> int:
    user = user or frappe.session.user
    if user == "Guest":
        return 0
    return frappe.db.count("Notification Log", {"for_user": user, "read": 0, "type": "Alert"})


def list_for(user: str, start: int = 0, page_length: int = 20) -> dict:
    filters = {"for_user": user, "type": "Alert"}
    rows = frappe.get_all(
        "Notification Log", filters=filters,
        fields=["name", "subject", "link", "read", "creation", "document_type", "document_name"],
        order_by="creation desc", start=max(0, cint(start)), page_length=max(1, min(cint(page_length) or 20, 100)))
    return {"rows": rows, "total": frappe.db.count("Notification Log", filters), "unread": unread_count(user)}


def mark_read(user: str, names: list[str] | None = None) -> int:
    """Mark the user's own notifications read (all of them when `names` is empty)."""
    filters = {"for_user": user, "read": 0, "type": "Alert"}
    if names:
        filters["name"] = ["in", names]
    frappe.db.set_value("Notification Log", filters, "read", 1, update_modified=False)
    frappe.cache.hdel("notifications", user)
    return unread_count(user)
