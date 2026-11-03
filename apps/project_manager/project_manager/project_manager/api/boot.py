"""Everything the SPA needs at start-up: who the user is, what the sidebar shows, which screens they may use."""

import frappe

from project_manager import __version__
from project_manager.project_manager.constants import ADMIN_SCREENS, MASTERS, SPA_HOME
from project_manager.project_manager.policy import capabilities_of, get_access, has_capability, is_admin, is_staff

GROUP_OVERVIEW = "Tổng quan"
GROUP_CATALOGUES = "Danh mục"
GROUP_ADMIN = "Quản trị"


def _can_read(doctype) -> bool:
    try:
        return bool(frappe.has_permission(doctype, "read"))
    except Exception:  # a DocType missing on this site must not break the whole shell
        return False


def _with_permissions(entries) -> list:
    return [{**e, "permissions": {p: bool(frappe.has_permission(e["doctype"], p))
                                  for p in ("create", "write", "delete")}} for e in entries]


def _admin_nav() -> list:
    """Administration: the administrators' pages, then the settings screens the user may read."""
    items = []
    if has_capability("users.manage"):
        items += [
            {"label": "Người dùng", "route": f"{SPA_HOME}/quan-tri/nguoi-dung", "icon": "users"},
            {"label": "Phân quyền", "route": f"{SPA_HOME}/quan-tri/phan-quyen", "icon": "shield-check"},
        ]
    if has_capability("logs.view"):
        items.append({"label": "Nhật ký hệ thống", "route": f"{SPA_HOME}/quan-tri/nhat-ky", "icon": "scroll-text"})
    if has_capability("monitor.view"):
        items.append({"label": "Giám sát hệ thống", "route": f"{SPA_HOME}/quan-tri/giam-sat", "icon": "gauge"})
    items += [{"label": e["label"], "route": f"{SPA_HOME}/quan-tri/{e['slug']}", "icon": e["icon"]}
              for e in ADMIN_SCREENS if _can_read(e["doctype"])]
    return [{"group": GROUP_ADMIN, "items": items}] if items else []


def build_boot() -> dict:
    """Sidebar sections filtered by the user's permissions (the server still enforces every call)."""
    user = frappe.session.user
    nav = [{"group": GROUP_OVERVIEW, "items": [{"label": "Tổng quan", "route": SPA_HOME, "icon": "layout-dashboard"}]}]
    masters = [m for m in MASTERS if _can_read(m["doctype"])]
    if masters:
        nav.append({"group": GROUP_CATALOGUES, "items": [
            {"label": m["label"], "route": f"{SPA_HOME}/danh-muc/{m['slug']}", "icon": m["icon"]} for m in masters]})
    nav.extend(_admin_nav())
    access = get_access(user)
    return {
        "user": {"name": user, "full_name": frappe.utils.get_fullname(user), "roles": frappe.get_roles(user),
                 "capabilities": sorted(capabilities_of(user)), "is_admin": is_admin(user),
                 "all_projects": access.read is None},
        "company": frappe.defaults.get_user_default("company") or frappe.defaults.get_global_default("company"),
        "version": __version__,
        "home": SPA_HOME,
        "nav": nav,
        "masters": _with_permissions(masters),
        "admin": _with_permissions([e for e in ADMIN_SCREENS if _can_read(e["doctype"])]),
    }


@frappe.whitelist()
def get_boot():
    if not is_staff():
        frappe.throw("Bạn không có quyền truy cập", frappe.PermissionError)
    return build_boot()
