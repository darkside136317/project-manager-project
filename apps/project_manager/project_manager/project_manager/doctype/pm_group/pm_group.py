import frappe
from frappe import _
from frappe.model.document import Document

from project_manager.project_manager.doctype.pm_access.pm_access import validate_scope
from project_manager.project_manager.policy import assignable_roles, clear_cache


class PMGroup(Document):
    """Nhóm nhân viên: gom người dùng, cấp nhóm quyền đồng loạt và (tùy chọn) một phạm vi dự án chung.

    Saving the group gives its roles to every member (additively: leaving a group never takes a role away, that is
    done on the user). Only the app's permission groups can be put in a group.
    """

    def validate(self):
        self.group_name = (self.group_name or "").strip()
        self._unique("roles", "role", _("Nhóm quyền"))
        self._unique("members", "user", _("Thành viên"))
        allowed = assignable_roles()
        for row in self.get("roles") or []:
            if row.role not in allowed:
                frappe.throw(_("Vai trò {0} không được cấp qua nhóm nhân viên").format(row.role))
        if self.apply_scope:
            validate_scope(self)
        else:
            self.set("read_projects", [])
            self.set("write_projects", [])

    def on_update(self):
        roles = [row.role for row in self.get("roles") or []]
        for row in self.get("members") or []:
            grant_roles(row.user, roles)
        clear_cache()

    def on_trash(self):
        clear_cache()

    def _unique(self, table: str, field: str, label: str) -> None:
        seen = set()
        for row in self.get(table) or []:
            if row.get(field) in seen:
                frappe.throw(_("{0} {1} xuất hiện hai lần").format(label, row.get(field)))
            seen.add(row.get(field))


def grant_roles(user: str, roles) -> list[str]:
    """Give `user` the roles they lack (never takes one away). Returns the roles added."""
    roles = [r for r in roles if r]
    if not roles or not frappe.db.exists("User", user):
        return []
    have = set(frappe.get_roles(user))
    missing = [r for r in roles if r not in have]
    if missing:
        doc = frappe.get_doc("User", user)
        doc.add_roles(*missing)  # saves the user
    return missing
