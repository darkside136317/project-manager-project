"""MS Project XML (MSPDI): export a project's plan, import one into a project.

Export: the WBS in tree order (outline level, WBS code), planned start and finish (08:00–17:00), duration in working
days of the project's calendar (8 hours a day), milestones, summary tasks, percent complete, the dependencies (FS, SS,
FF, SF and their lag), the people accountable or doing each task as resources and assignments. MS Project opens it as a
plan.

Import (preview first, then run, like the Excel import of the WBS): the tasks of the file under a node of the WBS (or
at the end of the project), their planned dates, milestones (node type "Mốc"), dependencies between imported tasks,
and the accountable person when a resource of the task is a member of the project (by email or full name). Progress in
the file is not imported: it is reported on the system. The file is read without its DOCTYPE (refused): no entities.
Who: plan.edit.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import assert_project_capability, get_access, project_in
from project_manager.project_manager.services import activity, assignments, tree
from project_manager.project_manager.services.workdays import calendar_of

NS = "http://schemas.microsoft.com/project"
MAX_BYTES = 10 * 1024 * 1024
MAX_TASKS = 5000
TENTHS_PER_DAY = 480 * 10  # LinkLag is in tenths of a minute; a day is 8 hours
TYPE_TO_CODE = {"0": "FF", "1": "FS", "2": "SF", "3": "SS"}
CODE_TO_TYPE = {v: k for k, v in TYPE_TO_CODE.items()}
MILESTONE = "Mốc"


# --- export -------------------------------------------------------------------------------------------------------------

def _stamp(day, end=False) -> str:
    return datetime.combine(getdate(day), time(17 if end else 8)).strftime("%Y-%m-%dT%H:%M:%S")


def _sub(parent, tag, text=None):
    node = ET.SubElement(parent, tag)
    if text is not None:
        node.text = str(text)
    return node


def export(project: str) -> tuple[str, bytes]:
    """(file name, MSPDI XML) of the project's plan (whatever the user may read of it)."""
    doc = frappe.get_doc("Project", project)
    doc.check_permission("read")
    tasks = frappe.get_list("Task", filters={"project": project, "status": ["!=", C.CANCELLED]},
                            fields=["name", "subject", "pm_wbs_code", "pm_level", "pm_path", "is_group", "exp_start_date",
                                    "exp_end_date", "progress", "pm_node_type", "description", "act_start_date",
                                    "act_end_date"], order_by="pm_path asc", limit_page_length=0)
    calendar = calendar_of(project)
    uid = {t.name: i for i, t in enumerate(tasks, start=1)}
    links = frappe.get_all("PM Task Dependency", filters={"project": project, "successor": ["in", list(uid) or [""]]},
                           fields=["predecessor", "successor", "dep_type", "lag_days"], limit_page_length=0)
    by_successor = {}
    for link in links:
        if link.predecessor in uid:
            by_successor.setdefault(link.successor, []).append(link)
    holders = frappe.get_all("PM Task Assignment", filters={"task": ["in", list(uid) or [""]], "is_active": 1,
                                                            "state": ["in", C.LIVE_STATES],
                                                            "raci": ["in", [C.ACCOUNTABLE, C.RESPONSIBLE]],
                                                            "user": ["is", "set"]},
                             fields=["task", "user"], order_by="raci asc", limit_page_length=0)
    people = sorted({h.user for h in holders})
    names = dict(frappe.get_all("User", filters={"name": ["in", people or [""]]}, fields=["name", "full_name"], as_list=True))
    resource = {user: i for i, user in enumerate(people, start=1)}

    root = ET.Element("Project", xmlns=NS)
    _sub(root, "SaveVersion", 14)
    _sub(root, "Name", f"{doc.pm_code or doc.name}.xml")
    _sub(root, "Title", doc.project_name)
    _sub(root, "ScheduleFromStart", 1)
    starts = [t.exp_start_date for t in tasks if t.exp_start_date] or [doc.expected_start_date or getdate()]
    ends = [t.exp_end_date for t in tasks if t.exp_end_date] or [doc.expected_end_date or getdate()]
    _sub(root, "StartDate", _stamp(min(getdate(d) for d in starts)))
    _sub(root, "FinishDate", _stamp(max(getdate(d) for d in ends), end=True))
    _sub(root, "MinutesPerDay", 480)
    _sub(root, "MinutesPerWeek", 480 * (7 - len(calendar.weekly_off)))
    _sub(root, "CalendarUID", 1)
    calendars = _sub(root, "Calendars")
    cal = _sub(calendars, "Calendar")
    _sub(cal, "UID", 1)
    _sub(cal, "Name", "Lịch dự án")
    _sub(cal, "IsBaseCalendar", 1)
    week = _sub(cal, "WeekDays")
    for day_type in range(1, 8):  # 1 = Sunday
        python_day = (day_type + 5) % 7
        day = _sub(week, "WeekDay")
        _sub(day, "DayType", day_type)
        working = python_day not in calendar.weekly_off
        _sub(day, "DayWorking", 1 if working else 0)
        if working:
            times = _sub(day, "WorkingTimes")
            for start, end in (("08:00:00", "12:00:00"), ("13:00:00", "17:00:00")):
                slot = _sub(times, "WorkingTime")
                _sub(slot, "FromTime", start)
                _sub(slot, "ToTime", end)

    nodes = _sub(root, "Tasks")
    for task in tasks:
        node = _sub(nodes, "Task")
        _sub(node, "UID", uid[task.name])
        _sub(node, "ID", uid[task.name])
        _sub(node, "Name", task.subject)
        _sub(node, "WBS", task.pm_wbs_code or "")
        _sub(node, "OutlineNumber", task.pm_wbs_code or "")
        _sub(node, "OutlineLevel", cint(task.pm_level) or 1)
        milestone = task.pm_node_type == MILESTONE
        if task.exp_start_date or task.exp_end_date:
            first = getdate(task.exp_start_date or task.exp_end_date)
            last = getdate(task.exp_end_date or task.exp_start_date)
            _sub(node, "Start", _stamp(first))
            _sub(node, "Finish", _stamp(last if not milestone else first, end=not milestone))
            days = 0 if milestone else max(1, calendar.count(first, last))
            _sub(node, "Duration", f"PT{days * 8}H0M0S")
            _sub(node, "DurationFormat", 7)
        _sub(node, "Milestone", 1 if milestone else 0)
        _sub(node, "Summary", 1 if task.is_group else 0)
        _sub(node, "PercentComplete", round(flt(task.progress)))
        if task.act_start_date:
            _sub(node, "ActualStart", _stamp(task.act_start_date))
        if task.act_end_date:
            _sub(node, "ActualFinish", _stamp(task.act_end_date, end=True))
        if task.description:
            _sub(node, "Notes", re.sub(r"<[^>]+>", "", task.description)[:4000])
        for link in by_successor.get(task.name, []):
            item = _sub(node, "PredecessorLink")
            _sub(item, "PredecessorUID", uid[link.predecessor])
            _sub(item, "Type", CODE_TO_TYPE.get(link.dep_type, "1"))
            _sub(item, "LinkLag", cint(link.lag_days) * TENTHS_PER_DAY)
            _sub(item, "LagFormat", 7)
    resources = _sub(root, "Resources")
    for user, number in resource.items():
        item = _sub(resources, "Resource")
        _sub(item, "UID", number)
        _sub(item, "ID", number)
        _sub(item, "Name", names.get(user) or user)
        _sub(item, "Type", 1)
        _sub(item, "EmailAddress", user)
    given = _sub(root, "Assignments")
    seen = set()
    for number, holder in enumerate(holders, start=1):
        if (holder.task, holder.user) in seen:
            continue
        seen.add((holder.task, holder.user))
        item = _sub(given, "Assignment")
        _sub(item, "UID", number)
        _sub(item, "TaskUID", uid[holder.task])
        _sub(item, "ResourceUID", resource[holder.user])
        _sub(item, "Units", 1)
    ET.indent(root)
    content = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(root, encoding="utf-8")
    return f"{doc.pm_code or doc.name}-ms-project.xml", content


# --- import -------------------------------------------------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(node, tag):
    return [child for child in node if _local(child.tag) == tag]


def _text(node, tag, default=None):
    for child in node:
        if _local(child.tag) == tag:
            return (child.text or "").strip()
    return default


def _when(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").date()
    except ValueError:
        try:
            return getdate(value[:10])
        except Exception:
            return None


def _root(content: bytes):
    if isinstance(content, str):
        content = content.encode("utf-8")
    if len(content) > MAX_BYTES:
        frappe.throw(_("Tệp lớn hơn 10 MB"))
    head = content[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in content.lower():
        frappe.throw(_("Tệp có khai báo DOCTYPE hoặc ENTITY: không đọc tệp như vậy"))
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        frappe.throw(_("Không đọc được tệp XML: {0}").format(e))
    if _local(root.tag) != "Project":
        frappe.throw(_("Đây không phải tệp MS Project XML (thiếu thẻ Project)"))
    return root


def _members(project: str) -> dict:
    """{lower email or full name: user} of the project's active members."""
    users = frappe.get_all("PM Project Member", filters={"project": project, "is_active": 1}, pluck="user")
    out = {}
    for row in frappe.get_all("User", filters={"name": ["in", users or [""]], "enabled": 1}, fields=["name", "full_name"]):
        out[row.name.lower()] = row.name
        if row.full_name:
            out[row.full_name.strip().lower()] = row.name
    return out


def parse(project: str, content: bytes) -> dict:
    root = _root(content)
    tasks_node = next(iter(_children(root, "Tasks")), None)
    raw = _children(tasks_node, "Task") if tasks_node is not None else []
    members = _members(project)
    resources = {}
    for node in _children(next(iter(_children(root, "Resources")), ET.Element("x")), "Resource"):
        uid = _text(node, "UID")
        user = members.get((_text(node, "EmailAddress") or "").lower()) or members.get((_text(node, "Name") or "").lower())
        resources[uid] = (user, _text(node, "Name") or _text(node, "EmailAddress") or uid)
    owner_of = {}
    for node in _children(next(iter(_children(root, "Assignments")), ET.Element("x")), "Assignment"):
        task, res = _text(node, "TaskUID"), _text(node, "ResourceUID")
        if task and res in resources and task not in owner_of:
            owner_of[task] = resources[res]
    rows, by_uid, stack, errors, warnings = [], {}, [], 0, []
    progress_seen = 0
    for node in raw:
        level = cint(_text(node, "OutlineLevel", "1"))
        if level <= 0 or _text(node, "IsNull") == "1" or _text(node, "Active") == "0":
            continue  # the project's own summary task, empty or inactive rows
        uid = _text(node, "UID")
        item = {"uid": uid, "level": level, "subject": (_text(node, "Name") or "").strip()[:140], "errors": [],
                "warnings": [], "start": _when(_text(node, "Start")), "end": _when(_text(node, "Finish")),
                "milestone": _text(node, "Milestone") == "1", "note": (_text(node, "Notes") or "").strip()[:2000] or None}
        if flt(_text(node, "PercentComplete")):
            progress_seen += 1
        if not item["subject"]:
            item["errors"].append(_("Thiếu tên công việc"))
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        if level > (stack[-1]["level"] + 1 if stack else 1):
            item["errors"].append(_("Cấp {0} nằm ngay dưới cấp {1}: thiếu cấp ở giữa").format(
                level, stack[-1]["level"] if stack else 0))
        item["parent_uid"] = stack[-1]["uid"] if stack else None
        if item["start"] and item["end"] and item["end"] < item["start"]:
            item["errors"].append(_("Ngày kết thúc trước ngày bắt đầu"))
        owner = owner_of.get(uid)
        if owner:
            if owner[0]:
                item["owner"] = owner[0]
            else:
                item["warnings"].append(_("\"{0}\" không phải thành viên dự án: chưa giao").format(owner[1]))
        item["links"] = [{"predecessor": _text(link, "PredecessorUID"), "kind": TYPE_TO_CODE.get(_text(link, "Type", "1"), "FS"),
                          "lag": round(cint(_text(link, "LinkLag", "0")) / TENTHS_PER_DAY)}
                         for link in _children(node, "PredecessorLink")]
        errors += bool(item["errors"])
        rows.append(item)
        by_uid[uid] = item
        stack.append(item)
        if len(rows) > MAX_TASKS:
            frappe.throw(_("Tệp có hơn {0} công việc").format(MAX_TASKS))
    parents = {r["parent_uid"] for r in rows if r["parent_uid"]}
    links = 0
    for item in rows:
        item["is_group"] = 1 if item["uid"] in parents else 0
        if item["is_group"]:
            item["start"] = item["end"] = None  # a group's dates come from its children
        kept = []
        for link in item["links"]:
            if link["predecessor"] in by_uid:
                kept.append(link)
            else:
                item["warnings"].append(_("Bỏ phụ thuộc vào công việc {0} không có trong tệp").format(link["predecessor"]))
        item["links"] = kept
        links += len(kept)
    if progress_seen:
        warnings.append(_("{0} công việc có tiến độ trong tệp: tiến độ không được nhập, hãy cập nhật trên hệ thống").format(
            progress_seen))
    return {"title": _text(root, "Title") or _text(root, "Name"), "rows": rows, "errors": errors, "total": len(rows),
            "groups": sum(r["is_group"] for r in rows), "links": links, "assigned": sum(1 for r in rows if r.get("owner")),
            "warnings": warnings}


def preview(project: str, content: bytes) -> dict:
    assert_project_capability(project, "plan.edit")
    return parse(project, content)


def _insert_links(project: str, links: list[dict]) -> None:
    """The checked links in a few statements (ids from the DocType's sequence)."""
    from frappe.utils import now_datetime

    from project_manager.project_manager.services.queries import reserve_ids

    now, user = now_datetime(), frappe.session.user
    for start in range(0, len(links), 1000):
        chunk = links[start:start + 1000]
        ids = reserve_ids("PM Task Dependency", len(chunk))
        frappe.db.sql("insert into `tabPM Task Dependency` (name, project, predecessor, successor, dep_type, lag_days, "
                      "creation, modified, owner, modified_by, docstatus) values "
                      + ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)"] * len(chunk)),
                      [v for name, link in zip(ids, chunk, strict=True)
                       for v in (name, project, link["predecessor"], link["successor"], link["kind"], link["lag"], now, now,
                                 user, user)])


def run(project: str, content: bytes, parent: str | None = None) -> dict:
    from project_manager.project_manager.services import schedule

    assert_project_capability(project, "plan.edit")
    if parent and frappe.db.get_value("Task", parent, "project") != project:
        frappe.throw(_("Việc cha thuộc dự án khác"))
    result = parse(project, content)
    if result["errors"]:
        frappe.throw(_("Tệp còn {0} dòng lỗi: hãy sửa rồi nhập lại").format(result["errors"]))
    if not result["rows"]:
        frappe.throw(_("Tệp không có công việc nào"))
    milestone = frappe.db.exists("PM Node Type", MILESTONE)
    nodes = [{"key": r["uid"], "parent_key": r["parent_uid"], "subject": r["subject"], "is_group": r["is_group"],
              "pm_node_type": MILESTONE if r["milestone"] and milestone and not r["is_group"] else None,
              "exp_start_date": r["start"], "exp_end_date": r["end"], "description": r["note"]} for r in result["rows"]]
    names = tree.bulk_insert(project, nodes, parent)
    name_of = {r["uid"]: name for r, name in zip(result["rows"], names, strict=True)}
    wanted = [{"predecessor": name_of[link["predecessor"]], "successor": name_of[item["uid"]], "kind": link["kind"],
               "lag": cint(link["lag"]), "subject": item["subject"]} for item in result["rows"] for link in item["links"]]
    kept, refused = schedule.check_many(schedule.Network(project), wanted)
    skipped = [f"{link['subject']}: {why}" for link, why in refused]
    _insert_links(project, kept)
    linked = len(kept)
    assigned = 0
    for item in result["rows"]:
        if item.get("owner") and project_in(get_access(item["owner"]).read, project):
            assignments.assign(name_of[item["uid"]], C.ACCOUNTABLE, user=item["owner"], note=_("Nhập từ MS Project"))
            assigned += 1
    schedule.refresh(project)
    activity.record("Project", project, "Thay đổi", _("Nhập {0} công việc, {1} phụ thuộc từ MS Project").format(len(names), linked),
                    data={"tasks": len(names), "links": linked, "assigned": assigned, "parent": parent})
    return {"tasks": len(names), "links": linked, "assigned": assigned, "skipped": skipped}
