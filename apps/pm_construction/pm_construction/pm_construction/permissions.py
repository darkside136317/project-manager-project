"""Project scope of the construction DocTypes, built on the core's helpers (project_manager.permissions)."""

import frappe
from project_manager.project_manager import permissions as core


def boq_query(user):
    return core.scope_condition(user, "PMC BOQ")


def boq_item_query(user):
    return core.entry_condition(user, "PMC BOQ Item")


def diary_query(user):
    return core.scope_condition(user, "PMC Site Diary")


def diary_quantity_query(user):
    return core.entry_condition(user, "PMC Diary Quantity")


# Written by the services only: through the API these rows are read, never changed.
has_boq_permission = core.read_only(lambda doc, ptype, user: core.scoped(doc, ptype, user))
has_boq_item_permission = core.read_only(lambda doc, ptype, user: core.entry_scoped(doc, ptype, user))
has_diary_permission = core.read_only(lambda doc, ptype, user: core.scoped(doc, ptype, user))
has_diary_quantity_permission = core.read_only(lambda doc, ptype, user: core.entry_scoped(doc, ptype, user))


# --- M8 ---------------------------------------------------------------------------------------------------------------------
def material_plan_query(user):
    return core.entry_condition(user, "PMC Material Plan")


def machine_shift_query(user):
    return core.entry_condition(user, "PMC Machine Shift")


def attendance_query(user):
    return core.scope_condition(user, "PMC Crew Attendance")


def machine_transfer_query(user):
    """A transfer concerns both projects: readable from either."""
    to = core.scope_condition(user, "PMC Machine Transfer")
    if not to:
        return ""
    frm = to.replace("`tabPMC Machine Transfer`.`project`", "`tabPMC Machine Transfer`.`from_project`")
    return f"(({to}) or ({frm}))"


def _transfer_scoped(doc, ptype, user) -> bool:
    from project_manager.project_manager.policy import get_access, project_in

    if core.scoped(doc, ptype, user):
        return True
    return bool(doc.get("from_project")) and project_in(get_access(user or frappe.session.user).read, doc.from_project)


has_material_plan_permission = core.read_only(lambda doc, ptype, user: core.entry_scoped(doc, ptype, user))
has_machine_shift_permission = core.read_only(lambda doc, ptype, user: core.entry_scoped(doc, ptype, user))
has_attendance_permission = core.read_only(lambda doc, ptype, user: core.scoped(doc, ptype, user))
has_machine_transfer_permission = core.read_only(lambda doc, ptype, user: _transfer_scoped(doc, ptype, user))

