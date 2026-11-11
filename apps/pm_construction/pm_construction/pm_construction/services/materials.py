"""Vật tư of a construction project, on ERPNext's stock (Warehouse, Material Request, Stock Entry).

* Each project has a site store (kho công trường): a Warehouse with pm_project, under "Kho công trường - ABBR".
* The material plan (PMC Material Plan) of a work item is its design quantity times the norm of its code (PMC Material
  Norm, with waste); it is rebuilt when the BOQ is approved or the norms change.
* An engineer asks for materials for work items (a Material Request "Material Issue" of the site store, each row
  tied to its work item by pmc_task); the store keeper receives deliveries (Nhập kho), issues to work items (Cấp phát,
  closing the request rows it answers), takes back what was not used (Hoàn trả), writes off losses (Hao hụt), moves
  stock to another project's store (Điều chuyển). Each is a submitted Stock Entry: stock ledger, valuation and
  accounts are ERPNext's.
* Used by a work item = issued − returned. The norm of the work done = done quantity × norm. Over the norm (alert
  "Vượt định mức vật tư"): used above the norm of the whole design quantity, or, once the work item is finished, above
  the norm of the work done (by more than NORM_TOLERANCE). Before that, more than the work done needs is only "issued
  ahead" (materials waiting at the work face): shown, not alerted.
Who: material.request to ask, stock.manage for the store; the costs only with finance.view.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate
from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import (
    can_see_task,
    get_access,
    has_project_capability,
    project_in,
)
from project_manager.project_manager.services import activity
from project_manager.project_manager.services.notify import notify_user
from project_manager.project_manager.services.queries import reserve_ids

from pm_construction.pm_construction import constants as K

SPA_TAB = "/pm/du-an/{}/vat-tu"
MAX_ROWS = 100


# --- who, where -------------------------------------------------------------------------------------------------------------

def _readable(project: str) -> None:
    if not project or not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)


def _may(project: str, *codes) -> None:
    if not has_project_capability(project, *codes):
        frappe.throw(_("Vai trò của bạn trong dự án không làm được việc này"), frappe.PermissionError)


def company_of(project: str) -> str:
    return frappe.db.get_value("Project", project, "company") or frappe.defaults.get_global_default("company")


def site_store(project: str) -> str | None:
    return frappe.db.get_value("Warehouse", {"pm_project": project, "is_group": 0, "disabled": 0}, "name")


def root_store(company: str) -> str | None:
    """The top of the company's warehouse tree (its name follows the site's language: "All Warehouses", "Tất cả Kho"...)."""
    return frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["is", "not set"]},
                               "name")


def account_of(company: str, account_type: str) -> str | None:
    return frappe.db.get_value("Account", {"company": company, "account_type": account_type, "is_group": 0}, "name")


def _stores_group(company: str) -> str:
    abbr = frappe.get_cached_value("Company", company, "abbr")
    name = f"{K.SITE_STORES} - {abbr}"
    if not frappe.db.exists("Warehouse", name):
        frappe.get_doc({"doctype": "Warehouse", "warehouse_name": K.SITE_STORES, "company": company, "is_group": 1,
                        "parent_warehouse": root_store(company)}).insert(ignore_permissions=True)
    return name


def create_store(project: str) -> str:
    """The site store of a project (made once)."""
    _readable(project)
    _may(project, "stock.manage", "plan.edit")
    existing = site_store(project)
    if existing:
        return existing
    company = company_of(project)
    code = frappe.db.get_value("Project", project, "pm_code") or project
    doc = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": f"Kho {code}", "company": company,
                          "parent_warehouse": _stores_group(company), "pm_project": project})
    doc.insert(ignore_permissions=True)
    activity.record("Project", project, "Hệ thống", _("Lập kho công trường {0}").format(doc.name))
    return doc.name


def _store_or_fail(project: str) -> str:
    store = site_store(project)
    if not store:
        frappe.throw(_("Dự án chưa có kho công trường"), title=_("Chưa có kho"))
    return store


# --- the plan from the norms ------------------------------------------------------------------------------------------------

def norms_of(codes) -> dict:
    """{norm code: [row]} of the active norms among `codes`."""
    codes = sorted({(c or "").strip().upper() for c in codes if c})
    if not codes:
        return {}
    active = set(frappe.get_all("PMC Material Norm", filters={"name": ["in", codes], "is_active": 1}, pluck="name"))
    out = {}
    for row in frappe.get_all("PMC Norm Material", filters={"parent": ["in", list(active)], "parenttype": "PMC Material Norm"},
                              fields=["parent", "item", "item_name", "uom", "qty", "waste_pct"], order_by="idx asc",
                              limit_page_length=0):
        out.setdefault(row.parent, []).append(row)
    return out


def plan_from_norms(project: str) -> int:
    """Rebuild the material plan of a project: every work item with a norm code gets the materials of its norm."""
    works = frappe.get_all("Task", filters={"project": project, "is_group": 0, "status": ["!=", C.CANCELLED],
                                            "pmc_norm_code": ["is", "set"], "pmc_planned_qty": [">", 0]},
                           fields=["name", "pmc_norm_code", "pmc_planned_qty"], limit_page_length=0)
    norms = norms_of(w.pmc_norm_code for w in works)
    rows = []
    for work in works:
        for material in norms.get((work.pmc_norm_code or "").strip().upper(), []):
            unit = flt(material.qty) * (1 + flt(material.waste_pct) / 100)
            rows.append((work.name, material, unit, flt(work.pmc_planned_qty) * unit, work.pmc_norm_code))
    frappe.db.delete("PMC Material Plan", {"project": project})
    if rows:
        now, user = frappe.utils.now_datetime(), frappe.session.user
        values = [(number, now, now, user, user, 0, 0, project, task, m.item, m.item_name, m.uom, code.upper(),
                   round(unit, 6), round(planned, 3))
                  for number, (task, m, unit, planned, code) in zip(reserve_ids("PMC Material Plan", len(rows)), rows,
                                                                     strict=True)]
        frappe.db.bulk_insert("PMC Material Plan", ("name", "creation", "modified", "modified_by", "owner", "docstatus",
                                                    "idx", "project", "task", "item", "item_name", "uom", "norm_code",
                                                    "unit_qty", "planned_qty"), values, chunk_size=500)
    return len(rows)


def recompute_plan(project: str) -> int:
    _readable(project)
    _may(project, "plan.edit", "stock.manage")
    return plan_from_norms(project)


# --- what was asked, issued, returned ----------------------------------------------------------------------------------------

def movements(project: str, tasks=None) -> dict:
    """{(task, item): {kind: {"qty", "amount"}}} of the submitted stock entries of the project's work items."""
    condition, params = "", {"project": project}
    if tasks:
        condition, params["tasks"] = " and d.pmc_task in %(tasks)s", tuple(tasks)
    out = {}
    for row in frappe.db.sql(f"""select d.pmc_task as task, d.item_code as item, e.pmc_kind as kind,
                                        sum(d.transfer_qty) as qty, sum(d.amount) as amount
                                 from `tabStock Entry Detail` d join `tabStock Entry` e on e.name = d.parent
                                 where e.docstatus = 1 and e.project = %(project)s and ifnull(d.pmc_task, '') != ''
                                   {condition}
                                 group by d.pmc_task, d.item_code, e.pmc_kind""", params, as_dict=True):
        out.setdefault((row.task, row.item), {})[row.kind] = {"qty": flt(row.qty), "amount": flt(row.amount)}
    return out


def requested(project: str) -> dict:
    """{(task, item): quantity asked for} of the submitted, not stopped requests."""
    rows = frappe.db.sql("""select i.pmc_task as task, i.item_code as item, sum(i.stock_qty) as qty
                            from `tabMaterial Request Item` i join `tabMaterial Request` r on r.name = i.parent
                            where r.docstatus = 1 and r.pm_project = %s and r.status not in ('Stopped', 'Cancelled')
                              and ifnull(i.pmc_task, '') != ''
                            group by i.pmc_task, i.item_code""", project, as_dict=True)
    return {(r.task, r.item): flt(r.qty) for r in rows}


def usage(project: str, tasks=None) -> list[dict]:
    """Per work item and material: plan, asked, issued, returned, wasted, used, norm of the work done, gap."""
    filters = {"project": project}
    if tasks:
        filters["task"] = ["in", list(tasks)]
    plans = frappe.get_all("PMC Material Plan", filters=filters,
                           fields=["task", "item", "item_name", "uom", "unit_qty", "planned_qty", "norm_code"],
                           limit_page_length=0)
    moved = movements(project, tasks)
    asked = requested(project)
    keys = {(p.task, p.item) for p in plans} | set(moved) | ({k for k in asked if not tasks or k[0] in tasks})
    plan_of = {(p.task, p.item): p for p in plans}
    names = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", list({k[1] for k in keys})]},
                                               fields=["name", "item_name", "stock_uom"])} if keys else {}
    works = {t.name: t for t in frappe.get_all("Task", filters={"name": ["in", list({k[0] for k in keys})]},
                                               fields=["name", "subject", "pm_wbs_code", "pm_path", "pmc_done_qty",
                                                       "pmc_planned_qty", "pmc_uom", "status"])} if keys else {}
    rows = []
    for task, item in keys:
        plan = plan_of.get((task, item)) or frappe._dict()
        kinds = moved.get((task, item), {})
        issued = kinds.get(K.ISSUE, {}).get("qty", 0)
        returned = kinds.get(K.RETURN, {}).get("qty", 0)
        wasted = kinds.get(K.WASTE, {}).get("qty", 0)
        used = issued - returned
        work = works.get(task) or frappe._dict()
        norm_done = flt(plan.unit_qty) * flt(work.pmc_done_qty) if plan else None
        finished = work.status == C.COMPLETED or (flt(work.pmc_planned_qty) > 0
                                                  and flt(work.pmc_done_qty) >= flt(work.pmc_planned_qty) - 1e-9)
        beyond_done = bool(plan) and used > flt(norm_done) * (1 + K.NORM_TOLERANCE) + 1e-9
        beyond_plan = bool(plan) and used > flt(plan.planned_qty) * (1 + K.NORM_TOLERANCE) + 1e-9
        over = beyond_plan or (finished and beyond_done)
        info = names.get(item) or frappe._dict()
        rows.append(frappe._dict(
            task=task, task_label=f"{work.pm_wbs_code or ''} {work.subject or task}".strip(), path=work.pm_path or "",
            item=item, item_name=plan.item_name or info.item_name or item, uom=plan.uom or info.stock_uom,
            norm_code=plan.norm_code, unit_qty=flt(plan.unit_qty), planned=flt(plan.planned_qty),
            requested=flt(asked.get((task, item))), issued=flt(issued, 6), returned=flt(returned, 6),
            wasted=flt(wasted, 6), used=flt(used, 6), norm_done=None if norm_done is None else flt(norm_done, 6),
            gap=None if norm_done is None else flt(used - norm_done, 6), over_norm=over,
            ahead=bool(beyond_done and not over), finished=finished,
            done_qty=flt(work.pmc_done_qty), work_uom=work.pmc_uom,
            value=flt(kinds.get(K.ISSUE, {}).get("amount", 0) - kinds.get(K.RETURN, {}).get("amount", 0)
                      + kinds.get(K.WASTE, {}).get("amount", 0), 0)))
    rows.sort(key=lambda r: (r.path, r.item_name))
    return rows


def stock_of(store: str) -> list[dict]:
    if not store:
        return []
    return frappe.db.sql("""select b.item_code as item, i.item_name, i.stock_uom as uom, b.actual_qty as qty,
                                   b.valuation_rate as rate, b.stock_value as value
                            from `tabBin` b join `tabItem` i on i.name = b.item_code
                            where b.warehouse = %s and (b.actual_qty != 0 or b.stock_value != 0)
                            order by i.item_name""", store, as_dict=True)


def overview(project: str) -> dict:
    _readable(project)
    store = site_store(project)
    finance = has_project_capability(project, "finance.view")
    rows = usage(project)
    stock = stock_of(store)
    if not finance:
        for row in rows:
            row.pop("value", None)
        for row in stock:
            row.pop("rate", None)
            row.pop("value", None)
    visible = {r.task for r in rows if can_see_task(r.task, project)}
    rows = [r for r in rows if r.task in visible]
    return {"store": store, "rows": rows, "stock": stock, "requests": requests(project), "entries": entries(project),
            "items": catalogue(project), "over_norm": sum(1 for r in rows if r.over_norm),
            "can": {"request": has_project_capability(project, "material.request"),
                    "manage": has_project_capability(project, "stock.manage"),
                    "plan": has_project_capability(project, "plan.edit"), "finance": finance}}


def catalogue(project: str, limit: int = 500) -> list[dict]:
    """Materials to pick from: those of the plan and of the store first, then the construction materials."""
    planned = set(frappe.get_all("PMC Material Plan", filters={"project": project}, pluck="item", distinct=True))
    store = site_store(project)
    stocked = set(frappe.get_all("Bin", filters={"warehouse": store}, pluck="item_code")) if store else set()
    rows = frappe.get_all("Item", filters={"is_stock_item": 1, "disabled": 0}, or_filters={
        "item_group": K.ITEM_GROUP, "name": ["in", list(planned | stocked) or [""]]},
        fields=["name", "item_name", "stock_uom"], order_by="item_name asc", limit_page_length=limit)
    for row in rows:
        row["planned"] = row.name in planned
    return rows


def requests(project: str, limit: int = 50) -> list[dict]:
    heads = frappe.get_all("Material Request", filters={"pm_project": project, "docstatus": 1},
                           fields=["name", "status", "transaction_date", "schedule_date", "owner", "per_ordered"],
                           order_by="creation desc", limit_page_length=limit)
    if not heads:
        return []
    lines = frappe.get_all("Material Request Item", filters={"parent": ["in", [h.name for h in heads]]},
                           fields=["name", "parent", "item_code", "item_name", "stock_qty", "ordered_qty", "uom",
                                   "pmc_task"], order_by="idx asc", limit_page_length=0)
    tasks = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip() for t in frappe.get_all(
        "Task", filters={"name": ["in", list({ln.pmc_task for ln in lines if ln.pmc_task})]},
        fields=["name", "subject", "pm_wbs_code"])} if lines else {}
    people = dict(frappe.get_all("User", filters={"name": ["in", list({h.owner for h in heads})]},
                                 fields=["name", "full_name"], as_list=True))
    by_head = {}
    for line in lines:
        line["task_label"] = tasks.get(line.pmc_task)
        line["left"] = max(0.0, flt(line.stock_qty) - flt(line.ordered_qty))
        by_head.setdefault(line.parent, []).append(line)
    for head in heads:
        head["requester"] = people.get(head.owner) or head.owner
        head["lines"] = by_head.get(head.name, [])
        head["open"] = head.status not in ("Issued", "Stopped", "Cancelled") and any(ln.left > 0 for ln in head["lines"])
    return heads


def entries(project: str, limit: int = 50) -> list[dict]:
    heads = frappe.get_all("Stock Entry", filters={"project": project, "docstatus": 1, "pmc_kind": ["is", "set"]},
                           fields=["name", "pmc_kind", "posting_date", "owner", "total_outgoing_value",
                                   "total_incoming_value", "remarks"], order_by="posting_date desc, creation desc",
                           limit_page_length=limit)
    finance = has_project_capability(project, "finance.view")
    for head in heads:
        head["lines"] = frappe.get_all("Stock Entry Detail", filters={"parent": head.name},
                                       fields=["item_code", "item_name", "transfer_qty", "stock_uom", "pmc_task"],
                                       order_by="idx asc")
        if not finance:
            head.pop("total_outgoing_value")
            head.pop("total_incoming_value")
    return heads


# --- asking -------------------------------------------------------------------------------------------------------------------

def _rows(project: str, rows, need_task: bool) -> list:
    if isinstance(rows, str):
        rows = frappe.parse_json(rows or "[]")
    out = []
    for row in rows or []:
        row = frappe._dict(row)
        qty = flt(row.qty)
        if not row.item or qty <= 0:
            continue
        if not frappe.db.get_value("Item", row.item, "is_stock_item"):
            frappe.throw(_("{0} không phải vật tư quản lý tồn kho").format(row.item))
        if row.task:
            info = frappe.db.get_value("Task", row.task, ["project", "is_group"], as_dict=True)
            if not info or info.project != project or cint(info.is_group):
                frappe.throw(_("Công tác {0} không thuộc dự án này").format(row.task))
            if not can_see_task(row.task, project):
                frappe.throw(_("Bạn không xem được công tác {0}").format(row.task), frappe.PermissionError)
        elif need_task:
            frappe.throw(_("Hãy chọn công tác dùng {0}").format(row.item))
        row.qty = qty
        out.append(row)
    if not out:
        frappe.throw(_("Chưa có dòng vật tư nào"))
    if len(out) > MAX_ROWS:
        frappe.throw(_("Mỗi phiếu tối đa {0} dòng").format(MAX_ROWS))
    return out


def request(project: str, rows, note: str = "", needed_by=None, client_uuid: str | None = None) -> dict:
    """Đề xuất vật tư: a submitted Material Request of the site store, a row per work item and material."""
    _readable(project)
    if client_uuid:
        existing = frappe.db.get_value("Material Request", {"pm_client_uuid": client_uuid}, "name")
        if existing:
            return {"name": existing, "again": True}
    _may(project, "material.request")
    rows = _rows(project, rows, need_task=True)
    store = _store_or_fail(project)
    day = getdate(needed_by or nowdate())
    doc = frappe.get_doc({
        "doctype": "Material Request", "material_request_type": "Material Issue", "company": company_of(project),
        "pm_project": project, "pm_client_uuid": client_uuid or None, "transaction_date": nowdate(), "schedule_date": day,
        "set_warehouse": store,
        "items": [{"item_code": r.item, "qty": r.qty, "warehouse": store, "schedule_date": day, "project": project,
                   "pmc_task": r.task, "description": r.note or None} for r in rows],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    who = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    text = _("{0} đề xuất {1} dòng vật tư ({2})").format(who, len(rows), doc.name) + \
        (f": {note.strip()}" if (note or "").strip() else "")
    activity.record("Project", project, "Hệ thống", text, data={"material_request": doc.name})
    for keeper in _keepers(project) - {frappe.session.user}:
        notify_user(keeper, _("Đề xuất vật tư mới chờ cấp phát: {0}").format(doc.name), SPA_TAB.format(project),
                    "Material Request", doc.name)
    return {"name": doc.name, "again": False}


def _keepers(project: str) -> set:
    """Members whose project role manages the store."""
    roles = set(frappe.get_all("PM Role Capability", filters={"parenttype": "PM Project Role", "capability": "stock.manage"},
                               pluck="parent"))
    if not roles:
        return set()
    return set(frappe.get_all("PM Project Member", filters={"project": project, "is_active": 1,
                                                            "project_role": ["in", list(roles)]}, pluck="user"))


def stop_request(name: str, note: str = "") -> dict:
    project = frappe.db.get_value("Material Request", name, "pm_project")
    _readable(project)
    _may(project, "stock.manage")
    doc = frappe.get_doc("Material Request", name)
    if doc.docstatus != 1 or doc.status in ("Stopped", "Issued"):
        frappe.throw(_("Đề xuất này không dừng được"))
    doc.update_status("Stopped")
    activity.record("Project", project, "Hệ thống", _("Dừng đề xuất vật tư {0}{1}").format(
        name, f": {note.strip()}" if (note or "").strip() else ""))
    owner = doc.owner
    if owner != frappe.session.user:
        notify_user(owner, _("Đề xuất vật tư {0} đã bị dừng").format(name), SPA_TAB.format(project), "Material Request", name)
    return {"name": name, "status": "Stopped"}


# --- the store keeper's entries -----------------------------------------------------------------------------------------------

def _entry(project: str, kind: str, rows: list, posting_date=None, client_uuid: str | None = None, note: str = "",
           to_store: str | None = None):
    company = company_of(project)
    store = _store_or_fail(project)
    purpose = K.PURPOSES[kind]
    items = []
    for row in rows:
        line = {"item_code": row.item, "qty": row.qty, "project": project, "pmc_task": row.task or None,
                "conversion_factor": 1, "uom": frappe.db.get_value("Item", row.item, "stock_uom")}
        if purpose == "Material Receipt":
            line.update(t_warehouse=store, basic_rate=flt(row.rate), allow_zero_valuation_rate=0)
        elif purpose == "Material Issue":
            line.update(s_warehouse=store)
        else:
            line.update(s_warehouse=store, t_warehouse=to_store)
        if row.get("material_request_item"):
            line.update(material_request=row.material_request, material_request_item=row.material_request_item)
        items.append(line)
    doc = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": purpose, "purpose": purpose, "company": company,
                          "project": project, "pmc_kind": kind, "pmc_client_uuid": client_uuid or None,
                          "set_posting_time": 1 if posting_date else 0, "posting_date": getdate(posting_date or nowdate()),
                          "remarks": (note or "").strip() or None, "items": items})
    try:
        doc.insert(ignore_permissions=True)
        doc.submit()
    except frappe.ValidationError as error:
        message = str(error)
        if "Insufficient Stock" in message or "NegativeStockError" in type(error).__name__ or "negative" in message.lower():
            frappe.throw(_("Không đủ tồn kho trong {0}: {1}").format(store, frappe.utils.strip_html(message)[:300]),
                         title=_("Không đủ tồn kho"))
        raise
    return doc


def _again(client_uuid):
    if not client_uuid:
        return None
    name = frappe.db.get_value("Stock Entry", {"pmc_client_uuid": client_uuid}, "name")
    return {"name": name, "again": True} if name else None


def _finish(project: str, doc, kind: str) -> dict:
    from pm_construction.pm_construction.services import costs

    tasks = sorted({row.pmc_task for row in doc.items if row.pmc_task})
    if tasks:
        costs.refresh(project, tasks)
    who = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    activity.record("Project", project, "Hệ thống", _("{0}: {1} ({2} dòng, {3})").format(kind, doc.name, len(doc.items), who),
                    data={"stock_entry": doc.name, "kind": kind})
    return {"name": doc.name, "again": False}


def receive(project: str, rows, posting_date=None, note: str = "", client_uuid: str | None = None) -> dict:
    """Nhập kho: a delivery to the site store, at its price."""
    _readable(project)
    again = _again(client_uuid)
    if again:
        return again
    _may(project, "stock.manage")
    rows = _rows(project, rows, need_task=False)
    for row in rows:
        if flt(row.rate) <= 0:
            frappe.throw(_("Nhập {0} cần đơn giá").format(row.item))
        row.task = None
    return _finish(project, _entry(project, K.RECEIPT, rows, posting_date, client_uuid, note), K.RECEIPT)


def issue(project: str, rows, posting_date=None, note: str = "", client_uuid: str | None = None) -> dict:
    """Cấp phát to work items; rows answering a request (material_request_item) close it."""
    _readable(project)
    again = _again(client_uuid)
    if again:
        return again
    _may(project, "stock.manage")
    rows = _rows(project, rows, need_task=True)
    for row in rows:
        if row.get("material_request_item"):
            link = frappe.db.get_value("Material Request Item", row.material_request_item,
                                       ["parent", "item_code", "pmc_task"], as_dict=True)
            if not link or link.item_code != row.item or frappe.db.get_value("Material Request", link.parent,
                                                                              "pm_project") != project:
                frappe.throw(_("Dòng đề xuất không khớp với vật tư {0}").format(row.item))
            row.material_request = link.parent
            row.task = row.task or link.pmc_task
    doc = _entry(project, K.ISSUE, rows, posting_date, client_uuid, note)
    for requester in {frappe.db.get_value("Material Request", r.material_request, "owner")
                      for r in rows if r.get("material_request")} - {None, frappe.session.user}:
        notify_user(requester, _("Vật tư đã được cấp phát ({0})").format(doc.name), SPA_TAB.format(project),
                    "Stock Entry", doc.name)
    return _finish(project, doc, K.ISSUE)


def give_back(project: str, rows, posting_date=None, note: str = "", client_uuid: str | None = None) -> dict:
    """Hoàn trả: what a work item did not use comes back to the store, at the price it went out."""
    _readable(project)
    again = _again(client_uuid)
    if again:
        return again
    _may(project, "stock.manage")
    rows = _rows(project, rows, need_task=True)
    moved = movements(project, [r.task for r in rows])
    for row in rows:
        out = moved.get((row.task, row.item), {})
        issued = out.get(K.ISSUE, {"qty": 0, "amount": 0})
        back = out.get(K.RETURN, {"qty": 0})["qty"]
        if row.qty > issued["qty"] - back + 1e-9:
            frappe.throw(_("{0}: trả lại nhiều hơn đã cấp cho công tác ({1})").format(row.item,
                                                                                   flt(issued["qty"] - back, 3)))
        row.rate = issued["amount"] / issued["qty"] if issued["qty"] else 0
    return _finish(project, _entry(project, K.RETURN, rows, posting_date, client_uuid, note), K.RETURN)


def write_off(project: str, rows, posting_date=None, note: str = "", client_uuid: str | None = None) -> dict:
    """Hao hụt: lost or spoiled in the store (or on a work item)."""
    _readable(project)
    again = _again(client_uuid)
    if again:
        return again
    _may(project, "stock.manage")
    if not (note or "").strip():
        frappe.throw(_("Ghi lý do hao hụt"))
    rows = _rows(project, rows, need_task=False)
    return _finish(project, _entry(project, K.WASTE, rows, posting_date, client_uuid, note), K.WASTE)


def transfer(project: str, to_project: str, rows, posting_date=None, note: str = "", client_uuid: str | None = None) -> dict:
    """Điều chuyển to another project's site store: the right on both stores."""
    _readable(project)
    again = _again(client_uuid)
    if again:
        return again
    _may(project, "stock.manage")
    if not to_project or to_project == project:
        frappe.throw(_("Chọn dự án nhận"))
    if not has_project_capability(to_project, "stock.manage"):
        frappe.throw(_("Bạn không quản lý kho của dự án nhận"), frappe.PermissionError)
    target = _store_or_fail(to_project)
    rows = _rows(project, rows, need_task=False)
    for row in rows:
        row.task = None
    doc = _entry(project, K.TRANSFER, rows, posting_date, client_uuid, note, to_store=target)
    activity.record("Project", to_project, "Hệ thống", _("Nhận điều chuyển vật tư từ dự án {0} ({1})").format(project, doc.name))
    return _finish(project, doc, K.TRANSFER)


# --- over the norm (alert type "Vượt định mức vật tư", core hook pm_alert_types) ----------------------------------------------

def over_norm(rule, today):
    from project_manager.project_manager.services import alerts

    projects = frappe.db.sql("""select distinct p.name from `tabPMC Material Plan` m join `tabProject` p on p.name = m.project
                                where p.pm_is_template = 0 and p.pm_state = 'Đang thực hiện'""", pluck=True)
    hits = []
    for project in projects:
        for row in usage(project):
            if row.over_norm:
                hits.append(alerts._hit("Task", row.task, project, row.task, row.item, _(
                    "Vượt định mức vật tư: {0} dùng {1} {2} {3}, định mức cho khối lượng đã làm {4}").format(
                    row.task_label, flt(row.used, 3), row.uom or "", row.item_name, flt(row.norm_done, 3))))
    return hits
