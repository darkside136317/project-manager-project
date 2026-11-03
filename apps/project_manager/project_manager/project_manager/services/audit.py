"""The one place that writes the system audit log (PM Audit Log).

* `log_activity` is the explicit entry point (downloads, admin actions, permission changes).
* `audit_doc_event` is attached to the configuration DocTypes through `doc_events` (hooks.py) and records
  create / update / delete — the state change too — without touching the feature code.
* `on_login` / `on_logout` record sessions.

The project timeline (who changed what on a task) is PM Activity, not this log.

Every writer honours `PM Settings.enable_audit_log`, never raises into the calling operation, and does
not commit unless asked to (a GET request is rolled back otherwise). Values are not copied into the log
except for state-like fields: the log must not become a second, unprotected copy of business data.
"""

import ipaddress

import frappe

from project_manager.project_manager.services.errors import log_exception

LOG_DOCTYPE = "PM Audit Log"
SETTINGS = "PM Settings"

AUDITED_DOCTYPES = (
    "PM Role Profile", "PM Group", "PM Access", "PM Project Role", "PM Project Member", "PM Node Type",
    "PM Settings",
)

# Fields whose old → new value is worth keeping in the description.
STATE_FIELDS = ("status", "workflow_state", "is_active", "project_role", "read_scope", "write_scope",
                "task_visibility", "pm_state")
IGNORED_FIELDS = {"modified", "modified_by", "creation", "owner", "idx", "docstatus"}

_EVENT_TYPES = {"after_insert": "Tạo mới", "on_update": "Cập nhật", "on_update_after_submit": "Cập nhật",
                "on_trash": "Xóa"}


def is_enabled() -> bool:
    value = frappe.db.get_single_value(SETTINGS, "enable_audit_log")
    return True if value is None else bool(frappe.utils.cint(value))


def _client_ip() -> str:
    """Use the address set by the trusted HTTPS proxy, with a safe fallback."""
    request = getattr(frappe.local, "request", None)
    forwarded = request.headers.get("X-Forwarded-For", "") if request else ""
    candidate = forwarded.split(",", 1)[0].strip() if forwarded else ""
    try:
        if candidate:
            return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass
    return getattr(frappe.local, "request_ip", None) or ""


def log_activity(activity_type, reference_doctype="", reference_name="", description="",
                 data_json="", commit=False, user=None):
    """Write one Business Activity Log row. Returns its name, or None when disabled/failed."""
    try:
        if not is_enabled():
            return None
        log = frappe.get_doc({
            "doctype": LOG_DOCTYPE,
            "activity_type": activity_type,
            "reference_doctype": reference_doctype or "",
            "reference_name": reference_name or "",
            "user": user or frappe.session.user,
            "ip_address": _client_ip(),
            "description": (description or "")[:2000],
            "data_json": data_json or "",
        }).insert(ignore_permissions=True)
        if commit:
            frappe.db.commit()
        return log.name
    except Exception:
        log_exception("Activity Log Error", "Failed to write the activity log")
        return None


def _skip() -> bool:
    flags = frappe.flags
    return bool(flags.in_migrate or flags.in_install or flags.in_patch or flags.in_import
                or flags.in_test_audit_off)


def _describe_changes(doc) -> str:
    before = doc.get_doc_before_save()
    if not before:
        return ""
    names, states = [], []
    for df in doc.meta.fields:
        field = df.fieldname
        if not field or field in IGNORED_FIELDS or df.fieldtype in ("Section Break", "Column Break", "Tab Break",
                                                                  "Table", "Table MultiSelect", "Password"):
            continue
        old, new = before.get(field), doc.get(field)
        if (old or "") == (new or ""):
            continue
        names.append(df.label or field)
        if field in STATE_FIELDS:
            states.append(f"{df.label or field}: {old or '∅'} → {new or '∅'}")
    return "; ".join(states) if states else ("Đã sửa: " + ", ".join(names) if names else "")


def audit_doc_event(doc, method=None):
    """`doc_events` handler for the audited DocTypes."""
    try:
        if doc.doctype == LOG_DOCTYPE or _skip():
            return
        activity_type = _EVENT_TYPES.get(method)
        if not activity_type:
            return
        if method == "on_update" and doc.flags.in_insert:
            return  # `after_insert` already recorded the creation
        description = doc.get("title") or doc.get(doc.meta.title_field or "name") or doc.name
        if method in ("on_update", "on_update_after_submit"):
            changes = _describe_changes(doc)
            if not changes:
                return
            description = f"{description} — {changes}"
        log_activity(activity_type, doc.doctype, doc.name, str(description))
    except Exception:
        log_exception("Activity Log Error", f"Audit failed for {doc.doctype} {doc.name}")


def on_login(login_manager=None):
    user = getattr(login_manager, "user", None) or frappe.session.user
    if user and user != "Guest":
        log_activity("Đăng nhập", "User", user, "Đăng nhập hệ thống", user=user)


def on_logout(login_manager=None):
    user = getattr(login_manager, "user", None) or frappe.session.user
    if user and user != "Guest":
        log_activity("Đăng xuất", "User", user, "Đăng xuất", user=user)


def purge_logs(before, batch_size: int = 5000, types: list | None = None) -> int:
    """Delete log rows older than `before` (optionally only of some activity types) in batches (one huge DELETE would
    lock the table). Records its own summary row so the clean-up itself stays auditable. Returns the number deleted."""
    where, params = "`timestamp` < %(before)s", {"before": before}
    if types:
        where += " and activity_type in %(types)s"
        params["types"] = tuple(types)
    deleted = 0
    while True:
        frappe.db.sql(f"delete from `tab{LOG_DOCTYPE}` where {where} limit {int(batch_size)}", params)
        count = frappe.db.sql("select row_count()")[0][0] or 0
        deleted += count
        frappe.db.commit()
        if count < batch_size:
            break
    detail = f" (loại: {', '.join(types)})" if types else ""
    log_activity("Dọn dẹp nhật ký", LOG_DOCTYPE, "", f"Đã xóa {deleted} dòng nhật ký trước {before}{detail}", commit=True)
    return deleted


def purge_expired() -> int:
    """Daily job: drop log rows older than the retention set in PM Settings (at least 7 days)."""
    from project_manager.project_manager.doctype.pm_settings.pm_settings import MIN_AUDIT_RETENTION_DAYS

    days = max(frappe.utils.cint(frappe.db.get_single_value(SETTINGS, "audit_retention_days")) or 180,
               MIN_AUDIT_RETENTION_DAYS)
    before = frappe.utils.add_days(frappe.utils.now_datetime(), -days)
    if not frappe.db.exists(LOG_DOCTYPE, {"timestamp": ["<", before]}):
        return 0
    return purge_logs(before)
