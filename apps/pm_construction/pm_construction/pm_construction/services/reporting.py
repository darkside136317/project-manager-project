"""What the construction layer adds to the M10 parts of the core (hooks pm_actual_costs, pm_reports, pm_dossier_parts;
the core never imports this module).

* Actual costs for the earned value: the materials, machines and labour of each work item (Task pmc_*_cost,
  services/costs.py).
* Reports: materials against their norm (one project), actual cost against the estimate (one project, finance.view).
* Dossier: the site diaries and their quantities, the approved BOQ (CSV), under thi-cong/.
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils import flt
from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import get_access, project_in
from project_manager.project_manager.services.reports.base import Report, col, link

from pm_construction.pm_construction import constants as K

COST_CATEGORIES = (("pmc_material_cost", "Vật tư"), ("pmc_machine_cost", "Máy thi công"), ("pmc_labour_cost", "Nhân công"))
GROUP = "Thi công"


def actual_costs(project: str) -> list[dict]:
    rows = frappe.get_all("Task", filters={"project": project, "is_group": 0, "status": ["!=", C.CANCELLED]},
                          fields=["name", *(field for field, _label in COST_CATEGORIES)], limit_page_length=0)
    out = []
    for row in rows:
        for field, category in COST_CATEGORIES:
            if flt(row.get(field)):
                out.append({"task": row.name, "category": category, "amount": flt(row.get(field))})
    return out


# --- reports ------------------------------------------------------------------------------------------------------------

def _readable(project: str) -> None:
    if not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)


def _norms(filters, page, size):
    from pm_construction.pm_construction.services import materials

    _readable(filters["project"])
    rows = []
    for row in materials.usage(filters["project"]):
        rows.append({**row, "task": row.task, "project": filters["project"],
                     "state": _("Vượt định mức") if row.over_norm else _("Cấp trước khối lượng") if row.ahead else ""})
    over = sum(1 for r in rows if r["state"] == _("Vượt định mức"))
    return {"rows": rows[(page - 1) * size: page * size], "total": len(rows),
            "info": [(_("Dòng vượt định mức"), str(over))]}


def _costs(filters, page, size):
    from pm_construction.pm_construction.services import costs

    _readable(filters["project"])
    summary = costs.summary(filters["project"])  # finance.view
    rows = [{**r, "task": r["name"], "project": filters["project"]} for r in summary["rows"]]
    total = summary["total"]
    return {"rows": rows[(page - 1) * size: page * size], "total": len(rows),
            "summary": {"label": _("Cộng"), **{k: total[k] for k in ("estimate", "earned", "material", "machine", "labour",
                                                                    "actual", "variance")}}}


def reports() -> list[Report]:
    return [
        Report(slug="vat-tu-dinh-muc", title="Vật tư so với định mức", group=GROUP, icon="package", order=10, paged=True,
               description="Theo công tác và vật tư của một dự án: kế hoạch, đã cấp, trả lại, đã dùng, định mức của khối "
                           "lượng đã làm, chênh lệch; dòng vượt định mức, cấp trước khối lượng.",
               run=_norms, filters=[link("project", "Dự án", "Project", reqd=1)],
               columns=[col("task_label", "Công tác", link="/cong-viec/{task}"), col("item_name", "Vật tư"),
                        col("uom", "Đơn vị"), col("planned", "Kế hoạch", "Float"), col("issued", "Đã cấp", "Float"),
                        col("returned", "Trả lại", "Float"), col("used", "Đã dùng", "Float"),
                        col("norm_done", "Định mức khối lượng đã làm", "Float"), col("gap", "Chênh lệch", "Float"),
                        col("state", "Tình trạng")]),
        Report(slug="chi-phi-du-toan", title="Chi phí thực tế so với dự toán", group=GROUP, icon="coins", order=20,
               paged=True,
               description="Theo hạng mục, công tác của một dự án: giá trị dự toán, giá trị đã thi công, chi phí vật tư, máy, "
                           "nhân công, thực tế và chênh lệch (cần quyền xem chi phí của dự án).",
               run=_costs, filters=[link("project", "Dự án", "Project", reqd=1)],
               columns=[col("label", "Hạng mục, công tác"), col("uom", "Đơn vị"), col("planned_qty", "KL thiết kế", "Float"),
                        col("done_qty", "KL đã làm", "Float"), col("estimate", "Dự toán", "Currency"),
                        col("earned", "Đã thi công", "Currency"), col("material", "Vật tư", "Currency"),
                        col("machine", "Máy", "Currency"), col("labour", "Nhân công", "Currency"),
                        col("actual", "Thực tế", "Currency"), col("variance", "Chênh lệch", "Currency")]),
    ]


# --- dossier ------------------------------------------------------------------------------------------------------------

def _csv(rows, columns) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label for _key, label in columns])
    for row in rows:
        writer.writerow(["" if row.get(key) is None else row.get(key) for key, _label in columns])
    return ("﻿" + out.getvalue()).encode("utf-8")


def dossier_parts(project: str) -> list[dict]:
    if not project_in(get_access().read, project):
        return []
    parts = []
    diaries = frappe.get_list("PMC Site Diary", filters={"project": project},
                              fields=["name", "diary_date", "status", "weather", "temperature", "workers", "work_summary",
                                      "issues", "safety", "author", "confirmed_by"], order_by="diary_date asc",
                              limit_page_length=0)
    if diaries:
        parts.append({"path": "thi-cong/nhat-ky-thi-cong.csv", "source": "PMC Site Diary", "content": _csv(diaries, [
            ("diary_date", "Ngày"), ("status", "Trạng thái"), ("weather", "Thời tiết"), ("temperature", "Nhiệt độ"),
            ("workers", "Nhân lực"), ("work_summary", "Công việc"), ("issues", "Vướng mắc"), ("safety", "An toàn"),
            ("author", "Người lập"), ("confirmed_by", "Người xác nhận")])})
        quantities = frappe.db.sql("""select d.diary_date, t.pm_wbs_code, t.subject, q.qty, q.uom, d.status
                                      from `tabPMC Diary Quantity` q join `tabPMC Site Diary` d on d.name = q.diary
                                      join `tabTask` t on t.name = q.task where q.project = %s
                                      order by d.diary_date, t.pm_path""", project, as_dict=True)
        parts.append({"path": "thi-cong/khoi-luong-theo-ngay.csv", "source": "PMC Diary Quantity", "content": _csv(
            quantities, [("diary_date", "Ngày"), ("pm_wbs_code", "Mã WBS"), ("subject", "Công tác"), ("qty", "Khối lượng"),
                         ("uom", "Đơn vị"), ("status", "Trạng thái nhật ký")])})
    boq = frappe.db.get_value("PMC BOQ", {"project": project, "status": K.BOQ_APPROVED}, ["name", "version_no"], as_dict=True)
    if boq:
        items = frappe.get_all("PMC BOQ Item", filters={"boq": boq.name},
                               fields=["line_no", "code", "norm_code", "description", "uom", "qty", "unit_price", "amount"],
                               order_by="line_no asc", limit_page_length=0)
        parts.append({"path": f"thi-cong/bang-khoi-luong-v{boq.version_no}.csv", "source": f"PMC BOQ {boq.name}",
                      "content": _csv(items, [("line_no", "STT"), ("code", "Mã"), ("norm_code", "Mã hiệu định mức"),
                                              ("description", "Nội dung"), ("uom", "Đơn vị"), ("qty", "Khối lượng"),
                                              ("unit_price", "Đơn giá"), ("amount", "Thành tiền")])})
    return parts
