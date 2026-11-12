"""M10 of the construction layer: the actual costs of the work items in the earned value, the two reports, the site part
of the dossier.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_reporting
"""

import frappe
from frappe.utils import nowdate
from project_manager.project_manager.services import budget, closing, reports

from pm_construction.pm_construction.services import diary, reporting
from pm_construction.tests.construction_helpers import ENGINEER, MANAGER, OUTSIDER, as_user
from pm_construction.tests.site_helpers import SiteBase


class TestReporting(SiteBase):
    def test_costs_reach_the_earned_value(self):
        frappe.db.set_value("Task", self.footing, {"pmc_material_cost": 300, "pmc_machine_cost": 200, "pmc_labour_cost": 100})
        rows = [r for r in reporting.actual_costs(self.project) if r["task"] == self.footing]
        self.assertEqual({r["category"]: r["amount"] for r in rows}, {"Vật tư": 300, "Máy thi công": 200, "Nhân công": 100})
        name = as_user(MANAGER, budget.save_draft, self.project, "Gốc", [{"category": "Vật tư", "amount": 5000}])["name"]
        as_user(MANAGER, budget.approve, name)
        figures = as_user(MANAGER, budget.evm, self.project)
        self.assertGreaterEqual(figures["ac"], 600)
        view = as_user(MANAGER, budget.overview, self.project)
        material = next(r for r in view["by_category"] if r["category"] == "Vật tư")
        self.assertEqual(material["budget"], 5000)
        self.assertGreaterEqual(material["actual"], 300)

    def test_reports_of_the_layer(self):
        slugs = [r.slug for r in as_user(MANAGER, reports.visible)]
        self.assertIn("vat-tu-dinh-muc", slugs)
        self.assertIn("chi-phi-du-toan", slugs)
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, reports.run, "vat-tu-dinh-muc", {})  # needs a project
        norms = as_user(ENGINEER, reports.run, "vat-tu-dinh-muc", {"project": self.project})
        self.assertGreater(norms["total"], 0)
        costs = as_user(MANAGER, reports.run, "chi-phi-du-toan", {"project": self.project})
        self.assertEqual(costs["summary"]["label"], "Cộng")
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, reports.run, "chi-phi-du-toan", {"project": self.project})
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, reports.run, "vat-tu-dinh-muc", {"project": self.project})

    def test_site_part_of_the_dossier(self):
        as_user(ENGINEER, diary.record, self.project, nowdate(), {"weather": "Nắng", "workers": 8},
                [{"task": self.footing, "qty": 2}])
        parts = {p["path"]: p for p in as_user(MANAGER, reporting.dossier_parts, self.project)}
        self.assertIn("thi-cong/nhat-ky-thi-cong.csv", parts)
        self.assertIn("thi-cong/khoi-luong-theo-ngay.csv", parts)
        self.assertTrue(any(path.startswith("thi-cong/bang-khoi-luong-v") for path in parts))
        self.assertEqual(as_user(OUTSIDER, reporting.dossier_parts, self.project), [])
        url = closing.build_dossier(self.project, MANAGER)
        paths = {e["path"] for e in closing.manifest_of(url)["entries"]}
        self.assertIn("thi-cong/nhat-ky-thi-cong.csv", paths)
        for name in frappe.get_all("File", filters={"file_url": url}, pluck="name"):
            frappe.delete_doc("File", name, force=True, ignore_permissions=True)
