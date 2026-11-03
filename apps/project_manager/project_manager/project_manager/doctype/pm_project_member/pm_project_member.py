import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from project_manager.project_manager.constants import STAFF_ROLE


class PMProjectMember(Document):
    """Thành viên dự án: a user holding a project role in one project, optionally for a period.

    A user may hold several roles in one project (one row each). Saving gives the user what the role needs in Frappe
    (the staff group and the role's required roles), additively.
    """

    def validate(self):
        if self.valid_from and self.valid_to and getdate(self.valid_to) < getdate(self.valid_from):
            frappe.throw(_("Ngày kết thúc phải sau ngày bắt đầu"))
        duplicate = frappe.db.exists("PM Project Member", {
            "project": self.project, "user": self.user, "project_role": self.project_role, "name": ["!=", self.name or 0]})
        if duplicate:
            frappe.throw(_("{0} đã có vai trò {1} trong dự án {2}").format(self.user, self.project_role, self.project))

    def on_update(self):
        from project_manager.project_manager.doctype.pm_group.pm_group import grant_roles
        from project_manager.project_manager.policy import clear_cache

        if self.is_active:
            required = frappe.get_all("PM Group Role", filters={"parenttype": "PM Project Role", "parent": self.project_role},
                                      pluck="role")
            grant_roles(self.user, [STAFF_ROLE, *required])
        clear_cache()

    def on_trash(self):
        from project_manager.project_manager.policy import clear_cache

        clear_cache()


def on_doctype_update():
    frappe.db.add_index("PM Project Member", ["user", "is_active"])
    frappe.db.add_index("PM Project Member", ["project", "project_role"])
