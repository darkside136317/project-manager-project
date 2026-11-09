"""Project scope of the construction DocTypes, built on the core's helpers (project_manager.permissions)."""

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
