"""M1: what setup/install.py makes, and that running it again changes nothing.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_install
"""

import frappe

from project_manager.project_manager import constants as C
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import PMTestCase

COUNTED = ("Role", "PM Role Profile", "PM Project Role", "PM Node Type", "Custom Field", "Custom DocPerm")


class TestInstall(PMTestCase):
    def test_roles_and_groups(self):
        for role in C.ASSIGNABLE_ROLES:
            self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 1)
            self.assertTrue(frappe.db.exists("PM Role Profile", role))
        director = frappe.get_doc("PM Role Profile", C.DIRECTOR_ROLE)
        self.assertIn("portfolio.view_all", {r.capability for r in director.capabilities})
        self.assertTrue(frappe.db.get_value("PM Role Profile", C.ADMIN_ROLE, "is_admin"))

    def test_project_roles_and_node_types(self):
        for spec in C.DEFAULT_PROJECT_ROLES:
            doc = frappe.get_doc("PM Project Role", spec["role_name"])
            # the core's capabilities, and maybe those an installed layer adds (pm_archive's archive.view...)
            self.assertTrue(set(spec["capabilities"]) <= {r.capability for r in doc.capabilities}, spec["role_name"])
        for spec in C.DEFAULT_NODE_TYPES:
            self.assertTrue(frappe.db.exists("PM Node Type", spec["node_type"]))

    def test_custom_fields_and_defaults(self):
        for doctype, fields in install.CUSTOM_FIELDS.items():
            meta = frappe.get_meta(doctype)
            for field in fields:
                self.assertTrue(meta.has_field(field["fieldname"]), f"{doctype}.{field['fieldname']}")
        self.assertEqual(frappe.get_meta("Project").get_field("percent_complete_method").default, "Manual")
        self.assertEqual(frappe.db.get_single_value("PM Settings", "enable_audit_log"), 1)

    def test_app_roles_have_rules_on_project_and_task(self):
        for doctype, roles in install.ERPNEXT_PERMISSIONS.items():
            for role in roles:
                self.assertTrue(frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}),
                                f"{role} on {doctype}")
            # ERPNext's own roles keep their rules
            self.assertTrue(frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "Projects User"}))

    def test_running_again_changes_nothing(self):
        before = {doctype: frappe.db.count(doctype) for doctype in COUNTED}
        install.seed_all()
        self.assertEqual({doctype: frappe.db.count(doctype) for doctype in COUNTED}, before)

    def test_an_administrators_change_survives(self):
        frappe.db.set_value("PM Project Role", "Kỹ sư", "description", "Đã sửa")
        install.seed_all()
        self.assertEqual(frappe.db.get_value("PM Project Role", "Kỹ sư", "description"), "Đã sửa")
