import frappe
from frappe import _
from frappe.model.document import Document

from project_manager.project_manager.constants import PROJECT_CAPABILITY_CODES
from project_manager.project_manager.doctype.pm_role_profile.pm_role_profile import validate_capabilities


class PMProjectRole(Document):
    """Vai trò trong dự án: what a member may do inside the projects where they hold it (policy.capabilities_in), which
    tasks they see, and the Frappe roles a member needs for it (e.g. Stock User for a storekeeper)."""

    def validate(self):
        self.role_name = (self.role_name or "").strip()
        validate_capabilities(self, PROJECT_CAPABILITY_CODES)
        seen = set()
        for row in self.get("required_roles") or []:
            if row.role in ("Administrator", "System Manager", "Guest", "All"):
                frappe.throw(_("Không cấp vai trò {0} qua vai trò dự án").format(row.role))
            if row.role in seen:
                frappe.throw(_("Vai trò {0} xuất hiện hai lần").format(row.role))
            seen.add(row.role)

    def on_update(self):
        _forget()

    def on_trash(self):
        if self.is_builtin and not frappe.flags.in_uninstall:
            frappe.throw(_("Không xóa được vai trò có sẵn"))
        if frappe.db.exists("PM Project Member", {"project_role": self.name}):
            frappe.throw(_("Vai trò {0} đang được dùng trong dự án").format(self.name))
        _forget()


def _forget():
    from project_manager.project_manager.policy import clear_cache

    clear_cache()
