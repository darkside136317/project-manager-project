"""M1: every DocType whose rows belong to a project is guarded by the project-scope hooks.

A DocType of the app with a `project` field that is not in constants.PROJECT_SCOPED (and so has no hooks) would leak
every project's rows to every user who may read the DocType: this test fails before that ships.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_hook_coverage
"""

import frappe

from project_manager.project_manager.constants import PROJECT_SCOPED
from project_manager.project_manager.services.audit import AUDITED_DOCTYPES
from project_manager.tests.helpers import PMTestCase

APP_MODULES = ("Project Manager",)


class TestHookCoverage(PMTestCase):
    def test_scoped_doctypes_have_both_hooks(self):
        queries = frappe.get_hooks("permission_query_conditions")
        checks = frappe.get_hooks("has_permission")
        for doctype in ("Project", *PROJECT_SCOPED):
            self.assertIn(doctype, queries, f"{doctype}: permission_query_conditions missing")
            self.assertIn(doctype, checks, f"{doctype}: has_permission missing")

    def test_every_app_doctype_with_a_project_is_scoped(self):
        unscoped = []
        for name in frappe.get_all("DocType", filters={"module": ["in", APP_MODULES], "istable": 0, "issingle": 0},
                                   pluck="name"):
            if frappe.get_meta(name).has_field("project") and name not in PROJECT_SCOPED:
                unscoped.append(name)
        self.assertEqual(unscoped, [])

    def test_audited_doctypes_exist(self):
        for doctype in AUDITED_DOCTYPES:
            self.assertTrue(frappe.db.exists("DocType", doctype), doctype)
