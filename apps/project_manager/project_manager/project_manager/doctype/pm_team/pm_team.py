import frappe
from frappe import _
from frappe.model.document import Document


class PMTeam(Document):
    """Đội / tổ: a group of people work can be given to as a whole (a crew, a department, a subcontractor)."""

    def validate(self):
        self.team_name = (self.team_name or "").strip()
        seen = set()
        for row in self.get("members") or []:
            if row.user in seen:
                frappe.throw(_("{0} xuất hiện hai lần trong đội").format(row.user))
            seen.add(row.user)
        if self.leader and self.leader not in seen:
            self.append("members", {"user": self.leader, "position": _("Trưởng nhóm")})

    def on_update(self):
        from project_manager.project_manager.policy import clear_cache

        clear_cache()

    def on_trash(self):
        if frappe.db.exists("PM Task Assignment", {"team": self.name}):
            frappe.throw(_("Đội {0} đã được giao việc: hãy ngừng hoạt động thay vì xóa").format(self.name))

