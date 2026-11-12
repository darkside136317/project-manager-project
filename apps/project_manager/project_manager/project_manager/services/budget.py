"""Ngân sách của dự án and its earned value (EVM).

* PM Budget: versions like the baselines. A draft (Nháp) is prepared from the one in use or from nothing, by cost
  category (Vật tư, Nhân công, Máy thi công, Thầu phụ, Chi phí chung, Dự phòng, Phát sinh, Khác), optionally on a node
  of the WBS. Approving it puts it in use (Đã duyệt) and the one before is replaced (Thay thế). An approved change
  request adds a "Phát sinh" line to the budget in use (services/control.py).
* Actual cost (AC): the timesheets of ERPNext (costing amount, by task: Nhân công) and what the industry layers report
  (hook pm_actual_costs: functions (project) returning [{"task", "category", "amount"}]; the construction layer gives
  the materials, machines and labour of its work items).
* Earned value, today: BAC = the budget in use; PV = BAC x planned progress (main baseline, else the plan); EV = BAC x
  progress; CPI = EV / AC, SPI = EV / PV, EAC = AC + (BAC - EV) / CPI, ETC = EAC - AC, VAC = BAC - EAC,
  TCPI = (BAC - EV) / (BAC - AC).
Who: finance.view (or budget.manage) reads; budget.manage prepares and approves.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

from project_manager.project_manager.policy import get_access, has_project_capability, project_in
from project_manager.project_manager.services import activity

DRAFT, APPROVED, REPLACED = "Nháp", "Đã duyệt", "Thay thế"
CATEGORIES = ("Vật tư", "Nhân công", "Máy thi công", "Thầu phụ", "Chi phí chung", "Dự phòng", "Phát sinh", "Khác")
CHANGE = "Phát sinh"
LINE_FIELDS = ("category", "task", "description", "amount", "change_request")


def may_read(project: str) -> bool:
    return project_in(get_access().read, project) and has_project_capability(project, "finance.view", "budget.manage")


def _assert_read(project: str) -> None:
    if not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)
    if not has_project_capability(project, "finance.view", "budget.manage"):
        frappe.throw(_("Vai trò của bạn trong dự án không xem được ngân sách"), frappe.PermissionError)


def _assert_manage(project: str) -> None:
    _assert_read(project)
    if not has_project_capability(project, "budget.manage"):
        frappe.throw(_("Vai trò của bạn trong dự án không lập, duyệt được ngân sách"), frappe.PermissionError)


def current(project: str) -> str | None:
    """The budget in use."""
    return frappe.db.get_value("PM Budget", {"project": project, "status": APPROVED}, "name", order_by="version desc")


def bac(project: str) -> float:
    name = current(project)
    return flt(frappe.db.get_value("PM Budget", name, "total")) if name else 0.0


# --- actual cost ------------------------------------------------------------------------------------------------------

def actual_costs(project: str) -> list[dict]:
    """[{"task", "category", "amount"}] of the project: timesheets, then the layers."""
    rows = [{"task": r.task, "category": "Nhân công", "amount": flt(r.amount)} for r in frappe.db.sql(
        """select d.task, sum(d.costing_amount) as amount from `tabTimesheet Detail` d
           join `tabTimesheet` t on t.name = d.parent
           where t.docstatus = 1 and d.project = %s and ifnull(d.costing_amount, 0) != 0 group by d.task""",
        project, as_dict=True)]
    for path in frappe.get_hooks("pm_actual_costs") or []:
        rows.extend(frappe.get_attr(path)(project) or [])
    return [r for r in rows if flt(r.get("amount"))]


# --- earned value -----------------------------------------------------------------------------------------------------

def _ratio(a, b):
    return round(flt(a) / flt(b), 3) if flt(b) else None


def evm(project: str, today=None, costs=None) -> dict:
    """The earned value figures of the project today (no permission check: callers check)."""
    from project_manager.project_manager.services import baseline, rollup

    today = getdate(today or nowdate())
    info = frappe.db.get_value("Project", project, ["percent_complete", "expected_start_date", "expected_end_date"],
                               as_dict=True) or frappe._dict()
    planned = flt(baseline.planned_on(project, today, rollup.planned_progress(info.expected_start_date,
                                                                              info.expected_end_date, today)))
    total = bac(project)
    progress = flt(info.percent_complete)
    actual = sum(flt(r["amount"]) for r in (actual_costs(project) if costs is None else costs))
    pv, ev = total * planned / 100, total * progress / 100
    cpi = _ratio(ev, actual)
    eac = (actual + (total - ev) / cpi) if cpi else (total if not actual else None)
    return {"bac": flt(total, 0), "planned_pct": flt(planned, 1), "progress_pct": flt(progress, 1), "pv": flt(pv, 0),
            "ev": flt(ev, 0), "ac": flt(actual, 0), "cv": flt(ev - actual, 0), "sv": flt(ev - pv, 0), "cpi": cpi,
            "spi": _ratio(ev, pv), "eac": None if eac is None else flt(eac, 0),
            "etc": None if eac is None else flt(eac - actual, 0), "vac": None if eac is None else flt(total - eac, 0),
            "tcpi": _ratio(total - ev, total - actual) if total > actual else None, "today": today.isoformat()}


# --- the screen -------------------------------------------------------------------------------------------------------

def _lines(name) -> list:
    return frappe.get_all("PM Budget Line", filters={"parent": name, "parenttype": "PM Budget"},
                          fields=["name", "idx", *LINE_FIELDS], order_by="idx asc", limit_page_length=0)


def _top_of(project: str) -> dict:
    """{task: (top-level node, its label)} of every node of the project."""
    rows = frappe.get_all("Task", filters={"project": project}, fields=["name", "pm_path", "subject", "pm_wbs_code"],
                          limit_page_length=0)
    by_path = {r.pm_path: r for r in rows if r.pm_path}
    out = {}
    for row in rows:
        top = by_path.get((row.pm_path or "").split(".")[0])
        if top:
            out[row.name] = (top.name, f"{top.pm_wbs_code or ''} {top.subject}".strip())
    return out


def overview(project: str) -> dict:
    _assert_read(project)
    budgets = frappe.get_all("PM Budget", filters={"project": project},
                             fields=["name", "title", "version", "status", "total", "prepared_by", "approved_by",
                                     "approved_on", "note", "modified"], order_by="version desc", limit_page_length=50)
    in_use = next((b for b in budgets if b.status == APPROVED), None)
    draft = next((b for b in budgets if b.status == DRAFT), None)
    costs = actual_costs(project)
    figures = evm(project, costs=costs)
    tops = _top_of(project)
    by_category = {c: {"category": c, "budget": 0.0, "actual": 0.0} for c in CATEGORIES}
    by_section = {}
    lines = _lines(in_use.name) if in_use else []
    for line in lines:
        by_category.setdefault(line.category, {"category": line.category, "budget": 0.0, "actual": 0.0})
        by_category[line.category]["budget"] += flt(line.amount)
        top = tops.get(line.task) if line.task else None
        key = top[0] if top else ""
        entry = by_section.setdefault(key, {"task": key or None, "label": top[1] if top else _("Chung cho dự án"),
                                            "budget": 0.0, "actual": 0.0})
        entry["budget"] += flt(line.amount)
    for row in costs:
        category = row.get("category") or "Khác"
        by_category.setdefault(category, {"category": category, "budget": 0.0, "actual": 0.0})
        by_category[category]["actual"] += flt(row["amount"])
        top = tops.get(row.get("task")) if row.get("task") else None
        key = top[0] if top else ""
        entry = by_section.setdefault(key, {"task": key or None, "label": top[1] if top else _("Chung cho dự án"),
                                            "budget": 0.0, "actual": 0.0})
        entry["actual"] += flt(row["amount"])
    labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", [l.task for l in [*lines, *(_lines(draft.name) if draft else [])] if l.task] or [""]]},
        fields=["name", "subject", "pm_wbs_code"])}
    def shown(rows):
        return [{**r, "task_label": labels.get(r.task)} for r in rows]
    manage = has_project_capability(project, "budget.manage")
    return {"budgets": budgets, "in_use": in_use and {**in_use, "lines": shown(lines)},
            "draft": draft and {**draft, "lines": shown(_lines(draft.name))}, "evm": figures,
            "by_category": [r for r in by_category.values() if r["budget"] or r["actual"]],
            "by_section": sorted(by_section.values(), key=lambda r: (r["task"] is None, r["label"])),
            "categories": list(CATEGORIES), "can": {"manage": manage}}


# --- drafts and approval --------------------------------------------------------------------------------------------

def _clean_lines(project: str, lines) -> list[dict]:
    if isinstance(lines, str):
        lines = frappe.parse_json(lines or "[]")
    out = []
    for row in lines or []:
        amount = flt(row.get("amount"))
        if not amount and not row.get("description"):
            continue
        category = row.get("category") or "Khác"
        if category not in CATEGORIES:
            frappe.throw(_("Khoản mục không hợp lệ: {0}").format(category))
        out.append({"category": category, "task": row.get("task") or None,
                    "description": (row.get("description") or "").strip()[:140] or None, "amount": amount,
                    "change_request": row.get("change_request") or None})
    return out


def save_draft(project: str, title: str, lines, note: str = "", name=None) -> dict:
    """Create or change the draft of the project (one draft at a time)."""
    _assert_manage(project)
    rows = _clean_lines(project, lines)
    if name:
        doc = frappe.get_doc("PM Budget", name)
        if doc.project != project or doc.status != DRAFT:
            frappe.throw(_("Chỉ sửa được ngân sách nháp"))
        doc.title, doc.note = (title or doc.title).strip(), (note or "").strip() or None
        doc.set("lines", rows)
        doc.save(ignore_permissions=True)
    else:
        if frappe.db.exists("PM Budget", {"project": project, "status": DRAFT}):
            frappe.throw(_("Dự án đã có một ngân sách nháp: sửa bản đó"))
        version = cint(frappe.db.sql("select max(version) from `tabPM Budget` where project = %s", project)[0][0]) + 1
        doc = frappe.get_doc({"doctype": "PM Budget", "project": project, "version": version, "status": DRAFT,
                              "title": (title or "").strip() or _("Ngân sách lần {0}").format(version),
                              "note": (note or "").strip() or None, "prepared_by": frappe.session.user, "lines": rows})
        doc.insert(ignore_permissions=True)
    return {"name": doc.name, "total": doc.total, "version": doc.version}


def start_from_current(project: str) -> dict:
    """A draft copying the budget in use (the way to revise it)."""
    _assert_manage(project)
    name = current(project)
    if not name:
        frappe.throw(_("Chưa có ngân sách đang dùng"))
    source = frappe.get_doc("PM Budget", name)
    return save_draft(project, _("{0} (điều chỉnh)").format(source.title),
                      [{f: line.get(f) for f in LINE_FIELDS} for line in source.lines], source.note or "")


def approve(name, note: str = "") -> dict:
    doc = frappe.get_doc("PM Budget", name)
    _assert_manage(doc.project)
    if doc.status != DRAFT:
        frappe.throw(_("Chỉ duyệt được ngân sách nháp"))
    if not doc.lines:
        frappe.throw(_("Ngân sách chưa có dòng nào"))
    frappe.db.sql("select name from `tabProject` where name = %s for update", doc.project)
    for old in frappe.get_all("PM Budget", filters={"project": doc.project, "status": APPROVED}, pluck="name"):
        frappe.db.set_value("PM Budget", old, "status", REPLACED)
    doc.db_set({"status": APPROVED, "approved_by": frappe.session.user, "approved_on": now_datetime()})
    text = _("Duyệt ngân sách {0}: {1}").format(doc.title, frappe.format_value(doc.total, {"fieldtype": "Currency"}))
    activity.record("Project", doc.project, "Thay đổi", text + (f" ({note.strip()})" if (note or "").strip() else ""),
                    data={"budget": doc.name, "total": flt(doc.total)})
    return {"name": doc.name, "status": APPROVED, "total": doc.total}


def discard(name) -> dict:
    doc = frappe.get_doc("PM Budget", name)
    _assert_manage(doc.project)
    if doc.status != DRAFT:
        frappe.throw(_("Chỉ bỏ được ngân sách nháp"))
    frappe.delete_doc("PM Budget", name, ignore_permissions=True)
    return {"deleted": name}


def add_change(project: str, change_request: str, title: str, amount) -> str | None:
    """Add an approved change request to the budget in use (called by services/control.py). None: no budget yet."""
    name = current(project)
    if not name or not flt(amount):
        return None
    doc = frappe.get_doc("PM Budget", name)
    doc.append("lines", {"category": CHANGE, "description": title[:140], "amount": flt(amount),
                         "change_request": change_request})
    doc.save(ignore_permissions=True)
    return doc.name
