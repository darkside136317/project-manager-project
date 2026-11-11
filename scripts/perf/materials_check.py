"""Speed of materials on a large site (M8): a 3 000-work BOQ whose norms give 9 000 plan rows, a site store, issues to a
third of the work items, then the overview (norm against what was used), the cost refresh and summary, and the
over-norm alert. Runs on a temporary project (code PERF-VT), removed at the end and by `reset`:

    docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/materials_check.py
    ... - reset < ../scripts/perf/materials_check.py
"""

import io
import os
import sys
import time

import frappe

SITE = os.environ.get("PERF_SITE", "pm.localhost")
CODE = "PERF-VT"
SECTIONS, WORKS = 100, 30  # 3 000 work items
ITEMS = (("PERF-XM", "Kg", 350), ("PERF-CAT", "m3", 0.48), ("PERF-DA", "m3", 0.9))


def sheet() -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    page = book.active
    page.append(["STT", "Mã hiệu", "Nội dung công việc", "Đơn vị", "Khối lượng", "Đơn giá", "Thành tiền"])
    for s in range(SECTIONS):
        page.append([f"{s + 1}", "", f"HẠNG MỤC {s + 1}", "", None, None, None])
        for w in range(WORKS):
            page.append([f"{s + 1}.{w + 1}", f"PERF.{w:03d}", f"Bê tông {w + 1} của hạng mục {s + 1}", "m3", 10 + w,
                         2_000_000, (10 + w) * 2_000_000])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def timed(label, action):
    started = time.perf_counter()
    result = action()
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms")
    return result


def seed():
    from pm_construction.pm_construction import constants as K
    from pm_construction.pm_construction.services import boq, costs, materials
    from pm_construction.pm_construction.setup import install

    reset(quiet=True)
    frappe.set_user("Administrator")
    install.ensure_stock_masters()
    for code, uom, _qty in ITEMS:
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": K.ITEM_GROUP,
                        "stock_uom": uom, "is_stock_item": 1}).insert(ignore_permissions=True)
    for w in range(WORKS):
        frappe.get_doc({"doctype": "PMC Material Norm", "norm_code": f"PERF.{w:03d}", "description": "Đo", "uom": "m3",
                        "materials": [{"item": c, "qty": q, "waste_pct": 1} for c, _u, q in ITEMS]}).insert(
            ignore_permissions=True)
    project = frappe.get_doc({"doctype": "Project", "project_name": "Đo vật tư", "pm_code": CODE, "pm_state": "Đang thực hiện",
                              "company": frappe.defaults.get_global_default("company")}).insert(ignore_permissions=True).name
    version = boq.import_version(project, sheet(), "v1.xlsx")
    frappe.db.commit()
    timed("duyệt BOQ 3.000 công tác, kế hoạch vật tư gồm trong đó", lambda: boq.approve(version.name))
    frappe.db.commit()
    rows = timed("tính lại kế hoạch vật tư", lambda: materials.plan_from_norms(project))
    print(f"  {rows} dòng kế hoạch")
    store = materials.create_store(project)
    timed("nhập kho 3 vật tư", lambda: materials.receive(project, [{"item": c, "qty": 10_000_000, "rate": 1_000}
                                                                    for c, _u, _q in ITEMS]))
    works = frappe.get_all("Task", filters={"project": project, "is_group": 0}, pluck="name", order_by="pm_path asc")
    chosen = works[::3]  # a third of the work items
    started = time.perf_counter()
    for start in range(0, len(chosen), 33):  # 33 work items x 3 materials = 99 rows a stock entry
        materials.issue(project, [{"task": t, "item": c, "qty": 5} for t in chosen[start:start + 33] for c, _u, _q in ITEMS])
    print(f"cấp phát cho {len(chosen)} công tác ({len(chosen) * 3} dòng, {(len(chosen) + 32) // 33} phiếu): "
          f"{(time.perf_counter() - started) * 1000:.0f} ms")
    frappe.db.set_value("Task", {"name": ["in", chosen[:200]]}, "pmc_done_qty", 0.001)  # used far above the norm
    frappe.db.commit()
    timed("một phiếu cấp phát 99 dòng", lambda: materials.issue(
        project, [{"task": t, "item": c, "qty": 1} for t in chosen[:33] for c, _u, _q in ITEMS]))
    view = timed("tổng quan vật tư (định mức so với thực tế)", lambda: materials.overview(project))
    print(f"  {len(view['rows'])} dòng, {view['over_norm']} vượt định mức, tồn kho {len(view['stock'])} vật tư ({store})")
    timed("tính lại chi phí cả dự án", lambda: costs.refresh(project))
    timed("bảng chi phí", lambda: costs.summary(project))
    hits = timed("quét cảnh báo vượt định mức (mọi dự án)", lambda: materials.over_norm(frappe._dict(), None))
    print(f"  {len(hits)} kết quả")
    frappe.db.rollback()
    reset()


def reset(quiet=False):
    from pm_construction.pm_construction.setup.demo_site import drop_site

    frappe.set_user("Administrator")
    for project in frappe.get_all("Project", filters={"pm_code": CODE}, pluck="name"):
        drop_site([project])
        for doctype in ("PMC BOQ Item", "PMC BOQ", "PM Activity", "PM Snapshot", "PM Alert"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    for w in range(WORKS):
        frappe.db.delete("PMC Norm Material", {"parent": f"PERF.{w:03d}"})
        frappe.db.delete("PMC Material Norm", {"name": f"PERF.{w:03d}"})
    for code, _u, _q in ITEMS:
        frappe.db.delete("Bin", {"item_code": code})
        frappe.db.delete("Stock Ledger Entry", {"item_code": code})
        frappe.db.delete("Item", {"name": code})
    frappe.db.commit()
    if not quiet:
        print("removed")


frappe.init(site=SITE)
frappe.connect()
try:
    (seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
finally:
    frappe.destroy()
