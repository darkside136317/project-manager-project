"""Speed of a large BOQ (M6): read, import and approve a 3 000-line bill of quantities, then a second version with a
tenth of its lines changed. Runs on a temporary project (code PERF-BOQ), removed by `reset`:

    docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/boq_check.py
    docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - reset < ../scripts/perf/boq_check.py
"""

import io
import os
import sys
import time

import frappe

SITE = os.environ.get("PERF_SITE", "pm.localhost")
CODE = "PERF-BOQ"
SECTIONS, WORKS = 100, 29  # 3 000 lines


def sheet(change: bool = False) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    page = book.active
    page.append(["STT", "Mã hiệu", "Nội dung công việc", "Đơn vị", "Khối lượng", "Đơn giá", "Thành tiền"])
    for s in range(SECTIONS):
        page.append([f"{s + 1}", "", f"HẠNG MỤC {s + 1}", "", None, None, None])
        for w in range(WORKS):
            qty = 10 + w + (1 if change and w % 10 == 0 else 0)
            page.append([f"{s + 1}.{w + 1}", f"AF.{w:05d}", f"Công tác {w + 1} của hạng mục {s + 1}", "m3", qty,
                         100_000 + w * 1000, qty * (100_000 + w * 1000)])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def timed(label, action):
    started = time.perf_counter()
    result = action()
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms")
    return result


def seed():
    from pm_construction.pm_construction.services import boq, boq_import

    reset(quiet=True)
    frappe.set_user("Administrator")
    project = frappe.get_doc({"doctype": "Project", "project_name": "Đo BOQ", "pm_code": CODE,
                              "company": frappe.defaults.get_global_default("company")}).insert(ignore_permissions=True).name
    first, second = sheet(), sheet(change=True)
    parsed = timed(f"đọc tệp {len(first) // 1024} KB", lambda: boq_import.parse(first))
    print(f"  {parsed['sections']} hạng mục, {parsed['works']} công tác")
    version = timed("nhập bản 1", lambda: boq.import_version(project, first, "v1.xlsx"))
    frappe.db.commit()
    timed("duyệt bản 1 (sinh WBS)", lambda: boq.approve(version.name))
    frappe.db.commit()
    version = timed("nhập bản 2", lambda: boq.import_version(project, second, "v2.xlsx"))
    frappe.db.commit()
    result = timed("duyệt bản 2 (cập nhật WBS)", lambda: boq.approve(version.name))
    frappe.db.commit()
    print(f"  bản 2: {result['sync']['created']} mới, {result['sync']['updated']} cập nhật")
    print(f"PROJECT={project}")


def reset(quiet=False):
    frappe.set_user("Administrator")
    for project in frappe.get_all("Project", filters={"pm_code": CODE}, pluck="name"):
        for doctype in ("PMC BOQ Item", "PMC BOQ", "PM Activity", "PM Snapshot"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    frappe.db.commit()
    if not quiet:
        print("removed")


frappe.init(site=SITE)
frappe.connect()
try:
    (seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
finally:
    frappe.destroy()
