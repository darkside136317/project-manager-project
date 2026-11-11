"""Materials, machines, labour and costs of a construction site (M8). Rules live in services/materials.py,
machines.py, labour.py, costs.py."""

import frappe
from project_manager.project_manager.services.ui import assert_staff

from pm_construction.pm_construction.services import costs, labour, machines, materials


def _list(value):
    return frappe.parse_json(value) if isinstance(value, str) else (value or [])


# --- materials -------------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def materials_overview(project):
    assert_staff()
    return materials.overview(project)


@frappe.whitelist(methods=["POST"])
def create_store(project):
    assert_staff()
    return {"store": materials.create_store(project)}


@frappe.whitelist(methods=["POST"])
def recompute_plan(project):
    assert_staff()
    return {"rows": materials.recompute_plan(project)}


@frappe.whitelist(methods=["POST"])
def material_request(project, rows, note="", needed_by=None, client_uuid=None):
    assert_staff()
    return materials.request(project, _list(rows), note, needed_by, client_uuid)


@frappe.whitelist(methods=["POST"])
def stop_request(name, note=""):
    assert_staff()
    return materials.stop_request(name, note)


@frappe.whitelist(methods=["POST"])
def stock_receive(project, rows, posting_date=None, note="", client_uuid=None):
    assert_staff()
    return materials.receive(project, _list(rows), posting_date, note, client_uuid)


@frappe.whitelist(methods=["POST"])
def stock_issue(project, rows, posting_date=None, note="", client_uuid=None):
    assert_staff()
    return materials.issue(project, _list(rows), posting_date, note, client_uuid)


@frappe.whitelist(methods=["POST"])
def stock_return(project, rows, posting_date=None, note="", client_uuid=None):
    assert_staff()
    return materials.give_back(project, _list(rows), posting_date, note, client_uuid)


@frappe.whitelist(methods=["POST"])
def stock_write_off(project, rows, posting_date=None, note="", client_uuid=None):
    assert_staff()
    return materials.write_off(project, _list(rows), posting_date, note, client_uuid)


@frappe.whitelist(methods=["POST"])
def stock_transfer(project, to_project, rows, posting_date=None, note="", client_uuid=None):
    assert_staff()
    return materials.transfer(project, to_project, _list(rows), posting_date, note, client_uuid)


# --- machines ----------------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def machines_overview(project):
    assert_staff()
    return machines.overview(project)


@frappe.whitelist(methods=["POST"])
def machine_transfer(machine, to_project=None, transfer_date=None, note=""):
    assert_staff()
    return machines.transfer(machine, to_project or None, transfer_date, note)


@frappe.whitelist(methods=["POST"])
def machine_shift(project, machine, shift_date, shifts, task=None, hours=None, fuel=None, operator="", note="",
                  client_uuid=None):
    assert_staff()
    return machines.record_shift(project, machine, task or None, shift_date, shifts, hours, fuel, operator, note,
                                 client_uuid)


@frappe.whitelist(methods=["POST"])
def delete_shift(name):
    assert_staff()
    return machines.delete_shift(name)


# --- labour -------------------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def labour_overview(project, start=None, end=None):
    assert_staff()
    return labour.overview(project, start, end)


@frappe.whitelist()
def attendance_sheet(project, team, day=None):
    assert_staff()
    return labour.sheet(project, team, day)


@frappe.whitelist(methods=["POST"])
def attendance_save(project, team, day, lines, note="", client_uuid=None):
    assert_staff()
    return labour.save(project, team, day, _list(lines), note, client_uuid)


@frappe.whitelist(methods=["POST"])
def attendance_submit(name):
    assert_staff()
    return labour.submit(name)


@frappe.whitelist(methods=["POST"])
def attendance_record(project, team, day, lines, note="", client_uuid=None):
    assert_staff()
    return labour.record(project, team, day, _list(lines), note, client_uuid)


@frappe.whitelist(methods=["POST"])
def attendance_confirm(name, note=""):
    assert_staff()
    return labour.confirm(name, note)


@frappe.whitelist(methods=["POST"])
def attendance_send_back(name, note):
    assert_staff()
    return labour.send_back(name, note)


# --- costs ---------------------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def cost_summary(project):
    assert_staff()
    return costs.summary(project)


# --- machine bookings (M9) --------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def machine_book(project, machine, from_date, to_date, task=None, note=""):
    return machines.book(project, machine, from_date, to_date, task or None, note)


@frappe.whitelist(methods=["POST"])
def machine_booking_cancel(name):
    return machines.cancel_booking(name)
