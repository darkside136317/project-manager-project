"""M12: the archive's catalogues (reports of the core's hub) and the archive package of TT 05/2025/TT-BNV.

Run: bench --site <site> run-tests --app pm_archive --module pm_archive.tests.test_catalogue
"""

import hashlib
import io
import zipfile

import frappe
from lxml import etree
from project_manager.project_manager.services import object_storage
from project_manager.project_manager.services import reports as report_service

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.services import aip_export, filing, locking
from pm_archive.tests.archive_helpers import ARCHIVIST, ENGINEER, MANAGER, ArchiveBase, as_user


class TestCatalogue(ArchiveBase):
    def filed(self):
        self.document("Hợp đồng thi công", "Hợp đồng")
        self.document("Phụ lục 01", "Hợp đồng")
        filing.compile(self.project)
        file = self.file_of("01.01")
        filing.describe(self.items(file)[0].name, {"doc_number": "15/2026/HĐ-XD", "page_count": 8})
        self.assertTrue(locking.run(file, ARCHIVIST))
        return file

    def test_the_catalogues_keep_to_what_the_user_reads(self):
        file = self.filed()
        rows = as_user(MANAGER, report_service.run, "muc-luc-ho-so", {"project": self.project})["rows"]
        self.assertIn(frappe.db.get_value("PM Archive File", file, "file_number"), [r["file_number"] for r in rows])
        self.assertEqual(as_user(ENGINEER, report_service.run, "muc-luc-ho-so", {"project": self.project})["rows"], [])
        items = as_user(MANAGER, report_service.run, "muc-luc-van-ban", {"archive_file": file})
        self.assertEqual([r["seq"] for r in items["rows"]], [1, 2])
        self.assertEqual(items["rows"][0]["doc_number"], "15/2026/HĐ-XD")
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, report_service.run, "muc-luc-van-ban", {"archive_file": file})

    def test_the_archive_package(self):
        file = self.filed()
        key = aip_export.run(file, ARCHIVIST)
        self.assertTrue(key)
        row = frappe.db.get_value("PM Archive File", file, ["aip_key", "aip_size", "aip_sha256"], as_dict=True)
        content = self.store.get(key[len(object_storage.PREFIX):])
        self.assertEqual((len(content), hashlib.sha256(content).hexdigest()), (row.aip_size, row.aip_sha256))
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            names = package.namelist()
            root = names[0].split("/")[0]
            for part in ("METS.xml", "metadata/descriptive/EAD.xml", "metadata/preservation/PREMIS.xml",
                         "representations/rep1/METS.xml", "representations/rep1/data/File1.pdf",
                         "representations/rep1/data/File2.pdf", "schemas/METS.xsd"):
                self.assertIn(f"{root}/{part}", names, part)
            ead = etree.fromstring(package.read(f"{root}/metadata/descriptive/EAD.xml"))
            self.assertTrue(ead.findtext("arcFileCode").endswith(frappe.db.get_value("PM Archive File", file, "file_number")))
            self.assertEqual(ead.findtext("totalDoc"), "2")
            first = self.items(file)[0]
            self.assertEqual(package.read(f"{root}/representations/rep1/data/File1.pdf"),
                             self.store.get(first.object_key[len(object_storage.PREFIX):]))
            doc = etree.fromstring(package.read(f"{root}/representations/rep1/metadata/descriptive/EAD_doc_File1.xml"))
            self.assertEqual(doc.findtext("codeNumber"), "15/2026/HĐ-XD")

    def test_a_package_refuses_a_document_that_changed(self):
        file = self.filed()
        first = self.items(file)[0]
        self.store.put(first.object_key[len(object_storage.PREFIX):], b"khac", "application/pdf", {})
        self.assertIsNone(aip_export.run(file, ARCHIVIST))
        self.assertIn("nộp lưu", frappe.db.get_value("PM Archive File", file, "aip_error"))

    def test_only_a_filed_file_has_a_package(self):
        self.document("Hợp đồng", "Hợp đồng")
        filing.compile(self.project)
        with self.assertRaises(frappe.ValidationError):
            aip_export.request(self.file_of("01.01"))
        self.assertEqual(frappe.db.get_value("PM Archive File", self.file_of("01.01"), "status"), A.DRAFT)
