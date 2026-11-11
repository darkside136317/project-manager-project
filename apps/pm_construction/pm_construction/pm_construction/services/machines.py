"""Máy thi công: the register (PMC Machine), moving machines between projects, shifts on work items.

* An owned machine is an ERPNext Asset: moving it records an Asset Movement (purpose Transfer) to the project's site
  location (a Location with pm_project, made on demand), or back to the company yard. A rented machine is not an
  asset: only the transfer history is kept.
* A shift (ca máy) is recorded on the project the machine is at, for a work item, with its fuel; its cost is the
  shifts times the machine's shift rate that day. Shifts are written from the phone (offline outbox, client_uuid).
* Alert type "Máy đến hạn bảo dưỡng": a machine at a project whose next maintenance is within N days or past.
Who: plan.edit or project.edit moves machines (on both projects); task.update records shifts.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate
from project_manager.project_manager.policy import can_see_task, get_access, has_project_capability, project_in
from project_manager.project_manager.services import activity

from pm_construction.pm_construction import constants as K

YARD = "Bãi máy công ty"


def _readable(project):
    if not project or not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)


def site_location(project: str | None) -> str:
    """The Location of a project's site (made once), or the company yard when no project."""
    if project:
        name = frappe.db.get_value("Location", {"pm_project": project}, "name")
        if name:
            return name
        code = frappe.db.get_value("Project", project, "pm_code") or project
        return frappe.get_doc({"doctype": "Location", "location_name": f"Công trường {code}", "pm_project": project}).insert(
            ignore_permissions=True).name
    if not frappe.db.exists("Location", YARD):
        frappe.get_doc({"doctype": "Location", "location_name": YARD}).insert(ignore_permissions=True)
    return YARD


def overview(project: str) -> dict:
    _readable(project)
    finance = has_project_capability(project, "finance.view")
    here = frappe.get_all("PMC Machine", filters={"current_project": project},
                          fields=["name", "machine_name", "machine_type", "ownership", "status", "since", "shift_rate",
                                  "fuel_norm", "next_maintenance"], order_by="machine_name asc")
    can_move = has_project_capability(project, "plan.edit", "project.edit")
    free = frappe.get_all("PMC Machine", filters={"current_project": ["is", "not set"], "status": ["!=", "Đã trả"]},
                          fields=["name", "machine_name", "machine_type", "ownership", "status"],
                          order_by="machine_name asc") if can_move else []
    shifts = frappe.get_all("PMC Machine Shift", filters={"project": project},
                            fields=["name", "machine", "machine_name", "task", "shift_date", "shifts", "hours", "fuel",
                                    "operator", "note", "amount", "recorded_by"],
                            order_by="shift_date desc, name desc", limit_page_length=100)
    labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", list({s.task for s in shifts if s.task})]}, fields=["name", "subject", "pm_wbs_code"])
    } if shifts else {}
    totals = {}
    for row in frappe.db.sql("""select machine, sum(shifts) as shifts, sum(fuel) as fuel, sum(amount) as amount
                                from `tabPMC Machine Shift` where project = %s group by machine""", project, as_dict=True):
        totals[row.machine] = row
    for machine in here:
        total = totals.get(machine.name) or {}
        machine["shifts_total"] = flt(total.get("shifts"))
        machine["fuel_total"] = flt(total.get("fuel"))
        machine["fuel_expected"] = flt(total.get("shifts")) * flt(machine.fuel_norm)
        if finance:
            machine["amount_total"] = flt(total.get("amount"))
        else:
            machine.pop("shift_rate")
    for shift in shifts:
        shift["task_label"] = labels.get(shift.task)
        if not finance:
            shift.pop("amount")
    transfers = frappe.db.sql("""select name, machine, from_project, project, transfer_date, note from `tabPMC Machine Transfer`
                                 where project = %(p)s or from_project = %(p)s order by transfer_date desc, name desc
                                 limit 30""", {"p": project}, as_dict=True)
    return {"machines": here, "free": free, "shifts": shifts, "transfers": transfers,
            "can": {"move": can_move, "record": has_project_capability(project, "task.update"), "finance": finance}}


def transfer(machine: str, to_project: str | None, transfer_date=None, note: str = "") -> dict:
    """Move a machine to a project (or back to the company: to_project empty)."""
    doc = frappe.get_doc("PMC Machine", machine)
    from_project = doc.current_project
    to_project = to_project or None
    for project in {from_project, to_project} - {None}:
        _readable(project)
        if not has_project_capability(project, "plan.edit", "project.edit"):
            frappe.throw(_("Bạn không điều chuyển được máy của dự án {0}").format(project), frappe.PermissionError)
    if from_project == to_project:
        frappe.throw(_("Máy đã ở đó") if to_project else _("Chọn dự án nhận máy"))
    day = getdate(transfer_date or nowdate())
    movement = None
    if doc.ownership == K.OWNED and doc.asset:
        movement = _move_asset(doc.asset, to_project, day)
    record = frappe.get_doc({"doctype": "PMC Machine Transfer", "machine": machine, "from_project": from_project,
                             "project": to_project, "transfer_date": day, "asset_movement": movement,
                             "moved_by": frappe.session.user, "note": (note or "").strip() or None})
    record.insert(ignore_permissions=True)
    doc.db_set({"current_project": to_project, "since": day if to_project else None,
                "status": K.MACHINE_BUSY if to_project else K.MACHINE_READY}, update_modified=True)
    text = _("Điều chuyển máy {0} {1}").format(doc.machine_name, _("đến dự án") if to_project else _("về công ty"))
    for project in {from_project, to_project} - {None}:
        activity.record("Project", project, "Hệ thống", text + (f": {note.strip()}" if (note or "").strip() else ""),
                        data={"machine": machine, "transfer": record.name})
    return {"name": record.name, "asset_movement": movement}


def _move_asset(asset: str, to_project: str | None, day) -> str:
    info = frappe.db.get_value("Asset", asset, ["company", "location", "docstatus"], as_dict=True)
    if not info or info.docstatus != 1:
        frappe.throw(_("Tài sản {0} chưa được ghi nhận trong ERPNext").format(asset))
    target = site_location(to_project)
    movement = frappe.get_doc({"doctype": "Asset Movement", "company": info.company, "purpose": "Transfer",
                               "transaction_date": now_datetime() if getdate(day) == getdate(nowdate()) else f"{day} 08:00:00",
                               "pm_project": to_project,
                               "assets": [{"asset": asset, "source_location": info.location, "target_location": target}]})
    movement.insert(ignore_permissions=True)
    movement.submit()
    return movement.name


def record_shift(project: str, machine: str, task: str | None, shift_date, shifts, hours=None, fuel=None,
                 operator: str = "", note: str = "", client_uuid: str | None = None) -> dict:
    _readable(project)
    if client_uuid:
        existing = frappe.db.get_value("PMC Machine Shift", {"client_uuid": client_uuid}, "name")
        if existing:
            return {"name": existing, "again": True}
    if not has_project_capability(project, "task.update"):
        frappe.throw(_("Vai trò của bạn trong dự án không ghi được ca máy"), frappe.PermissionError)
    info = frappe.db.get_value("PMC Machine", machine, ["machine_name", "current_project", "shift_rate"], as_dict=True)
    if not info:
        frappe.throw(_("Không có máy {0}").format(machine))
    if info.current_project != project:
        frappe.throw(_("Máy {0} không ở dự án này").format(info.machine_name))
    shifts = flt(shifts)
    if not 0 < shifts <= 3:
        frappe.throw(_("Số ca trong ngày phải lớn hơn 0 và không quá 3"))
    day = getdate(shift_date or nowdate())
    if day > getdate(nowdate()):
        frappe.throw(_("Không ghi ca máy cho ngày chưa tới"))
    if task:
        work = frappe.db.get_value("Task", task, ["project", "is_group"], as_dict=True)
        if not work or work.project != project or cint(work.is_group):
            frappe.throw(_("Công tác không thuộc dự án này"))
        if not can_see_task(task, project):
            frappe.throw(_("Bạn không xem được công tác này"), frappe.PermissionError)
    row = frappe.get_doc({"doctype": "PMC Machine Shift", "project": project, "machine": machine,
                          "machine_name": info.machine_name, "task": task or None, "shift_date": day, "shifts": shifts,
                          "hours": flt(hours) or None, "fuel": flt(fuel) or None, "operator": (operator or "").strip() or None,
                          "note": (note or "").strip() or None, "rate": flt(info.shift_rate),
                          "amount": flt(info.shift_rate) * shifts, "recorded_by": frappe.session.user,
                          "client_uuid": client_uuid or None})
    row.insert(ignore_permissions=True)
    if task:
        from pm_construction.pm_construction.services import costs

        costs.refresh(project, [task])
    return {"name": row.name, "again": False}


def delete_shift(name) -> dict:
    row = frappe.db.get_value("PMC Machine Shift", name, ["project", "task", "recorded_by", "creation"], as_dict=True)
    if not row:
        frappe.throw(_("Không có ca máy này"))
    _readable(row.project)
    mine = row.recorded_by == frappe.session.user and (now_datetime() - row.creation).days < 1
    if not (mine or has_project_capability(row.project, "plan.edit")):
        frappe.throw(_("Chỉ người ghi (trong ngày) hoặc người lập kế hoạch mới xóa được ca máy"), frappe.PermissionError)
    frappe.delete_doc("PMC Machine Shift", name, ignore_permissions=True)
    if row.task:
        from pm_construction.pm_construction.services import costs

        costs.refresh(row.project, [row.task])
    return {"deleted": name}


def maintenance_due(rule, today):
    """Alert type "Máy đến hạn bảo dưỡng"."""
    from project_manager.project_manager.services import alerts

    days = cint(rule.days) or 3
    rows = frappe.db.sql("""select m.name, m.machine_name, m.current_project, m.next_maintenance
                            from `tabPMC Machine` m join `tabProject` p on p.name = m.current_project
                            where m.next_maintenance is not null and m.next_maintenance <= %(until)s
                              and p.pm_is_template = 0 and p.pm_state = 'Đang thực hiện'""",
                         {"until": add_days(today, days)}, as_dict=True)
    return [alerts._hit("PMC Machine", r.name, r.current_project, None, str(r.next_maintenance),
                        _("Máy {0} đến hạn bảo dưỡng ngày {1}").format(r.machine_name,
                                                                     getdate(r.next_maintenance).strftime("%d/%m/%Y")))
            for r in rows]
