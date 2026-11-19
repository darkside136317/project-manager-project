"""M12: building a project's archive files (lập hồ sơ), closing the project, filing (nộp lưu), what cannot change
afterwards, the integrity check and the reminders.

Run: bench --site <site> run-tests --app pm_archive --module pm_archive.tests.test_filing
"""

import hashlib

import frappe
from frappe.utils import add_days, now_datetime
from project_manager.project_manager.services import closing, documents, object_storage

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.services import filing, integrity, locking, reminders
from pm_archive.tests.archive_helpers import ARCHIVIST, MANAGER, ArchiveBase, as_user, pdf


class TestCompile(ArchiveBase):
    def test_records_go_to_their_category_once(self):
        legal = self.document("Hợp đồng thi công", "Hợp đồng")
        self.document("Ghi chú nháp", "Khác", approve=False)
        photo = self.photo()
        form = self.approved_form()
        result = filing.compile(self.project)
        self.assertEqual(result["added"], 3)  # the unapproved document waits (the project runs)
        legal_items = self.items(self.file_of("01.01"))
        self.assertEqual([i.source_doctype for i in legal_items], ["PM Document Version"])
        version = frappe.db.get_value("PM Document Version", {"document": legal, "version_no": 1}, "name")
        self.assertEqual(legal_items[0].source_name, str(version))
        self.assertEqual(legal_items[0].collection, "documents")
        self.assertEqual([i.source_name for i in self.items(self.file_of("02.01"))], [str(photo)])
        self.assertEqual([i.source_name for i in self.items(self.file_of("01.04"))], [str(form)])  # every form left over
        self.assertFalse(self.file_of("01.05"))
        self.assertEqual(filing.compile(self.project)["added"], 0)  # again: nothing new
        file = frappe.get_doc("PM Archive File", self.file_of("01.01"))
        self.assertEqual((file.status, file.item_count, file.retention), (A.DRAFT, 1, "20"))
        self.assertTrue(file.file_number.startswith(frappe.db.get_value("Project", self.project, "pm_code")))
        self.assertEqual(file.expires_on.year, file.end_date.year + 20)

    def test_a_newly_approved_version_joins_the_file(self):
        name = self.document("Giấy phép xây dựng")
        filing.compile(self.project)
        documents.add_version(name, pdf("bản 2"), "gp2.pdf")
        self.assertEqual(filing.compile(self.project)["added"], 0)  # not approved yet
        documents.approve(name, 2)
        self.assertEqual(filing.compile(self.project)["added"], 1)
        self.assertEqual([i.title.split("(")[-1] for i in self.items(self.file_of("01.01"))], ["bản 1)", "bản 2)"])

    def test_the_manager_arranges_a_file(self):
        first, second = self.document("Hợp đồng A", "Hợp đồng"), self.document("Hợp đồng B", "Hợp đồng")
        self.assertTrue(first and second)
        filing.compile(self.project)
        file = self.file_of("01.01")
        a, b = self.items(file)
        as_user(MANAGER, filing.reorder, file, [b.name, a.name])
        self.assertEqual([i.name for i in self.items(file)], [b.name, a.name])
        as_user(MANAGER, filing.describe, a.name, {"doc_number": "15/2026/HĐ", "page_count": 12})
        self.assertEqual(frappe.db.get_value("PM Archive File", file, "page_count"), 12)
        as_user(MANAGER, filing.set_excluded, b.name, 1)
        self.assertEqual(frappe.db.get_value("PM Archive File", file, "item_count"), 1)
        other = filing.open_file(self.project, filing.rules().categories["01.05"])
        as_user(MANAGER, filing.move, a.name, other)
        self.assertEqual(frappe.db.get_value("PM Archive Item", a.name, "archive_file"), other)
        scan_bytes = pdf("bản scan")
        as_user(MANAGER, filing.upload, other, scan_bytes, "bien-ban-ky-tay.pdf",
                {"title": "Biên bản bàn giao mặt bằng (bản ký tay)", "page_count": 3})
        kinds = [i.kind for i in self.items(other)]
        self.assertEqual(kinds, [A.DOCUMENT, A.UPLOAD])
        scan = self.items(other)[-1]
        self.assertEqual(scan.collection, A.COLLECTION)
        self.assertEqual(self.store.get(scan.object_key[len(object_storage.PREFIX):]), scan_bytes)
        with self.assertRaises(frappe.ValidationError):
            filing.upload(other, b"<script>", "x.html")


class TestClosing(ArchiveBase):
    def test_closing_keeps_the_data_and_waits_for_the_archivist(self):
        self.document("Hợp đồng", "Hợp đồng")
        self.document("Bản nháp", "Khác", approve=False)
        closing.close(self.project, "Bàn giao xong")
        self.assertTrue(self.items(self.file_of("01.05"))[0].note)  # the unapproved document, noted so
        data = self.items(self.file_of("02.03"))
        self.assertTrue({"du-an.json", "cong-viec.csv", "thanh-vien.csv"} <=
                        {i.title.split(": ")[-1] for i in data})
        self.assertTrue(all(i.collection == A.COLLECTION and i.sha256 for i in data))
        self.assertEqual(len(self.items(self.file_of("02.02"))), 1)  # the discussions
        files = frappe.get_all("PM Archive File", filters={"project": self.project}, fields=["status", "waiting_since"])
        self.assertTrue(files and all(f.status == A.WAITING and f.waiting_since for f in files))
        self.assertNotIn("01.01", [g["code"] for g in filing.missing(self.project)])
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": ARCHIVIST, "document_name": self.project}))
        for item in data:  # the nightly sweep keeps this layer's objects
            object_storage.sweep_orphans()
            self.assertIn(item.object_key[len(object_storage.PREFIX):], self.store.objects)


class TestFiling(ArchiveBase):
    def filed(self):
        self.document("Hợp đồng chính", "Hợp đồng")
        self.document("Phụ lục hợp đồng", "Hợp đồng")
        filing.compile(self.project)
        file = self.file_of("01.01")
        left_out = self.items(file)[-1]
        filing.set_excluded(left_out.name, 1)
        self.assertEqual(locking.request([file])["queued"], [file])
        self.assertTrue(locking.run(file, ARCHIVIST))
        return file, left_out

    def test_filing_keeps_every_digest_and_locks(self):
        file, left_out = self.filed()
        doc = frappe.get_doc("PM Archive File", file)
        self.assertEqual((doc.status, doc.locked_by, doc.item_count), (A.FILED, ARCHIVIST, 1))
        self.assertFalse(frappe.db.exists("PM Archive Item", left_out.name))  # never part of the file
        item = self.items(file)[0]
        content = self.store.get(item.object_key[len(object_storage.PREFIX):])
        self.assertEqual(item.sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(doc.manifest_sha256, locking.manifest_of(file))
        with self.assertRaises(frappe.ValidationError):
            filing.describe(item.name, {"title": "Sửa sau khi nộp lưu"})
        with self.assertRaises(frappe.ValidationError):
            doc.title = "Sửa"
            doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("PM Archive Item", item.name, ignore_permissions=True)
        version = frappe.get_doc("PM Document Version", int(item.source_name))
        with self.assertRaises(frappe.ValidationError):  # its source stays in the project
            version.delete(ignore_permissions=True)

    def test_a_record_approved_later_goes_into_an_addendum(self):
        file, _left_out = self.filed()
        self.document("Phụ lục số 2", "Hợp đồng")
        filing.compile(self.project)
        addendum = self.file_of("01.01")
        self.assertNotEqual(addendum, file)
        self.assertEqual(frappe.db.get_value("PM Archive File", addendum, "is_addendum"), 1)

    def test_a_source_that_changed_is_not_filed(self):
        self.document("Hợp đồng", "Hợp đồng")
        filing.compile(self.project)
        file = self.file_of("01.01")
        frappe.db.set_value("PM Archive Item", self.items(file)[0].name, "sha256", "0" * 64)
        self.assertFalse(locking.run(file, ARCHIVIST))
        status, error = frappe.db.get_value("PM Archive File", file, ["status", "lock_error"])
        self.assertEqual(status, A.DRAFT)
        self.assertIn("SHA-256", error)

    def test_the_integrity_check_finds_changed_and_missing_items(self):
        self.document("Hợp đồng", "Hợp đồng")
        self.photo("a1.jpg")
        self.photo("a2.jpg")
        filing.compile(self.project)
        for code in ("01.01", "02.01"):
            self.assertTrue(locking.run(self.file_of(code), ARCHIVIST))
        self.assertEqual(frappe.db.get_value("PM Archive Check", integrity.run(file=self.file_of("02.01")),
                                             "status"), "Hoàn thành")
        first, second = self.items(self.file_of("02.01"))
        self.store.put(first.object_key[len(object_storage.PREFIX):], b"doi noi dung", "image/jpeg", {})
        self.store.delete(second.object_key[len(object_storage.PREFIX):])
        check = integrity.run(trigger="Thủ công")  # the whole archive (other projects' files on the site too)
        row = frappe.db.get_value("PM Archive Check", check, ["status", "checked"], as_dict=True)
        self.assertEqual(row.status, "Có lỗi")
        self.assertGreaterEqual(row.checked, 3)
        mine = [p for p in integrity.problems_of(check) if p["project"] == self.project]
        self.assertEqual(sorted((p["kind"], p["seq"]) for p in mine), [("changed", 1), ("missing", 2)])
        hits = integrity.alert_integrity(frappe._dict(days=0), now_datetime())
        mine = [h for h in hits if h.project == self.project]
        self.assertEqual(len(mine), 1)
        self.assertIn(ARCHIVIST, mine[0].direct)


class TestReminder(ArchiveBase):
    def test_files_waiting_too_long_are_reminded(self):
        self.document("Hợp đồng", "Hợp đồng")
        filing.compile(self.project)
        filing.request_filing(self.project)
        rule = frappe._dict(days=90)
        self.assertFalse([h for h in reminders.not_filed(rule, now_datetime()) if h.project == self.project])
        frappe.db.set_value("PM Archive File", self.file_of("01.01"), "waiting_since", add_days(now_datetime(), -100))
        hits = [h for h in reminders.not_filed(rule, now_datetime()) if h.project == self.project]
        self.assertEqual(len(hits), 1)
        self.assertIn(ARCHIVIST, hits[0].direct)
