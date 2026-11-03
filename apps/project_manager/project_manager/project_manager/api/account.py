"""The signed-in user's own account: change their password, read their notifications."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from project_manager.project_manager.services import notify


def _signed_in() -> None:
    if frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=15 * 60)
def change_password(old_password, new_password):
    """Frappe's own `update_password`: password policy and re-login included.

    The current password is checked here first: Frappe answers a wrong one with an AuthenticationError, and the
    framework ends the session of whoever raises that. A user who mistyped the old password must stay signed in,
    so it becomes an ordinary validation message.
    """
    from frappe.core.doctype.user.user import update_password
    from frappe.utils.password import check_password

    _signed_in()
    if not old_password or not new_password:
        frappe.throw(_("Vui lòng nhập mật khẩu hiện tại và mật khẩu mới"))
    if old_password == new_password:
        frappe.throw(_("Mật khẩu mới phải khác mật khẩu hiện tại"))
    try:
        check_password(frappe.session.user, old_password)
    except frappe.AuthenticationError:
        frappe.throw(_("Mật khẩu hiện tại không đúng"))
    update_password(new_password, old_password=old_password)
    return {"message": _("Đã đổi mật khẩu")}


@frappe.whitelist()
def get_notifications(start=0, page_length=20):
    _signed_in()
    return notify.list_for(frappe.session.user, start, page_length)


@frappe.whitelist(methods=["POST"])
def mark_notifications_read(names=None):
    """Mark some (JSON list of names) or all of the caller's notifications as read. Returns the unread count."""
    _signed_in()
    names = frappe.parse_json(names) if isinstance(names, str) and names else names
    return notify.mark_read(frappe.session.user, names or None)
