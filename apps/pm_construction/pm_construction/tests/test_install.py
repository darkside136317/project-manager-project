"""M0: the construction layer is installed on top of the core."""

import frappe
from frappe.tests import IntegrationTestCase


class TestInstall(IntegrationTestCase):
    def test_layer_sits_on_the_core(self):
        installed = frappe.get_installed_apps()
        self.assertIn("project_manager", installed)
        self.assertIn("pm_construction", installed)
        self.assertLess(installed.index("project_manager"), installed.index("pm_construction"))

    def test_declares_its_dependencies(self):
        required = frappe.get_hooks("required_apps", app_name="pm_construction")
        self.assertIn("erpnext", required)
        self.assertIn("project_manager", required)
