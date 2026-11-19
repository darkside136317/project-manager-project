"""Demo data of the archive layer (after the core's and the construction layer's demos):

* the company archivist demo.luutru@pm.localhost (group "Lưu trữ", not a member of any project);
* the paper storage: Kho A › Giá 1 › Hộp 1–3;
* the files of the two running demo projects (town house, factory), still being built (Đang lập);
* a small project already handed over, DEMO-LT01 "Nhà kho vật tư (đã bàn giao)": closed, its files waiting for the
  archivist, the contract file filed (Đã nộp lưu) and its paper in Hộp 1.

    bench --site <site> execute pm_archive.pm_archive.setup.demo.up
    bench --site <site> execute pm_archive.pm_archive.setup.demo.down   (before the other demos' down)
"""

import io

import frappe
from frappe.utils import add_days, getdate, nowdate
from project_manager.project_manager import constants as C
from project_manager.project_manager.services import closing, documents, object_storage, projects

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.services import filing, locking

ARCHIVIST = "demo.luutru@pm.localhost"
MANAGER = "demo.quanly@pm.localhost"
CLOSED_CODE = "DEMO-LT01"
RUNNING = ("DEMO-NP01", "DEMO-XD01")
STORAGE = (("KHO-A", "Kho A", "Kho", None, 1), ("KHO-A-G1", "Giá 1", "Giá", "KHO-A", 1),
           ("KHO-A-G1-H01", "Hộp 1", "Hộp", "KHO-A-G1", 0), ("KHO-A-G1-H02", "Hộp 2", "Hộp", "KHO-A-G1", 0),
           ("KHO-A-G1-H03", "Hộp 3", "Hộp", "KHO-A-G1", 0))


def _pdf(title: str) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_metadata({"/Title": title})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _archivist():
    if frappe.db.exists("User", ARCHIVIST):
        return
    user = frappe.get_doc({"doctype": "User", "email": ARCHIVIST, "first_name": "Đỗ Lưu Trữ", "send_welcome_email": 0,
                           "user_type": "System User", "roles": [{"role": C.STAFF_ROLE}, {"role": A.ARCHIVIST_ROLE}]})
    user.flags.no_welcome_mail = True
    user.insert(ignore_permissions=True)


def _storage():
    for code, title, kind, parent, group in STORAGE:
        if not frappe.db.exists("PM Archive Storage", code):
            frappe.get_doc({"doctype": "PM Archive Storage", "code": code, "title": title, "kind": kind,
                            "parent_pm_archive_storage": parent, "is_group": group}).insert(ignore_permissions=True)


def _closed_project() -> str:
    today = getdate(nowdate())
    start = add_days(today, -200)
    project = projects.create({"project_name": "Nhà kho vật tư (đã bàn giao)", "pm_code": CLOSED_CODE,
                               "pm_state": "Đang thực hiện", "expected_start_date": start,
                               "expected_end_date": add_days(today, -20), "pm_manager": MANAGER})["name"]
    for title, category in (("Hợp đồng thi công số 08/2026/HĐ-XD", "Hợp đồng"),
                            ("Phụ lục hợp đồng số 01", "Hợp đồng"),
                            ("Giấy phép xây dựng", "Pháp lý"),
                            ("Bản vẽ thiết kế thi công", "Bản vẽ"),
                            ("Biên bản bàn giao công trình", "Biên bản")):
        name = documents.create(project, title, _pdf(title), f"{frappe.scrub(title)[:40]}.pdf", category)["name"]
        documents.approve(name, 1)
    closing.close(project, "Đã bàn giao cho chủ đầu tư, hết thời gian bảo hành")  # files wait for the archivist
    contract = frappe.db.get_value("PM Archive File", {"project": project, "category": "01.01"}, "name")
    items = frappe.get_all("PM Archive Item", filters={"archive_file": contract}, fields=["name", "title"],
                           order_by="seq asc")
    for number, item in enumerate(items, 1):
        filing.describe(item.name, {"doc_number": f"{number:02d}/2026/HĐ-XD" if "Hợp đồng" in item.title else "",
                                    "page_count": 6 + number, "author": "Công ty và chủ đầu tư"})
    filing.set_paper(contract, "KHO-A-G1-H01", "01", "Bản gốc có chữ ký, đóng dấu")
    if object_storage.configured():
        locking.run(contract, ARCHIVIST)  # filed: read-only from now on
    return project


def up():
    """Create the demo (idempotent)."""
    frappe.set_user("Administrator")
    if frappe.db.exists("Project", {"pm_code": CLOSED_CODE}):
        print("Archive demo already present")
        return
    _archivist()
    _storage()
    for code in RUNNING:
        project = frappe.db.get_value("Project", {"pm_code": code}, "name")
        if project:
            filing.compile(project)
    project = _closed_project()
    frappe.db.commit()
    print(f"Archive demo created: {project} ({CLOSED_CODE})")


def down():
    """Remove what `up` created (the archive files of the running demo projects too)."""
    frappe.set_user("Administrator")
    projects_ = frappe.get_all("Project", filters={"pm_code": ["in", [CLOSED_CODE, *RUNNING]]}, pluck="name")
    for project in projects_:
        files = frappe.get_all("PM Archive File", filters={"project": project}, fields=["name", "aip_key"])
        made = frappe.get_all("PM Archive Item", filters={"project": project, "collection": A.COLLECTION}, pluck="object_key")
        if object_storage.configured():
            object_storage.delete_many([*made, *[f.aip_key for f in files if f.aip_key]], A.COLLECTION)
        frappe.db.delete("PM Archive Item", {"project": project})
        frappe.db.delete("PM Archive File", {"project": project})
    for project in frappe.get_all("Project", filters={"pm_code": CLOSED_CODE}, pluck="name"):
        versions = frappe.get_all("PM Document Version", filters={"project": project}, pluck="object_key")
        if object_storage.configured():
            object_storage.delete_many(versions, "documents")
        for doctype in ("PM Activity", "PM Project Member", "PM Document Version", "PM Document", "PM Alert"):
            frappe.db.delete(doctype, {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    for code, *_rest in reversed(STORAGE):
        frappe.delete_doc("PM Archive Storage", code, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.delete("Notification Log", {"for_user": ARCHIVIST})
    frappe.delete_doc("User", ARCHIVIST, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()
    print("Archive demo removed")
