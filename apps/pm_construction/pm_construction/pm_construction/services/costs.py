"""Chi phí thực tế of the work items, against their estimate (the BOQ value).

* Materials: the value of what was issued to the work item and written off on it, less what came back (submitted
  stock entries; the value is ERPNext's valuation at the moment of the entry).
* Machines: shifts × the machine's shift rate (PMC Machine Shift).
* Labour: man-days × the worker's daily rate on confirmed attendance sheets (PMC Crew Attendance).
Kept on the Task (pmc_*_cost, permission level 1), refreshed when one of these changes. The summary adds them up the
tree by path and sets them against the estimate value and the value of the work done (done quantity × unit price).
Only with finance.view in the project.
"""

import frappe
from frappe import _
from frappe.utils import flt
from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import get_access, has_project_capability, project_in

from pm_construction.pm_construction import constants as K

FIELDS = ("pmc_material_cost", "pmc_machine_cost", "pmc_labour_cost", "pmc_actual_cost")


def of_tasks(project: str, tasks=None) -> dict:
    """{task: {"material", "machine", "labour"}} from the ledgers."""
    params = {"project": project}
    narrow = ""
    if tasks:
        params["tasks"] = tuple(tasks)
        narrow = " and {column} in %(tasks)s"
    out = {}

    def add(rows, key):
        for task, value in rows:
            out.setdefault(task, {"material": 0.0, "machine": 0.0, "labour": 0.0})[key] += flt(value)

    add(frappe.db.sql(f"""select d.pmc_task, sum(case when e.pmc_kind = %(back)s then -d.amount else d.amount end)
                          from `tabStock Entry Detail` d join `tabStock Entry` e on e.name = d.parent
                          where e.docstatus = 1 and e.project = %(project)s and e.pmc_kind in %(kinds)s
                            and ifnull(d.pmc_task, '') != ''{narrow.format(column='d.pmc_task')}
                          group by d.pmc_task""", {**params, "back": K.RETURN, "kinds": (K.ISSUE, K.WASTE, K.RETURN)}),
        "material")
    add(frappe.db.sql(f"""select task, sum(amount) from `tabPMC Machine Shift`
                          where project = %(project)s and ifnull(task, '') != ''{narrow.format(column='task')}
                          group by task""", params), "machine")
    add(frappe.db.sql(f"""select l.task, sum(l.amount) from `tabPMC Attendance Line` l
                          join `tabPMC Crew Attendance` a on a.name = l.parent
                          where a.project = %(project)s and a.status = %(confirmed)s and ifnull(l.task, '') != ''
                            {narrow.format(column='l.task')}
                          group by l.task""", {**params, "confirmed": K.SHEET_CONFIRMED}), "labour")
    return out


def refresh(project: str, tasks=None) -> int:
    """Write the costs of these work items (all of the project's when None). Returns the rows changed."""
    if tasks is not None:
        tasks = [t for t in tasks if t]
        if not tasks:
            return 0
    found = of_tasks(project, tasks)
    filters = {"project": project, "is_group": 0}
    if tasks:
        filters["name"] = ["in", tasks]
    changed = 0
    for row in frappe.get_all("Task", filters=filters, fields=["name", *FIELDS], limit_page_length=0):
        cost = found.get(row.name, {"material": 0.0, "machine": 0.0, "labour": 0.0})
        values = {"pmc_material_cost": flt(cost["material"], 0), "pmc_machine_cost": flt(cost["machine"], 0),
                  "pmc_labour_cost": flt(cost["labour"], 0)}
        values["pmc_actual_cost"] = sum(values.values())
        if any(flt(row.get(k)) != v for k, v in values.items()):
            frappe.db.set_value("Task", row.name, values, update_modified=False)
            changed += 1
    return changed


def on_stock_entry(doc, method=None):
    """Stock Entry on_submit / on_cancel: the work items it touches."""
    if doc.get("project") and doc.get("pmc_kind"):
        refresh(doc.project, sorted({row.pmc_task for row in doc.items if row.get("pmc_task")}))


def summary(project: str) -> dict:
    """Estimate, value of the work done and actual cost per work item and per section (by path), and the project's."""
    if not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)
    if not has_project_capability(project, "finance.view"):
        frappe.throw(_("Vai trò của bạn trong dự án không xem được chi phí"), frappe.PermissionError)
    rows = frappe.get_all("Task", filters={"project": project, "status": ["!=", C.CANCELLED]},
                          fields=["name", "subject", "pm_wbs_code", "pm_path", "is_group", "pm_level", "pmc_uom",
                                  "pmc_planned_qty", "pmc_done_qty", "pmc_unit_price", "pmc_estimate_value", *FIELDS],
                          order_by="pm_path asc", limit_page_length=0)
    by_path = {r.pm_path: r for r in rows}
    keys = ("estimate", "earned", "material", "machine", "labour", "actual")
    for row in rows:
        row.update({k: 0.0 for k in keys})
    for row in rows:
        if row.is_group:
            continue
        values = {"estimate": flt(row.pmc_estimate_value), "earned": flt(row.pmc_done_qty) * flt(row.pmc_unit_price),
                  "material": flt(row.pmc_material_cost), "machine": flt(row.pmc_machine_cost),
                  "labour": flt(row.pmc_labour_cost), "actual": flt(row.pmc_actual_cost)}
        parts = (row.pm_path or "").split(".")
        for depth in range(1, len(parts) + 1):  # the row itself and every section above it
            target = by_path.get(".".join(parts[:depth]))
            if target:
                for key, value in values.items():
                    target[key] += value
    total = {k: sum(r[k] for r in rows if not r.is_group) for k in keys}
    out = []
    for row in rows:
        out.append({"name": row.name, "label": f"{row.pm_wbs_code or ''} {row.subject}".strip(), "level": row.pm_level,
                    "is_group": row.is_group, "uom": row.pmc_uom, "planned_qty": row.pmc_planned_qty,
                    "done_qty": row.pmc_done_qty, **{k: flt(row[k], 0) for k in keys},
                    "variance": flt(row["earned"] - row["actual"], 0)})
    return {"rows": out, "total": {**{k: flt(v, 0) for k, v in total.items()},
                                   "variance": flt(total["earned"] - total["actual"], 0)}}
