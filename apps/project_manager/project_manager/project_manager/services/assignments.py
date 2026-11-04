"""Giao việc rõ trách nhiệm: who does what on a task, in which RACI role, and the history that never disappears.

Rules kept here (and only here — PM Task Assignment is written by nobody else):

* A task has at most one live "Chịu trách nhiệm chính" (accountable) assignment, always to a person. Giving the role
  to someone else ends the previous holder's assignment (state Thu hồi, reason "Chuyển giao"). Two managers doing it
  at the same moment are serialised by a lock on the task row.
* The person must be able to read the project (a member, or granted it): assigning work to someone who cannot open
  it would only produce a task nobody does. A member who only sees the tasks given to them (crew lead, guest) sees
  this one from the moment it is given.
* An assignment starts "Chờ nhận"; the assignee accepts it or declines it with a reason. The assigner (or anyone who
  may assign in the project) can revoke it with a reason. Nothing is deleted: every step is a PM Activity entry.
* Task.pm_accountable / pm_reviewer mirror the live accountable and reviewer, so lists and filters stay cheap.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import (
    assert_project_capability,
    get_access,
    has_project_capability,
    project_in,
    teams_of,
)
from project_manager.project_manager.services import activity
from project_manager.project_manager.services.notify import notify_user

SPA_TASK = "/pm/cong-viec/{}"


def _task(name: str) -> frappe._dict:
    task = frappe.db.get_value("Task", name, ["name", "subject", "project", "is_group", "status"], as_dict=True)
    if not task:
        frappe.throw(_("Không tìm thấy công việc {0}").format(name), frappe.DoesNotExistError)
    return task


def _label(user: str | None = None, team: str | None = None) -> str:
    if team:
        return _("đội {0}").format(team)
    return frappe.utils.get_fullname(user) or user


def _sync_mirrors(task: str) -> None:
    """Task.pm_accountable / pm_reviewer = the live accountable / reviewer person (or empty)."""
    live = frappe.get_all("PM Task Assignment", filters={"task": task, "is_active": 1, "state": ["in", C.LIVE_STATES],
                                                         "raci": ["in", [C.ACCOUNTABLE, C.REVIEWER]]},
                          fields=["raci", "user"], order_by="name desc")
    accountable = next((r.user for r in live if r.raci == C.ACCOUNTABLE), None)
    reviewer = next((r.user for r in live if r.raci == C.REVIEWER), None)
    frappe.db.set_value("Task", task, {"pm_accountable": accountable, "pm_reviewer": reviewer}, update_modified=False)


def _end(row, state: str, reason: str = "") -> None:
    row.db_set({"state": state, "is_active": 0 if state in (C.REVOKED, C.DECLINED) else row.is_active,
                "ended_by": frappe.session.user, "ended_on": now_datetime(), "end_reason": reason or None})


def assign(task: str, raci: str, user: str | None = None, team: str | None = None, note: str = "") -> int:
    """Give `task` to a person or a team in a RACI role. Returns the new assignment's id."""
    info = _task(task)
    assert_project_capability(info.project, "task.assign")
    if raci not in C.RACI_ROLES:
        frappe.throw(_("Vai trò không hợp lệ: {0}").format(raci))
    if bool(user) == bool(team):
        frappe.throw(_("Giao cho một người hoặc một đội"))
    if raci in (C.ACCOUNTABLE, C.REVIEWER) and not user:
        frappe.throw(_("{0} phải là một người cụ thể").format(raci))
    if user:
        if not frappe.db.get_value("User", user, "enabled"):
            frappe.throw(_("Tài khoản {0} không hoạt động").format(user))
        if not project_in(get_access(user).read, info.project):
            frappe.throw(_("{0} chưa là thành viên dự án nên không thấy công việc này: thêm vào dự án trước")
                         .format(_label(user)))
    if team and not frappe.db.get_value("PM Team", team, "is_active"):
        frappe.throw(_("Đội {0} không hoạt động").format(team))

    frappe.db.sql("select name from `tabTask` where name = %s for update", task)
    same = {"task": task, "raci": raci, "is_active": 1, "state": ["in", C.LIVE_STATES]}
    if frappe.db.exists("PM Task Assignment", {**same, ("user" if user else "team"): user or team}):
        frappe.throw(_("{0} đã có vai trò {1} trong công việc này").format(_label(user, team), raci))
    if raci in (C.ACCOUNTABLE, C.REVIEWER):
        for name in frappe.get_all("PM Task Assignment", filters=same, pluck="name"):
            previous = frappe.get_doc("PM Task Assignment", name)
            _end(previous, C.REVOKED, _("Chuyển giao cho {0}").format(_label(user)))
            activity.record("Task", task, "Giao việc", _("Thu hồi vai trò {0} của {1}: chuyển giao cho {2}").format(
                raci, _label(previous.user, previous.team), _label(user)),
                data={"assignment": previous.name, "state": C.REVOKED})

    row = frappe.get_doc({"doctype": "PM Task Assignment", "task": task, "raci": raci, "user": user, "team": team,
                          "state": C.PENDING if raci != C.INFORMED else C.ACCEPTED, "is_active": 1, "note": note or None,
                          "assigned_by": frappe.session.user, "assigned_on": now_datetime()})
    row.insert(ignore_permissions=True)
    _sync_mirrors(task)
    activity.record("Task", task, "Giao việc", _("Giao {0} vai trò {1}").format(_label(user, team), raci) +
                    (f": {note}" if note else ""), data={"assignment": row.name, "raci": raci, "user": user, "team": team})
    for person in ([user] if user else _team_people(team)):
        if person != frappe.session.user:
            notify_user(person, _("Bạn được giao {0}: {1}").format(raci.lower(), info.subject), SPA_TASK.format(task),
                        "Task", task)
    return row.name


def _team_people(team: str) -> list[str]:
    return frappe.get_all("PM Team Member", filters={"parent": team, "parenttype": "PM Team"}, pluck="user")


def _own(row) -> bool:
    """Is the assignment the caller's (theirs, or their team's)?"""
    user = frappe.session.user
    return row.user == user or (bool(row.team) and row.team in teams_of(user))


def respond(assignment: int, accept: bool, reason: str = "") -> dict:
    """The assignee accepts or declines (a reason is required to decline)."""
    row = frappe.get_doc("PM Task Assignment", assignment)
    if not _own(row):
        frappe.throw(_("Chỉ người được giao mới nhận hoặc từ chối việc này"), frappe.PermissionError)
    if not row.is_active or row.state != C.PENDING:
        frappe.throw(_("Phân công này không còn chờ trả lời (đang ở trạng thái {0})").format(row.state))
    reason = (reason or "").strip()
    if not accept and not reason:
        frappe.throw(_("Hãy ghi lý do từ chối"))
    if accept:
        row.db_set({"state": C.ACCEPTED, "responded_on": now_datetime()})
        text = _("{0} nhận vai trò {1}").format(_label(frappe.session.user), row.raci)
    else:
        row.db_set({"state": C.DECLINED, "is_active": 0, "responded_on": now_datetime(), "decline_reason": reason})
        text = _("{0} từ chối vai trò {1}: {2}").format(_label(frappe.session.user), row.raci, reason)
        if row.assigned_by and row.assigned_by != frappe.session.user:
            subject = frappe.db.get_value("Task", row.task, "subject")
            notify_user(row.assigned_by, _("{0} từ chối việc \"{1}\": {2}").format(
                _label(frappe.session.user), subject, reason), SPA_TASK.format(row.task), "Task", row.task)
    _sync_mirrors(row.task)
    activity.record("Task", row.task, "Giao việc", text, data={"assignment": row.name, "state": row.state})
    return {"name": row.name, "state": row.state}


def revoke(assignment: int, reason: str) -> dict:
    """End an assignment (the person no longer has that role); the reason is kept in the history."""
    row = frappe.get_doc("PM Task Assignment", assignment)
    project = frappe.db.get_value("Task", row.task, "project")
    assert_project_capability(project, "task.assign")
    if not row.is_active or row.state not in C.LIVE_STATES:
        frappe.throw(_("Phân công này đã kết thúc"))
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Hãy ghi lý do thu hồi"))
    _end(row, C.REVOKED, reason)
    _sync_mirrors(row.task)
    activity.record("Task", row.task, "Giao việc", _("Thu hồi vai trò {0} của {1}: {2}").format(
        row.raci, _label(row.user, row.team), reason), data={"assignment": row.name, "state": C.REVOKED})
    return {"name": row.name, "state": C.REVOKED}


def complete_for(task: str) -> None:
    """The task is done: its live assignments are done too (they stay visible in the history)."""
    for name in frappe.get_all("PM Task Assignment", filters={"task": task, "is_active": 1, "state": ["in", C.LIVE_STATES]},
                               pluck="name"):
        frappe.db.set_value("PM Task Assignment", name, {"state": C.DONE, "ended_on": now_datetime()},
                            update_modified=False)


def of_task(task: str) -> list[dict]:
    """Every assignment of a task, live ones first, with what the caller may do on each."""
    info = _task(task)
    may_assign = has_project_capability(info.project, "task.assign")
    rows = frappe.get_all("PM Task Assignment", filters={"task": task},
                          fields=["name", "raci", "user", "team", "state", "is_active", "note", "assigned_by", "assigned_on",
                                  "responded_on", "decline_reason", "ended_by", "ended_on", "end_reason"],
                          order_by="is_active desc, name desc")
    for row in rows:
        live = row.is_active and row.state in C.LIVE_STATES
        row["who"] = _label(row.user, row.team)
        row["can_respond"] = bool(live and row.state == C.PENDING and _own(row))
        row["can_revoke"] = bool(live and may_assign)
    return rows

