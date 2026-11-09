"""Acceptance (nghiệm thu): records are forms of the core (M3) from the pack setup/form_pack.py, so they have the core's
designer, approval, signatures, PDF and closing conditions. This module adds what construction needs:

* when a work acceptance (NT-CONGVIEC) of a task is approved, the task's accepted quantity becomes the sum of its
  approved work acceptances (core hook pm_form_events);
* an overview of each work item: planned, done (diaries), accepted (records), and the records themselves.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt
from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import get_access, has_project_capability, project_in

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import boq


def accepted_of(task: str) -> float:
    total = 0.0
    for data in frappe.get_all("PM Form Submission", filters={"task": task, "template_code": K.QTY_ACCEPTANCE_CODE,
                                                              "state": C.SUB_APPROVED}, pluck="data"):
        try:
            total += flt((json.loads(data or "{}") or {}).get(K.QTY_FIELD))
        except ValueError:
            continue
    return flt(total, 6)


def on_form_approved(submission: str) -> None:
    """Core hook pm_form_events["approved"]."""
    row = frappe.db.get_value("PM Form Submission", submission, ["task", "template_code"], as_dict=True)
    if not row or not row.task or row.template_code != K.QTY_ACCEPTANCE_CODE:
        return
    frappe.db.set_value("Task", row.task, "pmc_accepted_qty", accepted_of(row.task), update_modified=False)


def overview(project: str) -> dict:
    """Work items with their quantities, and the acceptance records of the project."""
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))
    works = frappe.get_list("Task", filters={"project": project, "is_group": 0, "pmc_planned_qty": [">", 0],
                                             "status": ["!=", "Cancelled"]},
                            fields=["name", "subject", "pm_wbs_code", "pmc_uom", "pmc_planned_qty", "pmc_done_qty",
                                    "pmc_accepted_qty", "pmc_unit_price", "progress", "status"],
                            order_by="pm_path asc", limit_page_length=0)
    for row in works:
        row["waiting_qty"] = max(0.0, flt(row.pmc_done_qty) - flt(row.pmc_accepted_qty))  # done, not yet accepted
    records = frappe.get_list("PM Form Submission", filters={"project": project, "template_code": ["in", K.ACCEPTANCE_CODES]},
                              fields=["name", "title", "template_code", "state", "task", "submitted_on", "reviewed_on",
                                      "data"], order_by="modified desc", limit_page_length=200)
    labels = {w.name: f"{w.pm_wbs_code or ''} {w.subject}".strip() for w in works}
    for record in records:
        data = {}
        try:
            data = json.loads(record.pop("data") or "{}") or {}
        except ValueError:
            pass
        record["qty"] = flt(data.get(K.QTY_FIELD)) if record.template_code == K.QTY_ACCEPTANCE_CODE else None
        record["task_label"] = labels.get(record.task) or (frappe.db.get_value("Task", record.task, "subject")
                                                           if record.task else None)
    templates = frappe.get_all("PM Form Template", filters={"code": ["in", K.ACCEPTANCE_CODES], "status": C.FORM_ACTIVE},
                               fields=["code", "title"], order_by="code asc")
    return {"works": works, "records": records, "templates": templates, "summary": boq.summary(project),
            "can": {"fill": has_project_capability(project, "task.update", "plan.edit", "task.approve")}}
