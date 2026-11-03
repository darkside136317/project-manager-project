"""M0: a site made by scripts/bootstrap is fully set up, and the SPA host page behaves."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, nowdate

from project_manager.project_manager.services.web import inline_json
from project_manager.project_manager.setup.wizard import fiscal_year_dates
from project_manager.www import pm


class TestBootstrapDefaults(IntegrationTestCase):
    def test_setup_wizard_is_complete(self):
        self.assertTrue(frappe.is_setup_complete())

    def test_default_company_with_warehouses(self):
        company = frappe.defaults.get_global_default("company")
        self.assertTrue(company and frappe.db.exists("Company", company))
        # ERPNext makes a group warehouse and its stores for every new company.
        self.assertTrue(frappe.db.exists("Warehouse", {"company": company, "is_group": 1}))
        self.assertGreaterEqual(frappe.db.count("Warehouse", {"company": company, "is_group": 0}), 3)

    def test_fiscal_year_covers_today(self):
        from erpnext.accounts.utils import get_fiscal_year

        company = frappe.defaults.get_global_default("company")
        start, end = get_fiscal_year(nowdate(), company=company)[1:3]
        self.assertLessEqual(getdate(start), getdate(nowdate()))
        self.assertGreaterEqual(getdate(end), getdate(nowdate()))

    def test_company_holiday_list_has_days_off(self):
        company = frappe.defaults.get_global_default("company")
        name = frappe.db.get_value("Company", company, "default_holiday_list")
        self.assertTrue(name)
        holidays = frappe.get_doc("Holiday List", name)
        self.assertLessEqual(getdate(holidays.from_date), getdate(nowdate()))
        self.assertGreaterEqual(getdate(holidays.to_date), getdate(nowdate()))
        self.assertTrue(any(row.weekly_off for row in holidays.holidays))

    def test_system_settings_follow_the_company(self):
        company = frappe.defaults.get_global_default("company")
        settings = frappe.get_single("System Settings")
        self.assertEqual(settings.country, frappe.db.get_value("Company", company, "country"))
        self.assertEqual(settings.currency, frappe.db.get_value("Company", company, "default_currency"))
        self.assertTrue(settings.time_zone)


class TestFiscalYearDates(IntegrationTestCase):
    def test_calendar_year(self):
        self.assertEqual(fiscal_year_dates("01-01", "2026-03-15"), (getdate("2026-01-01"), getdate("2026-12-31")))

    def test_year_starting_in_april(self):
        self.assertEqual(fiscal_year_dates("04-01", "2026-03-15"), (getdate("2025-04-01"), getdate("2026-03-31")))
        self.assertEqual(fiscal_year_dates("04-01", "2026-04-01"), (getdate("2026-04-01"), getdate("2027-03-31")))


class TestSpaHost(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_inline_json_cannot_close_the_script(self):
        data = {"name": "</script><!-- &     Việt"}
        text = inline_json(data)
        for char in ("<", ">", "&", " ", " "):
            self.assertNotIn(char, text)
        self.assertEqual(json.loads(text), data)

    def test_guest_goes_to_login(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.Redirect):
            pm.get_context(frappe._dict())
        self.assertTrue(frappe.local.flags.redirect_location.startswith("/login?redirect-to="))

    def test_system_user_gets_boot_data(self):
        context = pm.get_context(frappe._dict())
        boot = json.loads(context.boot_json)
        self.assertEqual(boot["user"]["name"], "Administrator")
        self.assertTrue(boot["csrf_token"])
        self.assertEqual(boot["company"], frappe.defaults.get_global_default("company"))
