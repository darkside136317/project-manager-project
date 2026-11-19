"""M12: who sees and who changes the archive files of a project.

* the manager (archive.manage) sees them all and builds them, but does not file them;
* the site commander (archive.view) sees them, except the restricted ones (the project's data);
* an engineer (no archive capability) and an outsider see nothing;
* the archivist sees and files every project's files without being a member; the director sees them all.
Through Frappe's own list API the same, and a download needs the file's permission.

Run: bench --site <site> run-tests --app pm_archive --module pm_archive.tests.test_access
"""

import frappe
from project_manager.project_manager.services import closing

from pm_archive.pm_archive import constants as A
from pm_archive.pm_archive.api import archive as api
from pm_archive.pm_archive.services import register
from pm_archive.tests.archive_helpers import (
    ARCHIVIST,
    COMMANDER,
    DIRECTOR,
    ENGINEER,
    MANAGER,
    OUTSIDER,
    ArchiveBase,
    as_user,
)


class TestAccess(ArchiveBase):
    def setUp(self):
        super().setUp()
        self.document("Hợp đồng", "Hợp đồng")
        closing.close(self.project, "Xong")  # files of every kind, the data one restricted
        self.internal = frappe.db.get_value("PM Archive File", {"project": self.project, "category": "01.01"}, "name")
        self.restricted = frappe.db.get_value("PM Archive File", {"project": self.project, "category": "02.03"}, "name")
        self.assertEqual(frappe.db.get_value("PM Archive File", self.restricted, "access_mode"), A.RESTRICTED)

    def names(self, user):
        return {f["name"] for f in as_user(user, register.overview, self.project)["files"]}

    def listed(self, user):
        return set(as_user(user, frappe.get_list, "PM Archive File", filters={"project": self.project}, pluck="name"))

    def test_members_by_their_role(self):
        self.assertTrue({self.internal, self.restricted} <= self.names(MANAGER))
        self.assertIn(self.internal, self.names(COMMANDER))
        self.assertNotIn(self.restricted, self.names(COMMANDER))
        self.assertEqual(self.listed(COMMANDER), self.names(COMMANDER))
        for user in (ENGINEER, OUTSIDER):
            with self.assertRaises(frappe.PermissionError):
                as_user(user, register.overview, self.project)
            self.assertEqual(self.listed(user), set())

    def test_the_archivist_and_the_director_see_every_project(self):
        for user in (ARCHIVIST, DIRECTOR):
            self.assertTrue({self.internal, self.restricted} <= self.names(user), user)
            self.assertTrue({self.internal, self.restricted} <= self.listed(user), user)
        rows = as_user(ARCHIVIST, register.listing, {"project": self.project})["rows"]
        self.assertTrue({self.internal, self.restricted} <= {r.name for r in rows})
        self.assertTrue(as_user(ARCHIVIST, register.overview, self.project)["can"]["file"])
        self.assertFalse(as_user(DIRECTOR, register.overview, self.project)["can"]["manage"])

    def test_who_builds_and_who_files(self):
        self.assertTrue(as_user(MANAGER, api.compile_files, self.project) is not None)
        for user in (COMMANDER, ENGINEER, DIRECTOR):
            with self.assertRaises(frappe.PermissionError):
                as_user(user, api.compile_files, self.project)
        for user in (MANAGER, DIRECTOR):
            with self.assertRaises(frappe.PermissionError):
                as_user(user, api.file_records, [self.internal])
        self.assertEqual(as_user(ARCHIVIST, api.file_records, [self.internal])["queued"], [self.internal])

    def test_a_download_needs_the_files_permission(self):
        item = frappe.db.get_value("PM Archive Item", {"archive_file": self.internal}, "name")
        data = frappe.db.get_value("PM Archive Item", {"archive_file": self.restricted}, "name")
        self.assertEqual(as_user(COMMANDER, register.download, item).status_code, 200)
        with self.assertRaises(frappe.PermissionError):
            as_user(COMMANDER, register.download, data)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, register.download, item)
        self.assertEqual(as_user(ARCHIVIST, register.download, data).status_code, 200)
        self.assertTrue(frappe.db.exists("PM Audit Log", {"reference_doctype": "PM Archive Item",
                                                          "reference_name": str(data), "user": ARCHIVIST}))
