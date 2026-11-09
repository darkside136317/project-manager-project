"""The construction layer's DocTypes are scoped by project like the core's, and the layer is wired into the core
through the core's hooks (project_manager/extensions.py).

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_hook_coverage
"""

import frappe
from frappe.tests import IntegrationTestCase
from project_manager.project_manager import extensions

from pm_construction.pm_construction import constants as K


class TestLayerHooks(IntegrationTestCase):
    def test_scoped_doctypes_have_both_hooks(self):
        queries = frappe.get_hooks("permission_query_conditions")
        checks = frappe.get_hooks("has_permission")
        for doctype in K.PROJECT_SCOPED:
            self.assertIn(doctype, queries, doctype)
            self.assertIn(doctype, checks, doctype)

    def test_every_layer_doctype_with_a_project_is_scoped(self):
        for name in frappe.get_all("DocType", filters={"module": "PM Construction", "istable": 0}, pluck="name"):
            if frappe.get_meta(name).has_field("project"):
                self.assertIn(name, K.PROJECT_SCOPED, name)

    def test_the_core_sees_the_layer(self):
        self.assertEqual(extensions.rollup_methods().get(K.ESTIMATE_METHOD), "pmc_estimate_value")
        self.assertIn("PMC Site Diary", extensions.discussion_targets())
        self.assertIn("construction", extensions.spa_modules())
        options = frappe.get_meta("Project").get_field("pm_rollup_method").options.split("\n")
        self.assertIn(K.ESTIMATE_METHOD, options)
        for code in K.ACCEPTANCE_CODES:
            self.assertTrue(frappe.db.exists("PM Form Template", {"code": code}), code)
        for node_type in (K.NODE_SECTION, K.NODE_WORK):
            self.assertTrue(frappe.db.exists("PM Node Type", node_type))
