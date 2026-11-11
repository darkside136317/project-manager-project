"""Nhân công: crews (PM Team of type Tổ đội), their workers (PMC Worker), attendance by crew and day.

* An attendance sheet (PMC Crew Attendance) is one crew on one project and day: each line a worker, the work item
  they worked on, the man-days (1, 0.5...) and overtime hours. The crew lead writes it (offline too: client_uuid),
  submits it; the site commander confirms it or sends it back.
* The daily rate of each worker is taken when the sheet is saved; confirmed man-days × rate are the labour cost of
  the work items (services/costs.py). Overtime hours are recorded, not priced.
Who: task.update writes and submits (for work items they can see), task.approve confirms or sends back.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate
from project_manager.project_manager.policy import can_see_task, get_access, has_project_capability, project_in
from project_manager.project_manager.services import activity
from project_manager.project_manager.services.notify import notify_user

from pm_construction.pm_construction import constants as K

CREW = "Tổ đội"
SPA_TAB = "/pm/du-an/{}/cham-cong"


def _readable(project):
    if not project or not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)


def crews() -> list[dict]:
    """Active crews and their active workers."""
    teams = frappe.get_all("PM Team", filters={"is_active": 1, "team_type": CREW},
                           fields=["name", "team_name", "leader"], order_by="team_name asc")
    workers = frappe.get_all("PMC Worker", filters={"is_active": 1, "team": ["in", [t.name for t in teams] or [""]]},
                             fields=["name", "full_name", "team", "trade"], order_by="full_name asc", limit_page_length=0)
    by_team = {}
    for worker in workers:
        by_team.setdefault(worker.team, []).append(worker)
    for team in teams:
        team["workers"] = by_team.get(team.name, [])
    return teams


def overview(project: str, start=None, end=None) -> dict:
    _readable(project)
    end = getdate(end or nowdate())
    start = getdate(start) if start else frappe.utils.add_days(end, -30)
    sheets = frappe.get_all("PMC Crew Attendance", filters={"project": project, "attendance_date": ["between", [start, end]]},
                            fields=["name", "attendance_date", "team", "status", "total_man_days", "total_amount", "author",
                                    "return_note"], order_by="attendance_date desc, team asc", limit_page_length=200)
    finance = has_project_capability(project, "finance.view")
    names = dict(frappe.get_all("PM Team", filters={"name": ["in", list({s.team for s in sheets})]},
                                fields=["name", "team_name"], as_list=True)) if sheets else {}
    for sheet in sheets:
        sheet["team_name"] = names.get(sheet.team, sheet.team)
        if not finance:
            sheet.pop("total_amount")
    by_task = frappe.db.sql("""select l.task, sum(l.man_days) as man_days from `tabPMC Attendance Line` l
                               join `tabPMC Crew Attendance` a on a.name = l.parent
                               where a.project = %s and a.status = %s and ifnull(l.task, '') != '' group by l.task""",
                            (project, K.SHEET_CONFIRMED), as_dict=True)
    return {"sheets": sheets, "crews": crews(), "man_days_by_task": {r.task: flt(r.man_days) for r in by_task},
            "can": {"write": has_project_capability(project, "task.update"),
                    "confirm": has_project_capability(project, "task.approve"), "finance": finance}}


def sheet(project: str, team: str, day=None) -> dict:
    """The sheet of a crew on a day, or a new one with its workers (one man-day each, no work item yet)."""
    _readable(project)
    day = getdate(day or nowdate())
    name = frappe.db.get_value("PMC Crew Attendance", {"project": project, "team": team, "attendance_date": day}, "name")
    if name:
        return detail(name)
    workers = frappe.get_all("PMC Worker", filters={"team": team, "is_active": 1}, fields=["name", "full_name", "trade"],
                             order_by="full_name asc")
    return {"name": None, "project": project, "team": team, "attendance_date": str(day), "status": K.SHEET_DRAFT,
            "lines": [{"worker": w.name, "worker_name": w.full_name, "trade": w.trade, "task": None, "man_days": 1,
                       "overtime_hours": 0, "note": None} for w in workers],
            "can": _can(project, None)}


def _can(project, doc) -> dict:
    status = doc.status if doc else K.SHEET_DRAFT
    write = has_project_capability(project, "task.update") and status == K.SHEET_DRAFT
    return {"write": write, "submit": write, "confirm": has_project_capability(project, "task.approve")
            and status == K.SHEET_SUBMITTED, "send_back": has_project_capability(project, "task.approve")
            and status in (K.SHEET_SUBMITTED, K.SHEET_CONFIRMED)}


def detail(name) -> dict:
    doc = frappe.get_doc("PMC Crew Attendance", name)
    _readable(doc.project)
    finance = has_project_capability(doc.project, "finance.view")
    labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", list({ln.task for ln in doc.lines if ln.task})]},
        fields=["name", "subject", "pm_wbs_code"])} if doc.lines else {}
    lines = []
    for line in doc.lines:
        row = {"worker": line.worker, "worker_name": line.worker_name, "task": line.task, "task_label": labels.get(line.task),
               "man_days": line.man_days, "overtime_hours": line.overtime_hours, "note": line.note}
        if finance:
            row.update(rate=line.rate, amount=line.amount)
        lines.append(row)
    out = {"name": doc.name, "project": doc.project, "team": doc.team, "attendance_date": str(doc.attendance_date),
           "status": doc.status, "lines": lines, "total_man_days": doc.total_man_days, "return_note": doc.return_note,
           "note": doc.note, "can": _can(doc.project, doc)}
    if finance:
        out["total_amount"] = doc.total_amount
    return out


def _lines(project: str, team: str, lines) -> list:
    if isinstance(lines, str):
        lines = frappe.parse_json(lines or "[]")
    rates = {w.name: w for w in frappe.get_all("PMC Worker", filters={"name": ["in", [ln.get("worker") for ln in lines or []]]},
                                               fields=["name", "full_name", "team", "daily_rate", "is_active"])}
    out, seen = [], set()
    for line in lines or []:
        line = frappe._dict(line)
        man_days = flt(line.man_days)
        if not line.worker or man_days <= 0:
            continue
        worker = rates.get(line.worker)
        if not worker or worker.team != team:
            frappe.throw(_("{0} không thuộc tổ đội này").format(line.worker))
        if not 0 < man_days <= 2:
            frappe.throw(_("Số công của {0} phải từ 0 đến 2").format(worker.full_name))
        key = (line.worker, line.task or "")
        if key in seen:
            frappe.throw(_("{0} có hai dòng cho cùng công tác").format(worker.full_name))
        seen.add(key)
        if line.task:
            work = frappe.db.get_value("Task", line.task, ["project", "is_group"], as_dict=True)
            if not work or work.project != project or cint(work.is_group):
                frappe.throw(_("Công tác không thuộc dự án này"))
            if not can_see_task(line.task, project):
                frappe.throw(_("Bạn không xem được công tác {0}").format(line.task), frappe.PermissionError)
        rate = flt(worker.daily_rate)
        out.append({"worker": line.worker, "worker_name": worker.full_name, "task": line.task or None, "man_days": man_days,
                    "overtime_hours": flt(line.overtime_hours) or None, "rate": rate, "amount": flt(rate * man_days, 0),
                    "note": (line.note or "").strip() or None})
    if not out:
        frappe.throw(_("Chưa chấm công cho ai"))
    return out


def save(project: str, team: str, day, lines, note: str = "", client_uuid: str | None = None) -> dict:
    """Create or update the draft sheet of a crew on a day."""
    _readable(project)
    if client_uuid:
        existing = frappe.db.get_value("PMC Crew Attendance", {"client_uuid": client_uuid}, "name")
        if existing:
            return detail(existing)
    if not has_project_capability(project, "task.update"):
        frappe.throw(_("Vai trò của bạn trong dự án không chấm công được"), frappe.PermissionError)
    if not frappe.db.get_value("PM Team", team, "is_active"):
        frappe.throw(_("Tổ đội không còn hoạt động"))
    day = getdate(day or nowdate())
    if day > getdate(nowdate()):
        frappe.throw(_("Không chấm công cho ngày chưa tới"))
    rows = _lines(project, team, lines)
    name = frappe.db.get_value("PMC Crew Attendance", {"project": project, "team": team, "attendance_date": day}, "name")
    if name:
        doc = frappe.get_doc("PMC Crew Attendance", name)
        if doc.status != K.SHEET_DRAFT:
            frappe.throw(_("Bảng chấm công ngày này đã nộp"), title=_("Không sửa được"))
    else:
        doc = frappe.get_doc({"doctype": "PMC Crew Attendance", "project": project, "team": team, "attendance_date": day,
                              "status": K.SHEET_DRAFT, "author": frappe.session.user, "client_uuid": client_uuid or None})
    doc.set("lines", rows)
    doc.total_man_days = sum(r["man_days"] for r in rows)
    doc.total_amount = sum(r["amount"] for r in rows)
    doc.note = (note or "").strip() or None
    doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
    return detail(doc.name)


def _lock(name):
    frappe.db.sql("select name from `tabPMC Crew Attendance` where name = %s for update", name)
    return frappe.get_doc("PMC Crew Attendance", name)


def submit(name) -> dict:
    doc = _lock(name)
    _readable(doc.project)
    if doc.status != K.SHEET_DRAFT:
        return detail(name)  # resent
    if not has_project_capability(doc.project, "task.update"):
        frappe.throw(_("Vai trò của bạn trong dự án không chấm công được"), frappe.PermissionError)
    doc.db_set({"status": K.SHEET_SUBMITTED, "submitted_on": now_datetime(), "return_note": None})
    team = frappe.db.get_value("PM Team", doc.team, "team_name") or doc.team
    activity.record("Project", doc.project, "Hệ thống", _("Nộp chấm công {0} ngày {1}: {2} công").format(
        team, getdate(doc.attendance_date).strftime("%d/%m"), flt(doc.total_man_days)))
    return detail(name)


def record(project: str, team: str, day, lines, note: str = "", client_uuid: str | None = None) -> dict:
    """Save and submit in one call (the offline outbox)."""
    saved = save(project, team, day, lines, note, client_uuid)
    return submit(saved["name"])


def confirm(name, note: str = "") -> dict:
    doc = _lock(name)
    _readable(doc.project)
    if not has_project_capability(doc.project, "task.approve"):
        frappe.throw(_("Chỉ người có quyền duyệt trong dự án mới xác nhận chấm công"), frappe.PermissionError)
    if doc.status != K.SHEET_SUBMITTED:
        frappe.throw(_("Chỉ xác nhận được bảng chấm công đã nộp"))
    doc.db_set({"status": K.SHEET_CONFIRMED, "confirmed_by": frappe.session.user, "confirmed_on": now_datetime()})
    _costs(doc)
    return detail(name)


def send_back(name, note: str) -> dict:
    doc = _lock(name)
    _readable(doc.project)
    if not has_project_capability(doc.project, "task.approve"):
        frappe.throw(_("Chỉ người có quyền duyệt trong dự án mới trả lại chấm công"), frappe.PermissionError)
    if not (note or "").strip():
        frappe.throw(_("Ghi lý do trả lại"))
    if doc.status not in (K.SHEET_SUBMITTED, K.SHEET_CONFIRMED):
        frappe.throw(_("Bảng chấm công chưa nộp"))
    was_confirmed = doc.status == K.SHEET_CONFIRMED
    doc.db_set({"status": K.SHEET_DRAFT, "return_note": note.strip(), "confirmed_by": None, "confirmed_on": None})
    if was_confirmed:
        _costs(doc)
    if doc.author and doc.author != frappe.session.user:
        notify_user(doc.author, _("Bảng chấm công ngày {0} bị trả lại: {1}").format(
            getdate(doc.attendance_date).strftime("%d/%m"), note.strip()), SPA_TAB.format(doc.project),
            "PMC Crew Attendance", str(doc.name))
    return detail(name)


def _costs(doc) -> None:
    from pm_construction.pm_construction.services import costs

    costs.refresh(doc.project, sorted({line.task for line in doc.lines if line.task}))
