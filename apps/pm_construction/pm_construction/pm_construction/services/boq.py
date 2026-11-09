"""Bills of quantities (BOQ): imported from Excel as numbered versions, approved, and turned into the WBS.

* Import (plan.edit): the sheet is read (services/boq_import.py), shown first (preview, nothing written), then kept as
  a new version "Nháp" with its lines (bulk insert).
* Approve (plan.edit): the version becomes the one in force (the previous approved one "Thay thế") and the WBS
  follows it: each section becomes a group "Hạng mục", each line a task "Công tác" with its unit, planned quantity,
  unit price and estimate value. The first approval builds the tree in one go; a later one updates the tasks it
  recognises (same number and description under the same section), adds the new lines and reports the lines that
  disappeared (their tasks stay: they may have history). The project's progress is then weighed by estimate value.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime
from project_manager.project_manager.policy import (
    assert_project_capability,
    get_access,
    has_project_capability,
    project_in,
)
from project_manager.project_manager.services import activity, rollup, tree
from project_manager.project_manager.services.queries import reserve_ids
from project_manager.project_manager.services.text import plain

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import boq_import, quantities

PREVIEW_LINES = 400
ITEM_FIELDS = ("name", "boq", "project", "line_no", "code", "norm_code", "description", "uom", "qty", "unit_price",
               "amount", "is_group", "level", "parent_line", "task", "note", "owner", "modified_by", "creation",
               "modified", "docstatus", "idx")


def _assert_read(project: str) -> None:
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))


def preview(project: str, content: bytes) -> dict:
    assert_project_capability(project, "plan.edit")
    parsed = boq_import.parse(content)
    return {**parsed, "items": parsed["items"][:PREVIEW_LINES], "lines": len(parsed["items"]),
            "issues": parsed["issues"][:200], "next_version": _next_version(project)}


def _next_version(project: str) -> int:
    return cint(frappe.db.sql("select max(version_no) from `tabPMC BOQ` where project = %s", project)[0][0]) + 1


def import_version(project: str, content: bytes, filename: str = "", title: str = "", note: str = "") -> dict:
    assert_project_capability(project, "plan.edit")
    parsed = boq_import.parse(content)
    frappe.db.sql("select name from `tabProject` where name = %s for update", project)  # one import at a time
    version = _next_version(project)
    doc = frappe.get_doc({
        "doctype": "PMC BOQ", "project": project, "version_no": version,
        "title": (title or "").strip()[:140] or _("BOQ bản {0}").format(version), "status": K.BOQ_DRAFT,
        "source_file": (filename or "")[:140], "item_count": parsed["works"], "total_value": parsed["total"],
        "imported_by": frappe.session.user, "imported_on": now_datetime(), "note": (note or "").strip()[:1000],
    })
    doc.insert(ignore_permissions=True)
    now, user = now_datetime(), frappe.session.user
    rows = []
    for number, item in zip(reserve_ids("PMC BOQ Item", len(parsed["items"])), parsed["items"]):
        rows.append((number, doc.name, project, item["line_no"], item["code"], item["norm_code"], item["description"],
                     item["uom"], item["qty"], item["unit_price"], item["amount"], item["is_group"], item["level"],
                     item["parent_line"], None, item["note"] or None, user, user, now, now, 0, 0))
    frappe.db.bulk_insert("PMC BOQ Item", ITEM_FIELDS, rows, chunk_size=1000)
    activity.record("Project", project, "Tệp", _("Nhập BOQ bản {0}: {1} công tác, tổng giá trị {2} đ").format(
        version, parsed["works"], f"{parsed['total']:,.0f}".replace(",", ".")), data={"boq": doc.name})
    return detail(doc.name)


# --- reading ----------------------------------------------------------------------------------------------------------

def versions(project: str) -> dict:
    _assert_read(project)
    rows = frappe.get_all("PMC BOQ", filters={"project": project},
                          fields=["name", "version_no", "title", "status", "item_count", "total_value", "source_file",
                                  "imported_by", "imported_on", "approved_by", "approved_on"],
                          order_by="version_no desc")
    return {"versions": rows, "summary": summary(project), "can": {"plan": has_project_capability(project, "plan.edit")}}


def summary(project: str) -> dict:
    """Value planned, done and accepted over the work items of the project (from the tasks)."""
    row = frappe.db.sql("""select count(*), sum(pmc_estimate_value),
                                  sum(case when pmc_planned_qty > 0
                                      then least(pmc_done_qty, pmc_planned_qty) * pmc_unit_price else 0 end),
                                  sum(case when pmc_planned_qty > 0
                                      then least(pmc_accepted_qty, pmc_planned_qty) * pmc_unit_price else 0 end)
                           from `tabTask` where project = %s and is_group = 0 and ifnull(pmc_boq_key, '') != ''
                           and status != 'Cancelled'""", project)[0]
    planned, done, accepted = flt(row[1]), flt(row[2]), flt(row[3])
    return {"works": cint(row[0]), "planned_value": planned, "done_value": done, "accepted_value": accepted,
            "done_percent": flt(done / planned * 100, 2) if planned else 0,
            "accepted_percent": flt(accepted / planned * 100, 2) if planned else 0}


def detail(name: str) -> dict:
    doc = frappe.db.get_value("PMC BOQ", name, ["name", "project", "version_no", "title", "status", "item_count",
                                                "total_value", "source_file", "imported_by", "imported_on",
                                                "approved_by", "approved_on", "note"], as_dict=True)
    if not doc:
        raise frappe.DoesNotExistError(_("Không tìm thấy BOQ"))
    _assert_read(doc.project)
    items = frappe.get_all("PMC BOQ Item", filters={"boq": name},
                           fields=["name", "line_no", "code", "norm_code", "description", "uom", "qty", "unit_price",
                                   "amount", "is_group", "level", "parent_line", "task"], order_by="line_no asc",
                           limit_page_length=0)
    tasks = {t.name: t for t in frappe.get_all(
        "Task", filters={"name": ["in", [i.task for i in items if i.task]] or [""]},
        fields=["name", "progress", "status", "pmc_done_qty", "pmc_accepted_qty", "pm_wbs_code"])}
    for item in items:
        task = tasks.get(item.task)
        item["done_qty"] = flt(task.pmc_done_qty) if task else 0
        item["accepted_qty"] = flt(task.pmc_accepted_qty) if task else 0
        item["progress"] = flt(task.progress) if task else 0
        item["wbs_code"] = task.pm_wbs_code if task else None
    doc["items"] = items
    doc["can"] = {"approve": doc.status == K.BOQ_DRAFT and has_project_capability(doc.project, "plan.edit")}
    return doc


# --- approving: the WBS follows the BOQ ---------------------------------------------------------------------------------

def _keys(items) -> dict:
    """{line_no: key}: a line is recognised across versions by its number and description under the same section."""
    by_line = {item.line_no: item for item in items}
    keys = {}
    for item in items:
        own = plain(f"{item.code}|{item.description}")
        parent = keys.get(cint(item.parent_line), "") if cint(item.parent_line) in by_line else ""
        keys[item.line_no] = hashlib.md5(f"{parent}>{own}".encode()).hexdigest()
    return keys


def approve(name: str) -> dict:
    doc = frappe.get_doc("PMC BOQ", name)
    assert_project_capability(doc.project, "plan.edit")
    if doc.status != K.BOQ_DRAFT:
        frappe.throw(_("Chỉ duyệt được BOQ đang ở trạng thái nháp"))
    frappe.db.sql("select name from `tabProject` where name = %s for update", doc.project)
    frappe.db.sql("update `tabPMC BOQ` set status = %s where project = %s and status = %s",
                  (K.BOQ_REPLACED, doc.project, K.BOQ_APPROVED))
    frappe.db.set_value("PMC BOQ", name, {"status": K.BOQ_APPROVED, "approved_by": frappe.session.user,
                                          "approved_on": now_datetime()})
    result = sync_wbs(name)
    activity.record("Project", doc.project, "Tệp", _("Duyệt BOQ bản {0}: {1} việc mới, {2} việc cập nhật{3}").format(
        doc.version_no, result["created"], result["updated"],
        _(", {0} dòng không còn trong BOQ").format(len(result["missing"])) if result["missing"] else ""),
        data={"boq": name, **{k: v for k, v in result.items() if k != "missing"}})
    return {**detail(name), "sync": result}


def sync_wbs(name: str) -> dict:
    boq = frappe.db.get_value("PMC BOQ", name, ["name", "project"], as_dict=True)
    project = boq.project
    items = frappe.get_all("PMC BOQ Item", filters={"boq": name},
                           fields=["name", "line_no", "code", "norm_code", "description", "uom", "qty", "unit_price",
                                   "amount", "is_group", "parent_line"], order_by="line_no asc", limit_page_length=0)
    keys = _keys(items)
    existing = dict(frappe.db.sql("""select pmc_boq_key, name from `tabTask`
                                     where project = %s and ifnull(pmc_boq_key, '') != ''""", project))
    if frappe.db.get_value("Project", project, "pm_rollup_method") != K.ESTIMATE_METHOD:
        frappe.db.set_value("Project", project, "pm_rollup_method", K.ESTIMATE_METHOD)
    task_of = {}  # line_no -> task
    created = updated = 0
    if not existing:
        nodes = [{"key": item.line_no, "parent_key": cint(item.parent_line) or None, "subject": item.description,
                  "is_group": cint(item.is_group), "pm_node_type": K.NODE_SECTION if item.is_group else K.NODE_WORK,
                  "task_weight": 0 if item.is_group else flt(item.amount), "pmc_estimate_value": flt(item.amount),
                  "description": _description(item)} for item in items]
        for item, task in zip(items, tree.bulk_insert(project, nodes)):
            task_of[item.line_no] = task
        created = len(items)
    else:
        for item in items:
            key = keys[item.line_no]
            if key in existing:
                task_of[item.line_no] = existing[key]
                continue
            parent = task_of.get(cint(item.parent_line))
            row = tree.add(project, item.description, parent, cint(item.is_group),
                           K.NODE_SECTION if item.is_group else K.NODE_WORK)
            task_of[item.line_no] = row["name"]
            created += 1
    wanted = {}
    for item in items:
        values = {"pmc_boq_key": keys[item.line_no], "pmc_boq_item": item.name}
        if not item.is_group:
            values.update(pmc_uom=item.uom, pmc_planned_qty=flt(item.qty), pmc_unit_price=flt(item.unit_price),
                          pmc_estimate_value=flt(item.amount), pmc_norm_code=item.norm_code or None,
                          task_weight=flt(item.amount))
        wanted[task_of[item.line_no]] = values
    before = _current(list(wanted)) if existing else {}
    known = set(existing.values())
    changes, replanned = {}, []
    for task, values in wanted.items():
        old = before.get(task)
        fields = {f: v for f, v in values.items() if old is None or _differs(old.get(f), v)}
        if fields:
            changes[task] = fields
        if task in known and set(fields) - {"pmc_boq_item"}:
            updated += 1
        if task in known and "pmc_planned_qty" in fields:
            replanned.append(task)
    _bulk_update("Task", changes)
    _bulk_update("PMC BOQ Item", {item.name: {"task": task_of[item.line_no]} for item in items})
    missing = sorted(set(existing) - set(keys.values()))
    missing_tasks = [existing[k] for k in missing]
    rollup.reconcile(project)
    quantities.refresh(replanned, _("Khối lượng thiết kế đổi theo BOQ mới"))  # planned quantity changed: progress moves
    from project_manager.project_manager.services import schedule

    schedule.mark(project)
    return {"created": created, "updated": updated, "missing": missing_tasks}


SYNC_FIELDS = ("pmc_boq_key", "pmc_boq_item", "pmc_uom", "pmc_planned_qty", "pmc_unit_price", "pmc_estimate_value",
               "pmc_norm_code", "task_weight")
CHUNK = 400


def _current(tasks: list) -> dict:
    """{task: its BOQ fields now}, a few hundred tasks per query."""
    out = {}
    for start in range(0, len(tasks), CHUNK):
        chunk = tasks[start:start + CHUNK]
        for row in frappe.db.sql(f"select name, {', '.join(SYNC_FIELDS)} from `tabTask` where name in %s",
                                 (tuple(chunk),), as_dict=True):
            out[row.name] = row
    return out


def _bulk_update(doctype: str, rows: dict) -> None:
    """{name: {field: value}} in one UPDATE per few hundred rows (CASE per column), not one per row."""
    names = list(rows)
    for start in range(0, len(names), CHUNK):
        chunk = names[start:start + CHUNK]
        fields = sorted({f for name in chunk for f in rows[name]})
        parts, values = [], []
        for field in fields:
            cases = [name for name in chunk if field in rows[name]]
            parts.append(f"`{field}` = case name {' '.join('when %s then %s' for _ in cases)} else `{field}` end")
            for name in cases:
                values += [name, rows[name][field]]
        frappe.db.sql(f"update `tab{doctype}` set {', '.join(parts)} where name in %s", (*values, tuple(chunk)))


def _differs(old, new) -> bool:
    if isinstance(new, float | int):
        return abs(flt(old) - flt(new)) > 1e-6
    return (old or "") != (new or "")


def _description(item) -> str:
    parts = [f"Mã hiệu: {item.norm_code}" if item.norm_code else "", f"Đơn vị: {item.uom}" if item.uom else ""]
    return " · ".join(p for p in parts if p) or None
