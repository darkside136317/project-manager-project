import frappe
from frappe import _
from frappe.model.document import Document

from project_manager.project_manager import constants as C


class PMAccess(Document):
    """Phạm vi truy cập của một nhân viên, ngoài các dự án họ tham gia.

    Without a PM Access (and in no PM Group that sets a scope) a user sees exactly the projects they are a member of
    and changes them as far as their project roles allow. A scope adds to that: every project, or chosen projects, to
    see and possibly to change. Administrators are never narrowed and need none.
    """

    def validate(self):
        if frappe.db.get_value("User", self.user, "user_type") != "System User":
            frappe.throw(_("{0} không phải tài khoản nhân viên").format(self.user))
        validate_scope(self)

    def on_update(self):
        _forget()

    def on_trash(self):
        _forget()


def validate_scope(doc) -> None:
    """Shared by PM Access and PM Group: chosen projects listed once each, only where the scope uses them."""
    doc.read_scope = doc.read_scope or C.READ_MEMBER
    doc.write_scope = doc.write_scope or C.WRITE_MEMBER
    if doc.read_scope != C.READ_CHOSEN:
        doc.set("read_projects", [])
    if doc.write_scope != C.WRITE_CHOSEN:
        doc.set("write_projects", [])
    if doc.read_scope == C.READ_MEMBER and doc.write_scope == C.WRITE_SAME:
        doc.write_scope = C.WRITE_MEMBER  # "as what they see" adds nothing to their memberships
    for table in ("read_projects", "write_projects"):
        seen = set()
        for row in doc.get(table) or []:
            if row.project in seen:
                frappe.throw(_("Dự án {0} xuất hiện hai lần").format(row.project))
            seen.add(row.project)
    if doc.write_scope == C.WRITE_CHOSEN and doc.read_scope == C.READ_CHOSEN:
        readable = {r.project for r in doc.get("read_projects") or []}
        outside = [r.project for r in doc.get("write_projects") or [] if r.project not in readable]
        if outside:
            frappe.throw(_("Dự án được sửa phải nằm trong các dự án được xem: {0}").format(", ".join(outside)))


def _forget():
    from project_manager.project_manager.policy import clear_cache

    clear_cache()
