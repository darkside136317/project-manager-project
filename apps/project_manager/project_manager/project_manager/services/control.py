"""Kiểm soát dự án: the risk register, the issues, the change requests (phát sinh).

* Risk (PM Risk): probability and impact 1–5, score = their product, level Thấp (< 5) / Trung bình (< 12) / Cao; an
  owner, a response (Giảm thiểu, Tránh, Chuyển giao, Chấp nhận), a plan and a due date. Closed when over, or marked
  "Đã xảy ra": it then becomes an issue.
* Issue (PM Issue): a problem to solve, with an owner, a priority, a due date; resolved with how. Alert type
  "Vấn đề quá hạn xử lý" when its due date is past.
* Change request (PM Change Request): Nháp → Chờ duyệt → Đã duyệt / Từ chối (or Đã hủy by its author). Approving it
  adds its cost to the budget in use (services/budget.py) and moves the listed tasks to their new end (with what
  depends on them, services/schedule.apply). Its author cannot decide on it (administrators excepted).
Who: everyone who sees the whole project reads (not the roles that see only their own tasks); risk.manage writes
risks and issues; change.request prepares change requests; change.approve decides.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

from project_manager.project_manager.policy import get_access, has_project_capability, is_admin, project_in
from project_manager.project_manager.services import activity, notify

RISK_OPEN = ("Mở", "Đang xử lý")
ISSUE_OPEN = ("Mở", "Đang xử lý")
DRAFT, WAITING, APPROVED, REJECTED, CANCELLED = "Nháp", "Chờ duyệt", "Đã duyệt", "Từ chối", "Đã hủy"
OVERDUE_ISSUE = "Vấn đề quá hạn xử lý"
RISK_FIELDS = ("title", "category", "description", "task", "probability", "impact", "owner_user", "response", "plan",
               "due_date", "status", "close_note")
ISSUE_FIELDS = ("title", "description", "task", "risk", "priority", "owner_user", "due_date", "status", "resolution")
CHANGE_FIELDS = ("title", "reason", "description", "cost_impact", "days_impact")
RISK_ORDER = {"Mở": 0, "Đang xử lý": 1, "Đã xảy ra": 2, "Đã đóng": 3}
ISSUE_ORDER = {"Mở": 0, "Đang xử lý": 1, "Đã giải quyết": 2, "Đã đóng": 3}
PRIORITY_ORDER = {"Khẩn": 0, "Cao": 1, "Trung bình": 2, "Thấp": 3}


def _link(project: str, tab: str) -> str:
    return f"/pm/du-an/{project}/{tab}"


def _assert_read(project: str) -> None:
    if not project_in(get_access().read_tasks, project):
        frappe.throw(_("Bạn không xem được rủi ro, vấn đề, phát sinh của dự án này"), frappe.PermissionError)


def _assert(project: str, code: str, message: str) -> None:
    _assert_read(project)
    if not has_project_capability(project, code):
        frappe.throw(message, frappe.PermissionError)


def _member(project: str, user: str | None) -> str | None:
    if user and not project_in(get_access(user).read, project):
        frappe.throw(_("{0} không xem được dự án này nên không phụ trách được").format(user))
    return user or None


def _task(project: str, task: str | None) -> str | None:
    if task and frappe.db.get_value("Task", task, "project") != project:
        frappe.throw(_("Công việc không thuộc dự án này"))
    return task or None


def _names(users) -> dict:
    users = [u for u in set(users) if u]
    return dict(frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"], as_list=True)) if users else {}


def _task_labels(names) -> dict:
    names = [n for n in set(names) if n]
    return {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", names]}, fields=["name", "subject", "pm_wbs_code"])} if names else {}


# --- the tab ------------------------------------------------------------------------------------------------------------

def register(project: str) -> dict:
    """Risks, issues and change requests of the project, with what the user may do."""
    _assert_read(project)
    risks = frappe.get_all("PM Risk", filters={"project": project},
                           fields=["name", *RISK_FIELDS, "score", "level", "raised_by", "closed_on", "creation"],
                           order_by="creation desc", limit_page_length=500)
    risks.sort(key=lambda r: (RISK_ORDER.get(r.status, 9), -cint(r.score)))
    issues = frappe.get_all("PM Issue", filters={"project": project},
                            fields=["name", *ISSUE_FIELDS, "raised_by", "resolved_on", "creation"],
                            order_by="creation desc", limit_page_length=500)
    issues.sort(key=lambda i: (ISSUE_ORDER.get(i.status, 9), PRIORITY_ORDER.get(i.priority, 9)))
    changes = frappe.get_all("PM Change Request", filters={"project": project},
                             fields=["name", *CHANGE_FIELDS, "status", "requested_by", "submitted_on", "decided_by",
                                     "decided_on", "decision_note", "budget", "creation"],
                             order_by="creation desc", limit_page_length=200)
    rows = frappe.get_all("PM Change Task", filters={"parent": ["in", [c.name for c in changes] or [""]],
                                                     "parenttype": "PM Change Request"},
                          fields=["parent", "task", "old_end", "new_end", "note"], order_by="idx asc", limit_page_length=0)
    names = _names([*(r.owner_user for r in risks), *(i.owner_user for i in issues), *(c.requested_by for c in changes),
                    *(c.decided_by for c in changes)])
    labels = _task_labels([*(r.task for r in risks), *(i.task for i in issues), *(r.task for r in rows)])
    today = getdate(nowdate())
    for row in risks:
        row["owner_name"] = names.get(row.owner_user)
        row["task_label"] = labels.get(row.task)
        row["overdue"] = bool(row.due_date and row.status in RISK_OPEN and getdate(row.due_date) < today)
    for row in issues:
        row["owner_name"] = names.get(row.owner_user)
        row["task_label"] = labels.get(row.task)
        row["overdue"] = bool(row.due_date and row.status in ISSUE_OPEN and getdate(row.due_date) < today)
    by_change = {}
    for row in rows:
        by_change.setdefault(row.parent, []).append({**row, "task_label": labels.get(row.task)})
    finance = has_project_capability(project, "finance.view", "budget.manage")
    me = frappe.session.user
    approver = has_project_capability(project, "change.approve")
    for row in changes:
        row["tasks"] = by_change.get(row.name, [])
        row["requested_name"] = names.get(row.requested_by)
        row["decided_name"] = names.get(row.decided_by)
        row["can"] = {"edit": row.status == DRAFT and (row.requested_by == me or approver),
                      "decide": row.status == WAITING and approver and (row.requested_by != me or is_admin()),
                      "cancel": row.status in (DRAFT, WAITING) and (row.requested_by == me or approver)}
    return {"risks": risks, "issues": issues, "changes": changes, "summary": summary(project, risks, issues, changes),
            "finance": finance,
            "can": {"risk": has_project_capability(project, "risk.manage"),
                    "request": has_project_capability(project, "change.request"), "approve": approver}}


def summary(project: str, risks=None, issues=None, changes=None) -> dict:
    """Counts for the overview: open risks by level, open and overdue issues, change requests waiting."""
    today = getdate(nowdate())
    if risks is None:
        risks = frappe.get_all("PM Risk", filters={"project": project, "status": ["in", RISK_OPEN]}, fields=["level", "status"])
    if issues is None:
        issues = frappe.get_all("PM Issue", filters={"project": project, "status": ["in", ISSUE_OPEN]},
                                fields=["status", "due_date"])
    if changes is None:
        changes = frappe.get_all("PM Change Request", filters={"project": project}, fields=["status", "cost_impact"])
    open_risks = [r for r in risks if r.status in RISK_OPEN]
    open_issues = [i for i in issues if i.status in ISSUE_OPEN]
    return {"risks_open": len(open_risks), "risks_high": sum(1 for r in open_risks if r.level == "Cao"),
            "issues_open": len(open_issues),
            "issues_overdue": sum(1 for i in open_issues if i.due_date and getdate(i.due_date) < today),
            "changes_waiting": sum(1 for c in changes if c.status == WAITING),
            "changes_approved_cost": flt(sum(flt(c.cost_impact) for c in changes if c.status == APPROVED), 0)}


# --- risks --------------------------------------------------------------------------------------------------------------

def save_risk(project: str, values: dict, name=None) -> dict:
    _assert(project, "risk.manage", _("Vai trò của bạn trong dự án không ghi được rủi ro"))
    values = {k: v for k, v in (frappe.parse_json(values) if isinstance(values, str) else values or {}).items()
              if k in RISK_FIELDS}
    if "owner_user" in values:
        values["owner_user"] = _member(project, values["owner_user"])
    if "task" in values:
        values["task"] = _task(project, values["task"])
    owner_before = None
    if name:
        doc = frappe.get_doc("PM Risk", name)
        owner_before = doc.owner_user
        if doc.project != project:
            frappe.throw(_("Rủi ro thuộc dự án khác"))
        before = doc.status
        doc.update(values)
        if doc.status in ("Đã đóng", "Đã xảy ra") and before not in ("Đã đóng", "Đã xảy ra"):
            doc.closed_on = getdate(nowdate())
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "PM Risk", "project": project, "raised_by": frappe.session.user, **values})
        doc.insert(ignore_permissions=True)
        activity.record("Project", project, "Thay đổi", _("Ghi rủi ro {0}: {1} (mức {2})").format(doc.name, doc.title, doc.level),
                        data={"risk": doc.name})
    if doc.owner_user and doc.owner_user != frappe.session.user and (not name or doc.owner_user != owner_before):
        notify.notify_user(doc.owner_user, _("Bạn phụ trách rủi ro: {0}").format(doc.title), _link(project, "rui-ro"),
                           "PM Risk", doc.name)
    return doc.as_dict()


def risk_happened(name, note: str = "") -> dict:
    """The risk happened: closed as "Đã xảy ra", and an issue opened from it."""
    doc = frappe.get_doc("PM Risk", name)
    _assert(doc.project, "risk.manage", _("Vai trò của bạn trong dự án không ghi được rủi ro"))
    if doc.status not in RISK_OPEN:
        frappe.throw(_("Rủi ro này đã đóng"))
    doc.update({"status": "Đã xảy ra", "closed_on": getdate(nowdate()), "close_note": (note or "").strip() or None})
    doc.save(ignore_permissions=True)
    issue = save_issue(doc.project, {"title": doc.title, "description": "\n".join(filter(None, [doc.description, note])),
                                     "task": doc.task, "risk": doc.name, "owner_user": doc.owner_user,
                                     "priority": "Cao" if doc.level == "Cao" else "Trung bình"})
    return {"risk": doc.name, "issue": issue["name"]}


# --- issues -------------------------------------------------------------------------------------------------------------

def save_issue(project: str, values: dict, name=None) -> dict:
    _assert(project, "risk.manage", _("Vai trò của bạn trong dự án không ghi được vấn đề"))
    values = {k: v for k, v in (frappe.parse_json(values) if isinstance(values, str) else values or {}).items()
              if k in ISSUE_FIELDS}
    if "owner_user" in values:
        values["owner_user"] = _member(project, values["owner_user"])
    if "task" in values:
        values["task"] = _task(project, values["task"])
    if values.get("risk") and frappe.db.get_value("PM Risk", values["risk"], "project") != project:
        frappe.throw(_("Rủi ro thuộc dự án khác"))
    owner_before = None
    if name:
        doc = frappe.get_doc("PM Issue", name)
        owner_before = doc.owner_user
        if doc.project != project:
            frappe.throw(_("Vấn đề thuộc dự án khác"))
        before = doc.status
        doc.update(values)
        if doc.status in ("Đã giải quyết", "Đã đóng") and before in ISSUE_OPEN:
            if not (doc.resolution or "").strip():
                frappe.throw(_("Ghi cách giải quyết trước khi đóng vấn đề"))
            doc.resolved_on = getdate(nowdate())
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "PM Issue", "project": project, "raised_by": frappe.session.user, **values})
        doc.insert(ignore_permissions=True)
        activity.record("Project", project, "Thay đổi", _("Ghi vấn đề {0}: {1}").format(doc.name, doc.title),
                        data={"issue": doc.name})
    if doc.owner_user and doc.owner_user != frappe.session.user and (not name or doc.owner_user != owner_before):
        notify.notify_user(doc.owner_user, _("Bạn xử lý vấn đề: {0}").format(doc.title), _link(project, "rui-ro"),
                           "PM Issue", doc.name)
    return doc.as_dict()


def overdue_issues(rule, today):
    """Alert type "Vấn đề quá hạn xử lý": an open issue past its due date (to its owner and the manager)."""
    from project_manager.project_manager.services import alerts

    rows = frappe.db.sql("""select i.name, i.title, i.project, i.task, i.due_date, i.owner_user, p.pm_manager
                            from `tabPM Issue` i join `tabProject` p on p.name = i.project
                            where i.status in %(open)s and i.due_date < %(today)s and p.pm_is_template = 0
                              and p.pm_state in ('Chuẩn bị', 'Đang thực hiện')""",
                         {"open": ISSUE_OPEN, "today": getdate(today)}, as_dict=True)
    return [alerts._hit("PM Issue", r.name, r.project, r.task, str(r.due_date),
                        _("Vấn đề quá hạn xử lý ({0}): {1}").format(getdate(r.due_date).strftime("%d/%m"), r.title),
                        direct=[u for u in (r.owner_user, r.pm_manager) if u]) for r in rows]


# --- change requests ----------------------------------------------------------------------------------------------------

def _change_tasks(project: str, tasks) -> list[dict]:
    if isinstance(tasks, str):
        tasks = frappe.parse_json(tasks or "[]")
    out = []
    for row in tasks or []:
        if not row.get("task"):
            continue
        _task(project, row["task"])
        out.append({"task": row["task"], "new_end": getdate(row["new_end"]) if row.get("new_end") else None,
                    "note": (row.get("note") or "").strip()[:140] or None})
    return out


def save_change(project: str, values: dict, tasks=None, name=None) -> dict:
    values = {k: v for k, v in (frappe.parse_json(values) if isinstance(values, str) else values or {}).items()
              if k in CHANGE_FIELDS}
    if name:
        doc = frappe.get_doc("PM Change Request", name)
        _assert_read(doc.project)
        if doc.status != DRAFT:
            frappe.throw(_("Chỉ sửa được phát sinh còn nháp"))
        if doc.requested_by != frappe.session.user and not has_project_capability(doc.project, "change.approve"):
            frappe.throw(_("Chỉ người lập hoặc người duyệt sửa được phát sinh này"), frappe.PermissionError)
        doc.update(values)
        if tasks is not None:
            doc.set("tasks", _change_tasks(doc.project, tasks))
        doc.save(ignore_permissions=True)
    else:
        _assert(project, "change.request", _("Vai trò của bạn trong dự án không lập được phát sinh"))
        doc = frappe.get_doc({"doctype": "PM Change Request", "project": project, "status": DRAFT,
                              "requested_by": frappe.session.user, **values,
                              "tasks": _change_tasks(project, tasks)})
        doc.insert(ignore_permissions=True)
    return doc.as_dict()


def submit_change(name) -> dict:
    doc = frappe.get_doc("PM Change Request", name)
    _assert_read(doc.project)
    if doc.status != DRAFT:
        frappe.throw(_("Phát sinh này không còn nháp"))
    if doc.requested_by != frappe.session.user and not has_project_capability(doc.project, "change.approve"):
        frappe.throw(_("Chỉ người lập gửi duyệt được phát sinh này"), frappe.PermissionError)
    doc.db_set({"status": WAITING, "submitted_on": now_datetime()})
    activity.record("Project", doc.project, "Thay đổi", _("Gửi duyệt phát sinh {0}: {1}").format(doc.name, doc.title),
                    data={"change_request": doc.name, "state": WAITING})
    from project_manager.project_manager.policy import capabilities_in

    members = frappe.get_all("PM Project Member", filters={"project": doc.project, "is_active": 1}, pluck="user")
    for user in sorted(set(members)):
        if user != frappe.session.user and "change.approve" in capabilities_in(doc.project, user):
            notify.notify_user(user, _("Phát sinh chờ duyệt: {0}").format(doc.title), _link(doc.project, "phat-sinh"),
                               "PM Change Request", doc.name)
    return {"name": doc.name, "status": WAITING}


def decide(name, approve: bool, note: str = "") -> dict:
    doc = frappe.get_doc("PM Change Request", name)
    _assert(doc.project, "change.approve", _("Vai trò của bạn trong dự án không duyệt được phát sinh"))
    if doc.status != WAITING:
        frappe.throw(_("Phát sinh này không chờ duyệt"))
    if doc.requested_by == frappe.session.user and not is_admin():
        frappe.throw(_("Người lập không tự duyệt phát sinh của mình"), frappe.PermissionError)
    note = (note or "").strip()
    if not approve and not note:
        frappe.throw(_("Ghi lý do từ chối"))
    frappe.db.sql("select name from `tabPM Change Request` where name = %s for update", name)
    values = {"status": APPROVED if cint(approve) else REJECTED, "decided_by": frappe.session.user,
              "decided_on": now_datetime(), "decision_note": note or None}
    moved = []
    if cint(approve):
        from project_manager.project_manager.services import budget, schedule

        values["budget"] = budget.add_change(doc.project, doc.name, doc.title, doc.cost_impact)
        reason = _("Phát sinh {0}: {1}").format(doc.name, doc.title)
        for row in doc.tasks:
            if row.new_end:
                schedule.apply(row.task, None, row.new_end, reason)
                moved.append(row.task)
    doc.db_set(values)
    text = (_("Duyệt phát sinh {0}: {1}") if cint(approve) else _("Từ chối phát sinh {0}: {1}")).format(doc.name, doc.title)
    activity.record("Project", doc.project, "Thay đổi", text + (f" ({note})" if note else ""),
                    data={"change_request": doc.name, "state": values["status"], "moved": moved})
    if doc.requested_by and doc.requested_by != frappe.session.user:
        notify.notify_user(doc.requested_by, text, _link(doc.project, "phat-sinh"), "PM Change Request", doc.name)
    return {"name": doc.name, "status": values["status"], "budget": values.get("budget"), "moved": moved}


def cancel_change(name) -> dict:
    doc = frappe.get_doc("PM Change Request", name)
    _assert_read(doc.project)
    if doc.status not in (DRAFT, WAITING):
        frappe.throw(_("Phát sinh đã có quyết định"))
    if doc.requested_by != frappe.session.user and not has_project_capability(doc.project, "change.approve"):
        frappe.throw(_("Chỉ người lập hoặc người duyệt hủy được phát sinh này"), frappe.PermissionError)
    doc.db_set("status", CANCELLED)
    return {"name": doc.name, "status": CANCELLED}
