"""The archive layer is installed and wired into the core: its DocTypes are scoped by project like the core's, its
capabilities, MinIO collection and catalogues reach the core through the core's hooks, and its set-up gives the
company archivist a permission group and the built-in roles their archive capabilities.

Run: bench --site <site> run-tests --app pm_archive --module pm_archive.tests.test_install
"""

import frappe
from frappe.tests import IntegrationTestCase
from project_manager.project_manager import constants as C
from project_manager.project_manager import extensions
from project_manager.project_manager.services import object_storage

from pm_archive.pm_archive import constants as A


class TestInstall(IntegrationTestCase):
    def test_scoped_doctypes_have_both_hooks(self):
        queries = frappe.get_hooks("permission_query_conditions")
        checks = frappe.get_hooks("has_permission")
        for doctype in A.PROJECT_SCOPED:
            self.assertIn(doctype, queries, doctype)
            self.assertIn(doctype, checks, doctype)

    def test_every_layer_doctype_with_a_project_is_scoped(self):
        for name in frappe.get_all("DocType", filters={"module": A.MODULE, "istable": 0}, pluck="name"):
            if frappe.get_meta(name).has_field("project"):
                self.assertIn(name, A.PROJECT_SCOPED, name)

    def test_the_core_sees_the_layer(self):
        self.assertTrue({A.MANAGE_ALL, A.VIEW_ALL} <= extensions.capability_codes())
        self.assertTrue({A.VIEW, A.MANAGE} <= extensions.project_capability_codes())
        self.assertIn(A.VIEW_ALL, extensions.builtin_capabilities()[C.DIRECTOR_ROLE])
        self.assertIn(A.COLLECTION, object_storage.collections())
        self.assertEqual(extensions.object_stores()[A.COLLECTION],
                         [("PM Archive Item", "object_key"), ("PM Archive File", "aip_key")])
        doctypes = {entry["doctype"] for entry in extensions.masters()}
        self.assertTrue({"PM Archive Category", "PM Archive Storage"} <= doctypes)

    def test_the_archivist_group_and_the_role_grants(self):
        group = frappe.get_doc("PM Role Profile", A.ARCHIVIST_ROLE)
        self.assertEqual({row.capability for row in group.capabilities}, {A.MANAGE_ALL, A.VIEW_ALL})
        director = {row.capability for row in frappe.get_doc("PM Role Profile", C.DIRECTOR_ROLE).capabilities}
        self.assertIn(A.VIEW_ALL, director)
        for role, codes in A.ROLE_GRANTS.items():
            held = {row.capability for row in frappe.get_doc("PM Project Role", role).capabilities}
            self.assertTrue(set(codes) <= held, role)
