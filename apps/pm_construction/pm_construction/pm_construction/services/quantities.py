"""Quantities of a work item (công tác): planned (from the approved BOQ), done (site diaries), accepted (acceptance
records). The done quantity is never typed in: it is the sum of the quantities of the task's submitted or confirmed
diaries, recomputed whenever one of them changes state, and the task's progress follows it (done / planned)."""

import frappe
from frappe import _
from frappe.utils import flt
from project_manager.project_manager.services import progress

from pm_construction.pm_construction import constants as K


def done_of(tasks) -> dict:
    tasks = [t for t in set(tasks or []) if t]
    if not tasks:
        return {}
    rows = frappe.db.sql("""select q.task, sum(q.qty) from `tabPMC Diary Quantity` q
                            join `tabPMC Site Diary` d on d.name = q.diary
                            where q.task in %s and d.status in %s group by q.task""",
                         (tuple(tasks), K.DIARY_COUNTED))
    return {task: flt(total, 6) for task, total in rows}


def percent(done, planned) -> float:
    planned = flt(planned)
    return min(100.0, flt(done) / planned * 100) if planned > 0 else 0.0


def refresh(tasks, note: str = "") -> int:
    """Store the done quantity of these tasks and move their progress with it. Returns how many changed."""
    tasks = [t for t in set(tasks or []) if t]
    if not tasks:
        return 0
    done = done_of(tasks)
    changed = 0
    for row in frappe.get_all("Task", filters={"name": ["in", tasks]},
                              fields=["name", "pmc_planned_qty", "pmc_done_qty", "is_group", "progress"],
                              limit_page_length=0):
        quantity = done.get(row.name, 0.0)
        if abs(flt(row.pmc_done_qty) - quantity) > 1e-9:
            frappe.db.set_value("Task", row.name, "pmc_done_qty", quantity, update_modified=False)
            changed += 1
        if row.is_group or flt(row.pmc_planned_qty) <= 0:
            continue
        target = flt(percent(quantity, row.pmc_planned_qty), 2)
        if abs(flt(row.progress) - target) >= 0.005 and not (target >= 100 and flt(row.progress) == 99):
            progress.set_measured(row.name, target, note)  # loads the task only when its figure moves
    return changed


def guard_task_delete(doc, method=None):
    """Task.on_trash: a work item with quantities in a diary keeps its history; BOQ lines forget a deleted task."""
    if frappe.db.exists("PMC Diary Quantity", {"task": doc.name}):
        frappe.throw(_("Công tác đã có khối lượng trong nhật ký thi công: hãy hủy thay vì xóa"),
                     title=_("Không xóa được"))
    frappe.db.sql("update `tabPMC BOQ Item` set task = null where task = %s", doc.name)
