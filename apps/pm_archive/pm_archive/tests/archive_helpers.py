"""Shared set-up of the archive layer's tests: a project with a manager (archive.manage), a site commander
(archive.view), an engineer (no archive capability), an outsider, the company archivist (not a member) and a director;
records of every kind the categories file, in MinIO stand-in objects and Frappe files."""

import hashlib

import frappe
from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import documents, object_storage
from project_manager.project_manager.services.queries import reserve_ids
from project_manager.tests.helpers import TAG, PMTestCase, add_member, drop_user, make_project, make_user, memory_store

from pm_archive.pm_archive import constants as A

MANAGER = f"ar.manager.{TAG}@example.com"
COMMANDER = f"ar.commander.{TAG}@example.com"
ENGINEER = f"ar.engineer.{TAG}@example.com"
OUTSIDER = f"ar.outsider.{TAG}@example.com"
ARCHIVIST = f"ar.archivist.{TAG}@example.com"
DIRECTOR = f"ar.director.{TAG}@example.com"
USERS = (MANAGER, COMMANDER, ENGINEER, OUTSIDER, ARCHIVIST, DIRECTOR)


def pdf(text: str) -> bytes:
    """A real one-page PDF (Frappe reads the PDFs it keeps), different for each text."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": text})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class ArchiveBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for user in (MANAGER, COMMANDER, ENGINEER, OUTSIDER):
            make_user(user, [C.STAFF_ROLE])
        make_user(ARCHIVIST, [C.STAFF_ROLE, A.ARCHIVIST_ROLE])
        make_user(DIRECTOR, [C.DIRECTOR_ROLE])
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.store = memory_store(self)
        self.project = make_project("Dự án lưu trữ")
        add_member(self.project, MANAGER, "Quản lý dự án")
        add_member(self.project, COMMANDER, "Chỉ huy trưởng")
        add_member(self.project, ENGINEER, "Kỹ sư")
        frappe.db.set_value("Project", self.project, {"pm_code": f"LT{TAG.upper()}", "pm_manager": MANAGER})

    # --- records ------------------------------------------------------------------------------------------------------
    def document(self, title, category="Pháp lý", approve=True, raw=None):
        raw = raw or pdf(f"{title} {frappe.generate_hash(length=6)}")
        name = documents.create(self.project, title, raw, f"{frappe.scrub(title)}.pdf", category)["name"]
        if approve:
            documents.approve(name, 1)
        return name

    def photo(self, name="anh.jpg"):
        raw = b"\xff\xd8\xff" + frappe.generate_hash(length=20).encode()
        key = object_storage.put(raw, name, "image/jpeg", "media")
        doc = frappe.get_doc({"doctype": "PM Media", "project": self.project, "reference_doctype": "Project",
                              "reference_name": self.project, "file_name": name, "content_type": "image/jpeg",
                              "size_bytes": len(raw), "uploaded_by": "Administrator", "object_key": key,
                              "client_uuid": frappe.generate_hash(length=16), "is_deleted": 0})
        doc.name = reserve_ids("PM Media", 1)[0]
        doc.db_insert()
        return doc.name

    def approved_form(self, code="BM-THU", title="Biên bản kiểm tra"):
        content = pdf(f"biểu mẫu {frappe.generate_hash(length=6)}")
        file = frappe.get_doc({"doctype": "File", "file_name": f"bm-{frappe.generate_hash(length=6)}.pdf",
                               "content": content, "is_private": 1}).insert(ignore_permissions=True)
        doc = frappe.get_doc({"doctype": "PM Form Submission", "template_code": code, "title": title,
                              "project": self.project, "state": C.SUB_APPROVED, "data": "{}", "version": 1,
                              "submitted_by": "Administrator", "reviewed_on": frappe.utils.now_datetime(),
                              "pdf_file": file.file_url, "pdf_hash": hashlib.sha256(content).hexdigest()})
        doc.name = reserve_ids("PM Form Submission", 1)[0]
        doc.db_insert()
        return doc.name

    # --- reading back -------------------------------------------------------------------------------------------------
    def file_of(self, code):
        return frappe.db.get_value("PM Archive File", {"project": self.project, "category": code}, "name",
                                   order_by="creation desc")

    def items(self, file, **filters):
        return frappe.get_all("PM Archive Item", filters={"archive_file": file, **filters},
                              fields=["name", "seq", "kind", "source_doctype", "source_name", "title", "object_key",
                                      "collection", "file_url", "sha256", "excluded", "note"], order_by="seq asc")
