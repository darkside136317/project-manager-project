import frappe
from frappe import _
from frappe.model.document import Document

from project_manager.project_manager.constants import ADMIN_ONLY_CAPABILITIES, ADMIN_ROLE, CAPABILITY_CODES

# Frappe's own roles never become permission groups of the application.
RESERVED_ROLES = frozenset({"Administrator", "System Manager", "Guest", "All", "Desk User"})


class PMRoleProfile(Document):
    """Nhóm quyền: a Frappe Role described for the app, with the global functions it grants.

    What the group may do with data (read / create / write / delete ...) is the role's DocPerm, which Frappe enforces
    everywhere; functions that are not a DocType (see every project, see everyone's performance, ...) are the
    `capabilities` rows, checked by `policy.has_capability`. The administrators' group holds every capability
    implicitly and cannot be changed.
    """

    def validate(self):
        if self.role in RESERVED_ROLES:
            frappe.throw(_("Vai trò {0} không thể làm nhóm quyền của ứng dụng").format(self.role))
        self.label = (self.label or "").strip()
        self.is_admin = int(self.role == ADMIN_ROLE)
        if self.is_admin:
            self.set("capabilities", [])  # an administrator holds every capability: nothing to list
            return
        validate_capabilities(self, CAPABILITY_CODES, ADMIN_ONLY_CAPABILITIES)

    def on_update(self):
        _forget()

    def on_trash(self):
        if self.is_builtin and not frappe.flags.in_uninstall:
            frappe.throw(_("Không xóa được nhóm quyền có sẵn"))
        _forget()


def validate_capabilities(doc, known: frozenset, admin_only: frozenset = frozenset()) -> None:
    """Shared by PM Role Profile and PM Project Role: known codes, each listed once."""
    seen = set()
    for row in doc.get("capabilities") or []:
        code = (row.capability or "").strip()
        if code in admin_only:
            frappe.throw(_("Chức năng {0} chỉ dành cho quản trị viên").format(code))
        if code not in known:
            frappe.throw(_("Chức năng {0} không tồn tại").format(code))
        if code in seen:
            frappe.throw(_("Chức năng {0} xuất hiện hai lần").format(code))
        seen.add(code)
        row.capability = code


def _forget():
    from project_manager.project_manager.policy import clear_cache

    clear_cache()
