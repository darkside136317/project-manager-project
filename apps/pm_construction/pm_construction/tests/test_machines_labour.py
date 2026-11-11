"""M8: machines (owned ones are ERPNext Assets moved by Asset Movements), shifts on work items, crews and their
attendance, and the cost of the work items against their estimate.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_machines_labour
"""

import frappe
from frappe.utils import add_days, flt, nowdate
from project_manager.project_manager import constants as C
from project_manager.project_manager.services import alerts, assignments
from project_manager.tests.helpers import TAG

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import costs, labour, machines
from pm_construction.tests.construction_helpers import COMMANDER, ENGINEER, LEAD, MANAGER, OUTSIDER, as_user
from pm_construction.tests.site_helpers import SiteBase

RATE = 2_000_000
CREW, OTHER_CREW = f"To ne {TAG}", f"To sat {TAG}"


class MachineBase(SiteBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from pm_construction.pm_construction.services.materials import account_of
        from pm_construction.pm_construction.setup.install import root_item_group

        company = frappe.defaults.get_global_default("company")
        category = f"May thi cong {TAG}"
        if not frappe.db.exists("Asset Category", category):
            frappe.get_doc({"doctype": "Asset Category", "asset_category_name": category, "accounts": [{
                "company_name": company, "fixed_asset_account": account_of(company, "Fixed Asset"),
                "accumulated_depreciation_account": account_of(company, "Accumulated Depreciation"),
                "depreciation_expense_account": account_of(company, "Depreciation")}]}).insert(ignore_permissions=True)
        item = f"MAY-{TAG}"
        if not frappe.db.exists("Item", item):
            frappe.get_doc({"doctype": "Item", "item_code": item, "item_name": "Máy đào (thử)", "item_group": root_item_group(),
                            "stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1,
                            "asset_category": category}).insert(ignore_permissions=True)
        yard = machines.site_location(None)
        asset = frappe.get_doc({"doctype": "Asset", "item_code": item, "asset_name": f"Máy đào {TAG}", "company": company,
                                "location": yard, "is_existing_asset": 1, "asset_owner": "Company",
                                "gross_purchase_amount": 900_000_000, "purchase_amount": 900_000_000, "net_purchase_amount": 900_000_000,
                                "purchase_date": "2025-01-10", "available_for_use_date": "2025-01-10",
                                "calculate_depreciation": 0, "asset_category": category})
        asset.insert(ignore_permissions=True)
        asset.submit()
        cls.asset, cls.category, cls.asset_item = asset.name, category, item
        cls.digger = frappe.get_doc({"doctype": "PMC Machine", "machine_code": f"MD-{TAG}", "machine_name": f"Máy đào {TAG}",
                                     "ownership": K.OWNED, "asset": asset.name, "shift_rate": RATE, "fuel_norm": 60}).insert(
            ignore_permissions=True).name
        cls.crane = frappe.get_doc({"doctype": "PMC Machine", "machine_code": f"CC-{TAG}", "machine_name": f"Cần cẩu {TAG}",
                                    "ownership": K.RENTED, "shift_rate": 3_500_000}).insert(ignore_permissions=True).name
        for name, leader in ((CREW, LEAD), (OTHER_CREW, None)):
            if not frappe.db.exists("PM Team", {"team_name": name}):
                frappe.get_doc({"doctype": "PM Team", "team_name": name, "team_type": "Tổ đội", "leader": leader,
                                "is_active": 1}).insert(ignore_permissions=True)
        cls.crew = frappe.db.get_value("PM Team", {"team_name": CREW}, "name")
        cls.other_crew = frappe.db.get_value("PM Team", {"team_name": OTHER_CREW}, "name")
        cls.workers = [frappe.get_doc({"doctype": "PMC Worker", "full_name": f"Thợ {n} {TAG}", "team": cls.crew,
                                       "trade": "Thợ nề", "daily_rate": rate}).insert(ignore_permissions=True).name
                       for n, rate in ((1, 400_000), (2, 350_000))]
        cls.stranger = frappe.get_doc({"doctype": "PMC Worker", "full_name": f"Thợ sắt {TAG}", "team": cls.other_crew,
                                       "daily_rate": 380_000}).insert(ignore_permissions=True).name
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for name in frappe.get_all("Asset Movement", filters={"reference_name": ["is", "not set"]}, pluck="name"):
            items = frappe.get_all("Asset Movement Item", filters={"parent": name, "asset": cls.asset}, pluck="name")
            if items:
                frappe.db.delete("Asset Movement Item", {"parent": name})
                frappe.db.delete("Asset Movement", {"name": name})
        for doctype, names in (("PMC Machine", [cls.digger, cls.crane]), ("PMC Worker", [*cls.workers, cls.stranger])):
            for name in names:
                frappe.db.delete(doctype, {"name": name})
        frappe.db.delete("PMC Machine Transfer", {"machine": ["in", [cls.digger, cls.crane]]})
        frappe.db.delete("Asset", {"name": cls.asset})
        frappe.db.delete("Item", {"name": cls.asset_item})
        frappe.db.delete("Asset Category Account", {"parent": cls.category})
        frappe.db.delete("Asset Category", {"name": cls.category})
        for team in (cls.crew, cls.other_crew):
            frappe.db.delete("PM Team", {"name": team})
        frappe.db.commit()
        super().tearDownClass()

    def bring(self, machine=None, user=MANAGER):
        return as_user(user, machines.transfer, machine or self.digger, self.project)


class TestMachines(MachineBase):
    def test_an_owned_machine_moves_with_its_asset(self):
        moved = self.bring()
        self.assertTrue(moved["asset_movement"])
        target = frappe.db.get_value("Location", {"pm_project": self.project}, "name")
        self.assertEqual(frappe.db.get_value("Asset", self.asset, "location"), target)
        self.assertEqual(frappe.db.get_value("Asset Movement", moved["asset_movement"], ["docstatus", "pm_project"]),
                         (1, self.project))
        self.assertEqual(frappe.db.get_value("PMC Machine", self.digger, ["current_project", "status"]),
                         (self.project, K.MACHINE_BUSY))
        back = as_user(MANAGER, machines.transfer, self.digger, None, note="xong phần đào")
        self.assertEqual(frappe.db.get_value("Asset", self.asset, "location"), machines.YARD)
        self.assertIsNone(frappe.db.get_value("PMC Machine", self.digger, "current_project"))
        self.assertTrue(back["asset_movement"])

    def test_a_rented_machine_has_only_its_history(self):
        moved = self.bring(self.crane)
        self.assertIsNone(moved["asset_movement"])
        self.assertEqual(frappe.db.get_value("PMC Machine Transfer", moved["name"], ["project", "from_project"]),
                         (self.project, None))
        self.assertRaises(frappe.PermissionError, self.bring, self.crane, ENGINEER)  # no plan.edit

    def test_shifts_on_work_items(self):
        self.bring()
        shift = as_user(ENGINEER, machines.record_shift, self.project, self.digger, self.footing, nowdate(), 1.5, 8, 85,
                        "Anh Ba", client_uuid=f"shift-{self.footing}")
        again = as_user(ENGINEER, machines.record_shift, self.project, self.digger, self.footing, nowdate(), 1.5,
                        client_uuid=f"shift-{self.footing}")
        self.assertEqual((again["name"], again["again"]), (shift["name"], True))
        self.assertEqual(flt(frappe.db.get_value("PMC Machine Shift", shift["name"], "amount")), 1.5 * RATE)
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_machine_cost")), 1.5 * RATE)
        seen = as_user(ENGINEER, machines.overview, self.project)
        digger = next(m for m in seen["machines"] if m.name == self.digger)
        self.assertEqual((digger.shifts_total, digger.fuel_total, digger.fuel_expected), (1.5, 85, 90))
        self.assertNotIn("amount", seen["shifts"][0])  # no finance.view
        as_user(ENGINEER, machines.delete_shift, shift["name"])
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_machine_cost")), 0)

    def test_what_a_shift_refuses(self):
        self.assertRaises(frappe.ValidationError, as_user, ENGINEER, machines.record_shift, self.project, self.crane,
                          self.footing, nowdate(), 1)  # not at this project
        self.bring()
        self.assertRaises(frappe.ValidationError, as_user, ENGINEER, machines.record_shift, self.project, self.digger,
                          self.footing, nowdate(), 4)
        self.assertRaises(frappe.ValidationError, as_user, ENGINEER, machines.record_shift, self.project, self.digger,
                          self.footing, add_days(nowdate(), 1), 1)
        self.assertRaises(frappe.PermissionError, as_user, LEAD, machines.record_shift, self.project, self.digger,
                          self.footing, nowdate(), 1)  # a crew lead sees only the work given to them
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, machines.record_shift, self.project, self.digger,
                          None, nowdate(), 1)

    def test_maintenance_due(self):
        self.bring()
        frappe.db.set_value("PMC Machine", self.digger, "next_maintenance", add_days(nowdate(), 1))
        rule = frappe.get_doc("PM Alert Rule", K.MACHINE_MAINTENANCE)
        alerts.evaluate_rule(rule)
        alert = frappe.db.get_value("PM Alert", {"rule": rule.name, "reference_name": self.digger}, ["state", "recipients"],
                                    as_dict=True)
        self.assertEqual(alert.state, alerts.OPEN)
        self.assertIn(MANAGER, alert.recipients)


class TestLabour(MachineBase):
    def give(self):
        assignments.assign(self.footing, C.RESPONSIBLE, user=LEAD)

    def lines(self):
        return [{"worker": self.workers[0], "task": self.footing, "man_days": 1, "overtime_hours": 2},
                {"worker": self.workers[1], "task": self.footing, "man_days": 0.5}]

    def test_a_crew_day_from_draft_to_confirmed(self):
        self.give()
        blank = as_user(LEAD, labour.sheet, self.project, self.crew)
        self.assertEqual(sorted(line["worker"] for line in blank["lines"]), sorted(self.workers))
        saved = as_user(LEAD, labour.save, self.project, self.crew, nowdate(), self.lines())
        self.assertEqual((saved["status"], saved["total_man_days"]), (K.SHEET_DRAFT, 1.5))
        self.assertNotIn("total_amount", saved)  # the crew lead does not see costs
        as_user(LEAD, labour.submit, saved["name"])
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, labour.confirm, saved["name"])
        self.assertRaises(frappe.ValidationError, as_user, LEAD, labour.save, self.project, self.crew, nowdate(),
                          self.lines())  # submitted: no more changes
        confirmed = as_user(COMMANDER, labour.confirm, saved["name"])
        self.assertEqual(confirmed["status"], K.SHEET_CONFIRMED)
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_labour_cost")), 400_000 + 175_000)
        view = as_user(COMMANDER, labour.overview, self.project)
        self.assertEqual(view["man_days_by_task"][self.footing], 1.5)
        as_user(COMMANDER, labour.send_back, saved["name"], "thiếu người")
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_labour_cost")), 0)

    def test_one_sheet_per_crew_and_day(self):
        self.give()
        first = as_user(LEAD, labour.save, self.project, self.crew, nowdate(), self.lines())
        second = as_user(LEAD, labour.save, self.project, self.crew, nowdate(), self.lines()[:1])
        self.assertEqual((second["name"], second["total_man_days"]), (first["name"], 1))
        recorded = as_user(LEAD, labour.record, self.project, self.crew, add_days(nowdate(), -1), self.lines(),
                           client_uuid=f"att-{self.footing}")
        resent = as_user(LEAD, labour.record, self.project, self.crew, add_days(nowdate(), -1), self.lines(),
                         client_uuid=f"att-{self.footing}")
        self.assertEqual((recorded["name"], resent["status"]), (resent["name"], K.SHEET_SUBMITTED))

    def test_what_a_sheet_refuses(self):
        self.give()
        self.assertRaises(frappe.ValidationError, as_user, LEAD, labour.save, self.project, self.crew, nowdate(),
                          [{"worker": self.stranger, "task": self.footing, "man_days": 1}])  # another crew's worker
        self.assertRaises(frappe.ValidationError, as_user, LEAD, labour.save, self.project, self.crew, nowdate(),
                          [{"worker": self.workers[0], "task": self.footing, "man_days": 3}])
        other = next(t for name, t in self.tasks.items() if t != self.footing and frappe.db.get_value("Task", t, "is_group") == 0)
        self.assertRaises(frappe.PermissionError, as_user, LEAD, labour.save, self.project, self.crew, nowdate(),
                          [{"worker": self.workers[0], "task": other, "man_days": 1}])  # not given to the crew lead
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, labour.save, self.project, self.crew, nowdate(),
                          self.lines())


class TestCosts(MachineBase):
    def test_the_summary_adds_up(self):
        from pm_construction.pm_construction.services import materials

        materials.create_store(self.project)
        materials.receive(self.project, [{"item": materials.catalogue(self.project)[0].name, "qty": 100, "rate": 1_000}])
        item = materials.catalogue(self.project)[0].name
        materials.issue(self.project, [{"task": self.footing, "item": item, "qty": 40}])
        self.bring()
        machines.record_shift(self.project, self.digger, self.footing, nowdate(), 1)
        assignments.assign(self.footing, C.RESPONSIBLE, user=LEAD)
        sheet = labour.record(self.project, self.crew, nowdate(), [{"worker": self.workers[0], "task": self.footing,
                                                                     "man_days": 1}])
        labour.confirm(sheet["name"])
        self.done(self.footing, 10)
        view = as_user(MANAGER, costs.summary, self.project)
        row = next(r for r in view["rows"] if r["name"] == self.footing)
        self.assertEqual((row["material"], row["machine"], row["labour"]), (40_000, RATE, 400_000))
        self.assertEqual(row["actual"], 40_000 + RATE + 400_000)
        unit = frappe.db.get_value("Task", self.footing, "pmc_unit_price")
        self.assertEqual(row["earned"], 10 * unit)
        phase = next(r for r in view["rows"] if r["is_group"] and r["label"].endswith("PHẦN MÓNG"))
        self.assertEqual(phase["actual"], row["actual"])
        self.assertEqual(view["total"]["actual"], row["actual"])
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, costs.summary, self.project)  # no finance.view
