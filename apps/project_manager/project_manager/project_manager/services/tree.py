"""The WBS tree of a project as the SPA edits it: read a level, add, change, move, cancel, delete.

Numbering is services/wbs.py's; this module adds the rules people see:

* Structure (add, move, delete, rename) needs `plan.edit` in the project; a date change needs `plan.edit` or
  `task.assign`. Once someone holds a live assignment on a task, changing its dates needs a reason, and the change goes
  to the timeline with it (services/progress.record_activity): a deadline never moves silently.
* A group's dates, progress and status come from its children (roll-up): they are not edited by hand.
* Adding under a leaf turns the leaf into a group. A task with history (assignments, progress reports, timeline) is
  cancelled, not deleted.
* `bulk_insert` writes many tasks in one statement with their tree position already computed (project templates, Excel
  import): no per-row save, no per-row numbering.
"""

import frappe
from frappe import _
from frappe.model.naming import NamingSeries
from frappe.utils import cint, getdate, now_datetime

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import assert_project_capability, get_access, has_project_capability
from project_manager.project_manager.services import activity, rollup, wbs

MAX_LEVEL_ROWS = 500
TREE_FIELDS = ["name", "subject", "is_group", "status", "progress", "exp_start_date", "exp_end_date", "pm_wbs_code",
               "pm_level", "pm_sort", "pm_node_type", "pm_accountable", "pm_reviewer", "pm_is_overdue", "pm_delay_days",
               "parent_task", "priority", "task_weight", "pm_is_critical", "pm_conflict_days"]
EDITABLE = ("subject", "description", "pm_node_type", "task_weight", "priority", "exp_start_date", "exp_end_date")
DATE_FIELDS = ("exp_start_date", "exp_end_date")


def _project_of(task: str) -> str:
    project = frappe.db.get_value("Task", task, "project")
    if project is None and not frappe.db.exists("Task", task):
        frappe.throw(_("Không tìm thấy công việc {0}").format(task), frappe.DoesNotExistError)
    return project


def children(project: str, parent: str | None = None, start: int = 0, limit: int = MAX_LEVEL_ROWS) -> dict:
    """One level of the tree (lazy). A person who only sees the tasks given to them gets those tasks as a flat list,
    since the groups above them are not theirs to see."""
    frappe.get_doc("Project", project).check_permission("read")
    limit = max(1, min(cint(limit) or MAX_LEVEL_ROWS, MAX_LEVEL_ROWS))
    access = get_access()
    flat = access.read_tasks is not None and project not in access.read_tasks
    filters = {"project": project}
    if not flat:
        filters["parent_task"] = parent or ("is", "not set")
    rows = frappe.get_list("Task", filters=filters, fields=TREE_FIELDS,
                           order_by="pm_path asc" if flat else "pm_sort asc, creation asc",
                           start=max(0, cint(start)), page_length=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    _decorate(rows)
    return {"rows": rows, "more": more, "flat": flat,
            "can_plan": has_project_capability(project, "plan.edit"),
            "can_assign": has_project_capability(project, "task.assign")}


def _decorate(rows) -> None:
    names = [r.name for r in rows if r.is_group]
    counts = dict(frappe.db.sql(
        "select parent_task, count(*) from `tabTask` where parent_task in %(names)s group by parent_task",
        {"names": tuple(names)})) if names else {}
    people = {r.pm_accountable for r in rows if r.pm_accountable}
    full_names = dict(frappe.get_all("User", filters={"name": ["in", list(people)]}, fields=["name", "full_name"],
                                     as_list=True)) if people else {}
    for row in rows:
        row["children"] = cint(counts.get(row.name))
        row["status_label"] = C.STATUS_LABELS.get(row.status, row.status)
        row["accountable_name"] = full_names.get(row.pm_accountable) if row.pm_accountable else None


def _make_group(parent: str) -> None:
    info = frappe.db.get_value("Task", parent, ["is_group", "project"], as_dict=True)
    if not info:
        frappe.throw(_("Không tìm thấy việc cha {0}").format(parent))
    if info.is_group:
        return
    if frappe.db.exists("PM Progress Entry", {"task": parent}):
        frappe.throw(_("Việc {0} đã có báo cáo tiến độ nên không chia nhỏ được: hãy thêm việc ở cấp trên").format(parent))
    frappe.db.set_value("Task", parent, "is_group", 1, update_modified=False)
    activity.record("Task", parent, "Thay đổi", _("Chia nhỏ thành nhóm công việc"))


def add(project: str, subject: str, parent: str | None = None, is_group: int = 0, node_type: str | None = None,
        start=None, end=None, weight=None) -> dict:
    assert_project_capability(project, "plan.edit")
    subject = (subject or "").strip()
    if not subject:
        frappe.throw(_("Hãy nhập tên công việc"))
    if parent:
        if _project_of(parent) != project:
            frappe.throw(_("Việc cha thuộc dự án khác"))
        _make_group(parent)
    if node_type:
        is_group = cint(frappe.db.get_value("PM Node Type", node_type, "is_group")) or cint(is_group)
    doc = frappe.get_doc({"doctype": "Task", "project": project, "subject": subject, "parent_task": parent or None,
                          "is_group": cint(is_group), "pm_node_type": node_type or None, "exp_start_date": start or None,
                          "exp_end_date": end or None, "task_weight": weight or 0, "status": C.OPEN})
    doc.insert()
    rows = frappe.get_list("Task", filters={"name": doc.name}, fields=TREE_FIELDS)
    _decorate(rows)
    return rows[0]


def _has_live_assignment(task: str) -> bool:
    return bool(frappe.db.exists("PM Task Assignment", {"task": task, "is_active": 1, "state": ["in", C.LIVE_STATES]}))


def update(task: str, values: dict, reason: str = "") -> dict:
    """Change the fields of one task. Dates of a task someone is working on need a reason."""
    doc = frappe.get_doc("Task", task)
    values = {k: v for k, v in (values or {}).items() if k in EDITABLE}
    if not values:
        frappe.throw(_("Không có gì để thay đổi"))
    structure = set(values) - set(DATE_FIELDS)
    if structure:
        assert_project_capability(doc.project, "plan.edit")
    dates_changed = [f for f in DATE_FIELDS if f in values and _date(values[f]) != _date(doc.get(f))]
    if dates_changed:
        assert_project_capability(doc.project, "plan.edit", "task.assign")
        if doc.is_group and frappe.db.exists("Task", {"parent_task": task}):
            frappe.throw(_("Ngày của nhóm được tính từ các việc con: hãy đổi ngày của việc con"))
        if _has_live_assignment(task) and not (reason or "").strip():
            frappe.throw(_("Công việc đã giao cho người thực hiện: hãy ghi lý do đổi ngày"), title=_("Thiếu lý do"))
    for field, value in values.items():
        doc.set(field, (value or None) if field in DATE_FIELDS else value)
    doc.flags.pm_reason = (reason or "").strip()
    doc.save(ignore_permissions=True)
    rows = frappe.get_list("Task", filters={"name": task}, fields=TREE_FIELDS)
    _decorate(rows)
    return rows[0]


def _date(value):
    return getdate(value) if value else None


def move(task: str, parent: str | None = None, index: int | None = None, reason: str = "") -> dict:
    """Put `task` under `parent` (None = a root of the project), at position `index` among its new siblings (0-based;
    None = last)."""
    doc = frappe.get_doc("Task", task)
    project = doc.project
    assert_project_capability(project, "plan.edit")
    parent = parent or None
    if parent:
        if _project_of(parent) != project:
            frappe.throw(_("Chỉ di chuyển trong cùng một dự án"))
        _make_group(parent)
    if (doc.parent_task or None) != parent:
        doc.parent_task = parent
        doc.flags.pm_reason = (reason or "").strip()
        doc.save(ignore_permissions=True)
    if index is not None:
        siblings = frappe.get_all("Task", filters={"project": project, "parent_task": parent or ("is", "not set")},
                                  order_by="pm_sort asc, creation asc", pluck="name", limit_page_length=0)
        siblings.remove(task)
        siblings.insert(max(0, min(cint(index), len(siblings))), task)
        renumber(project, parent, siblings)
    return frappe.db.get_value("Task", task, ["name", "parent_task", "pm_wbs_code", "pm_level"], as_dict=True)


def renumber(project: str, parent: str | None, order: list[str]) -> int:
    """Give the children of `parent` the positions 1, 2, 3 ... in `order`, and their subtrees the matching paths.
    Only rows whose numbers change are written. Returns that number."""
    if parent:
        base = frappe.db.get_value("Task", parent, ["pm_path", "pm_wbs_code", "pm_level"], as_dict=True)
        prefix = base.pm_path.replace("%", r"\%").replace("_", r"\_") + ".%"
        rows = frappe.db.sql("""select name, parent_task, pm_sort, pm_path, pm_wbs_code, pm_level, creation from `tabTask`
                                where project = %s and pm_path like %s""", (project, prefix), as_dict=True)
    else:
        base = frappe._dict(pm_path="", pm_wbs_code="", pm_level=0)
        rows = frappe.db.sql("""select name, parent_task, pm_sort, pm_path, pm_wbs_code, pm_level, creation from `tabTask`
                                where project = %s""", project, as_dict=True)
    by_parent = {}
    for row in rows:
        by_parent.setdefault(row.parent_task or None, []).append(row)
    position = {name: i for i, name in enumerate(order)}
    updates = []

    def walk(nodes, path, code, level, ordered):
        if ordered:
            nodes.sort(key=lambda r: position.get(r.name, len(position)))
        else:
            nodes.sort(key=lambda r: (cint(r.pm_sort) or wbs.MAX_SIBLINGS, r.creation, r.name))
        for i, node in enumerate(nodes, 1):
            own_path = f"{path}.{wbs.segment(i)}" if path else wbs.segment(i)
            own_code = f"{code}.{i}" if code else str(i)
            if (cint(node.pm_sort), node.pm_path, node.pm_wbs_code, cint(node.pm_level)) != (i, own_path, own_code, level):
                updates.append((i, own_path, own_code, level, node.name))
            walk(by_parent.get(node.name, []), own_path, own_code, level + 1, False)

    walk(by_parent.get(parent, []), base.pm_path, base.pm_wbs_code, cint(base.pm_level) + 1, True)
    write_positions(updates)
    return len(updates)


def write_positions(updates: list[tuple]) -> None:
    """[(pm_sort, pm_path, pm_wbs_code, pm_level, name)] in statements of 500 rows."""
    for chunk in range(0, len(updates), 500):
        batch = updates[chunk:chunk + 500]
        frappe.db.sql(
            "update `tabTask` set pm_sort = case name {s} end, pm_path = case name {p} end, pm_wbs_code = case name {c} end,"
            " pm_level = case name {l} end where name in ({names})".format(
                s=" ".join(f"when {frappe.db.escape(u[4])} then {cint(u[0])}" for u in batch),
                p=" ".join(f"when {frappe.db.escape(u[4])} then {frappe.db.escape(u[1])}" for u in batch),
                c=" ".join(f"when {frappe.db.escape(u[4])} then {frappe.db.escape(u[2])}" for u in batch),
                l=" ".join(f"when {frappe.db.escape(u[4])} then {cint(u[3])}" for u in batch),
                names=", ".join(frappe.db.escape(u[4]) for u in batch)))


def cancel(task: str, reason: str) -> dict:
    """Stop a leaf task that will not be done (it keeps its history and stops counting in the roll-up)."""
    doc = frappe.get_doc("Task", task)
    assert_project_capability(doc.project, "plan.edit")
    if doc.is_group:
        frappe.throw(_("Hãy hủy từng việc con của nhóm"))
    if not (reason or "").strip():
        frappe.throw(_("Hãy ghi lý do hủy"))
    if doc.status == C.CANCELLED:
        return {"name": task, "status": doc.status}
    doc.status = C.CANCELLED
    doc.flags.pm_reason = reason.strip()
    doc.flags.pm_history_type = "Trạng thái"
    doc.save(ignore_permissions=True)
    for name in frappe.get_all("PM Task Assignment", filters={"task": task, "is_active": 1,
                                                              "state": ["in", C.LIVE_STATES]}, pluck="name"):
        frappe.db.set_value("PM Task Assignment", name, {"state": C.REVOKED, "is_active": 0, "ended_by": frappe.session.user,
                                                         "ended_on": now_datetime(), "end_reason": _("Việc bị hủy")})
    frappe.db.set_value("Task", task, {"pm_accountable": None, "pm_reviewer": None}, update_modified=False)
    return {"name": task, "status": C.CANCELLED}


def delete(task: str) -> dict:
    """Delete a task that has no history. Anything with a history is cancelled instead."""
    doc = frappe.get_doc("Task", task)
    assert_project_capability(doc.project, "plan.edit")
    if frappe.db.exists("Task", {"parent_task": task}):
        frappe.throw(_("Hãy xóa hoặc chuyển các việc con trước"))
    for doctype, what in (("PM Task Assignment", _("đã giao việc")), ("PM Progress Entry", _("đã báo cáo tiến độ")),
                          ("PM Form Submission", _("đã có biểu mẫu")), ("PM Baseline Task", _("đã có trong baseline")),
                          ("PM Activity", _("đã có trao đổi, lịch sử"))):
        if frappe.db.exists(doctype, {"task": task}):
            frappe.throw(_("Công việc {0}: hãy hủy thay vì xóa để giữ lịch sử").format(what), title=_("Không xóa được"))
    frappe.db.delete("PM Gate Requirement", {"task": task})
    frappe.db.delete("PM Task Dependency", {"predecessor": task})
    frappe.db.delete("PM Task Dependency", {"successor": task})
    project, subject, code = doc.project, doc.subject, doc.pm_wbs_code
    frappe.delete_doc("Task", task)
    activity.record("Project", project, "Thay đổi", _("Xóa công việc {0} {1}").format(code or "", subject).strip(),
                    data={"task": task})
    return {"name": task, "deleted": True}


# --- bulk -----------------------------------------------------------------------------------------------------------

def reserve_names(count: int) -> list[str]:
    """`count` new Task names, reserved with one update of the naming series."""
    if count <= 0:
        return []
    series = NamingSeries(frappe.get_meta("Task").autoname)
    prefix = series.get_prefix()
    digits = series.series.count("#") or 5
    current = frappe.db.sql("select `current` from `tabSeries` where name = %s for update", prefix)
    if not current:
        frappe.db.sql("insert into `tabSeries` (name, `current`) values (%s, 0)", prefix)
        start = 1
    else:
        start = cint(current[0][0]) + 1
    frappe.db.sql("update `tabSeries` set `current` = %s where name = %s", (start + count - 1, prefix))
    return [f"{prefix}{i:0{digits}d}" for i in range(start, start + count)]


BULK_FIELDS = ("name", "subject", "description", "project", "company", "parent_task", "old_parent", "is_group",
               "status", "progress", "priority", "task_weight", "exp_start_date", "exp_end_date", "pm_node_type",
               "pm_sort", "pm_path", "pm_wbs_code", "pm_level", "pm_rollup_weight", "lft", "rgt", "is_template",
               "owner", "modified_by", "creation", "modified", "docstatus", "idx")


def bulk_insert(project: str, nodes: list[dict], parent: str | None = None) -> list[str]:
    """Insert a subtree at the end of `parent`'s children (the roots when None) in a few statements.

    `nodes` are dicts in tree order (parents before children) with a local `key`, an optional `parent_key` and the task
    fields (subject, is_group, dates, pm_node_type, task_weight, description, priority). Returns the new names, in the
    order of `nodes`. The roll-up of the project is recomputed afterwards.
    """
    if not nodes:
        return []
    names = reserve_names(len(nodes))
    company = frappe.db.get_value("Project", project, "company")
    method = rollup.method_of(project)
    if parent:
        base = frappe.db.get_value("Task", parent, ["pm_path", "pm_wbs_code", "pm_level"], as_dict=True)
    else:
        base = frappe._dict(pm_path="", pm_wbs_code="", pm_level=0)
    first = wbs._lock_and_next_sort(project, parent, None)
    now, user = now_datetime(), frappe.session.user
    position = {}
    sorts = {}
    rows = []
    for name, node in zip(names, nodes):
        parent_key = node.get("parent_key")
        if parent_key is not None and parent_key not in position:
            frappe.throw(_("Việc cha của dòng {0} phải đứng trước nó").format(node.get("subject")))
        parent_name, parent_path, parent_code, parent_level = (
            position[parent_key] if parent_key is not None else (parent, base.pm_path, base.pm_wbs_code, cint(base.pm_level)))
        sort = sorts.get(parent_key, (first - 1) if parent_key is None else 0) + 1
        sorts[parent_key] = sort
        path = f"{parent_path}.{wbs.segment(sort)}" if parent_path else wbs.segment(sort)
        code = f"{parent_code}.{sort}" if parent_code else str(sort)
        level = parent_level + 1
        position[node["key"]] = (name, path, code, level)
        values = frappe._dict(node)
        values.status = C.OPEN
        weight = 0 if cint(node.get("is_group")) else rollup.leaf_weight(values, method)
        rows.append((name, node["subject"][:140], node.get("description"), project, company, parent_name, parent_name,
                     cint(node.get("is_group")), C.OPEN, 0, node.get("priority") or "Medium", node.get("task_weight") or 0,
                     node.get("exp_start_date"), node.get("exp_end_date"), node.get("pm_node_type"),
                     sort, path, code, level, weight, 0, 0, 0, user, user, now, now, 0, 0))
    if parent:
        _make_group(parent)
    frappe.db.bulk_insert("Task", BULK_FIELDS, rows, chunk_size=500)
    rollup.reconcile(project)
    return names
