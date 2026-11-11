"""M8: materials of a construction site — the plan by the norms, asking, receiving, issuing to work items, giving back,
writing off, moving to another site, the norm against what was used, the over-norm alert, the material cost.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_materials
"""

import frappe
from frappe.utils import flt
from project_manager.project_manager.services import alerts

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import costs, materials
from pm_construction.tests.construction_helpers import COMMANDER, ENGINEER, LEAD, MANAGER, OUTSIDER, as_user
from pm_construction.tests.site_helpers import CEMENT, KEEPER, NORM, SAND, STONE, SiteBase

PRICE = 1_800


class MaterialBase(SiteBase):
    def setUp(self):
        super().setUp()
        materials.plan_from_norms(self.project)
        self.store = as_user(KEEPER, materials.create_store, self.project)

    def stock_up(self, qty=10_000, item=CEMENT, rate=PRICE):
        return as_user(KEEPER, materials.receive, self.project, [{"item": item, "qty": qty, "rate": rate}])

    def ask(self, qty=5_000, item=CEMENT, user=ENGINEER, **kwargs):
        return as_user(user, materials.request, self.project, [{"task": self.footing, "item": item, "qty": qty}], **kwargs)


class TestPlanAndStore(MaterialBase):
    def test_the_plan_follows_the_norm_of_the_work_item(self):
        rows = {r.item: r for r in frappe.get_all("PMC Material Plan", filters={"task": self.footing},
                                                  fields=["item", "planned_qty", "unit_qty", "norm_code"])}
        planned = frappe.db.get_value("Task", self.footing, "pmc_planned_qty")
        self.assertAlmostEqual(rows[CEMENT].planned_qty, round(planned * 350 * 1.01, 3))
        self.assertAlmostEqual(rows[SAND].unit_qty, 0.51)
        self.assertEqual(rows[STONE].norm_code, NORM)
        # a norm turned off: its rows go at the next rebuild
        frappe.db.set_value("PMC Material Norm", NORM, "is_active", 0)
        materials.plan_from_norms(self.project)
        self.assertFalse(frappe.db.exists("PMC Material Plan", {"task": self.footing}))

    def test_one_site_store_per_project(self):
        self.assertEqual(frappe.db.get_value("Warehouse", self.store, "pm_project"), self.project)
        self.assertEqual(as_user(MANAGER, materials.create_store, self.project), self.store)
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, materials.create_store, self.other)

    def test_recomputing_the_plan_needs_the_planner_or_the_store(self):
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, materials.recompute_plan, self.project)
        self.assertGreater(as_user(KEEPER, materials.recompute_plan, self.project), 0)


class TestFlow(MaterialBase):
    def test_ask_receive_issue_give_back(self):
        asked = self.ask(note="đổ móng trục A")
        mr = frappe.get_doc("Material Request", asked["name"])
        self.assertEqual((mr.docstatus, mr.pm_project, mr.items[0].pmc_task, mr.items[0].project),
                         (1, self.project, self.footing, self.project))
        self.stock_up()
        line = mr.items[0].name
        as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 5_000,
                                                         "material_request_item": line}])
        self.assertEqual(frappe.db.get_value("Material Request", mr.name, "status"), "Issued")
        as_user(KEEPER, materials.give_back, self.project, [{"task": self.footing, "item": CEMENT, "qty": 200}])
        row = self.row_of(materials.usage(self.project), self.footing, CEMENT)
        self.assertEqual((row.requested, row.issued, row.returned, row.used), (5_000, 5_000, 200, 4_800))
        self.assertEqual(flt(frappe.db.get_value("Bin", {"warehouse": self.store, "item_code": CEMENT}, "actual_qty")),
                         10_000 - 5_000 + 200)
        # the cost of the work item: what went out less what came back, at the store's price
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_material_cost")), 4_800 * PRICE)
        self.assertRaises(frappe.ValidationError, as_user, KEEPER, materials.give_back, self.project,
                          [{"task": self.footing, "item": CEMENT, "qty": 5_000}])  # more than it got

    def test_who_does_what(self):
        self.assertRaises(frappe.PermissionError, self.ask, user=LEAD)  # a crew lead does not ask for materials
        self.assertRaises(frappe.PermissionError, self.ask, user=OUTSIDER)
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, materials.receive, self.project,
                          [{"item": CEMENT, "qty": 1, "rate": PRICE}])
        self.stock_up()
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, materials.issue, self.project,
                          [{"task": self.footing, "item": CEMENT, "qty": 1}])
        self.assertTrue(as_user(COMMANDER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT,
                                                                            "qty": 1}])["name"])

    def test_the_same_send_twice_is_one(self):
        first = self.ask(client_uuid=f"uuid-{self.footing}")
        again = self.ask(client_uuid=f"uuid-{self.footing}")
        self.assertEqual((again["name"], again["again"]), (first["name"], True))
        self.stock_up()
        sent = as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 10}],
                       client_uuid=f"issue-{self.footing}")
        resent = as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 10}],
                         client_uuid=f"issue-{self.footing}")
        self.assertEqual(sent["name"], resent["name"])
        self.assertEqual(self.row_of(materials.usage(self.project), self.footing, CEMENT).issued, 10)

    def test_not_enough_in_the_store(self):
        self.stock_up(qty=100)
        with self.assertRaises(frappe.ValidationError) as caught:
            as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 5_000}])
        self.assertIn("Không đủ tồn kho", str(caught.exception))

    def test_what_is_refused(self):
        self.assertRaises(frappe.ValidationError, self.ask, qty=0)
        other_task = frappe.get_all("Task", filters={"project": ["!=", self.project], "is_group": 0}, pluck="name", limit=1)
        if other_task:
            self.assertRaises(frappe.ValidationError, as_user, ENGINEER, materials.request, self.project,
                              [{"task": other_task[0], "item": CEMENT, "qty": 1}])
        group = frappe.db.get_value("Task", {"project": self.project, "is_group": 1}, "name")
        self.assertRaises(frappe.ValidationError, as_user, ENGINEER, materials.request, self.project,
                          [{"task": group, "item": CEMENT, "qty": 1}])
        self.assertRaises(frappe.ValidationError, as_user, KEEPER, materials.receive, self.project,
                          [{"item": CEMENT, "qty": 1}])  # a delivery needs its price
        self.assertRaises(frappe.ValidationError, as_user, KEEPER, materials.write_off, self.project,
                          [{"item": CEMENT, "qty": 1}])  # a loss needs its reason

    def test_a_loss_on_a_work_item_counts_in_its_cost(self):
        self.stock_up()
        as_user(KEEPER, materials.write_off, self.project, [{"task": self.footing, "item": CEMENT, "qty": 50}],
                note="bao xi măng bị ướt")
        row = self.row_of(materials.usage(self.project), self.footing, CEMENT)
        self.assertEqual((row.wasted, row.used), (50, 0))
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_material_cost")), 50 * PRICE)

    def test_moving_stock_to_another_site(self):
        self.stock_up()
        self.assertRaises(frappe.PermissionError, as_user, KEEPER, materials.transfer, self.project, self.other,
                          [{"item": CEMENT, "qty": 100}])  # not a keeper of the other site
        target = materials.create_store(self.other)
        materials.transfer(self.project, self.other, [{"item": CEMENT, "qty": 100}])
        self.assertEqual(flt(frappe.db.get_value("Bin", {"warehouse": target, "item_code": CEMENT}, "actual_qty")), 100)

    def test_a_desk_stock_entry_on_a_work_item_moves_its_cost(self):
        self.stock_up()
        doc = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Issue", "company":
                              materials.company_of(self.project), "project": self.project, "pmc_kind": K.ISSUE,
                              "items": [{"item_code": CEMENT, "qty": 10, "s_warehouse": self.store, "project": self.project,
                                         "pmc_task": self.footing}]})
        doc.insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_material_cost")), 10 * PRICE)
        doc.cancel()
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_material_cost")), 0)


class TestNorm(MaterialBase):
    def test_used_against_the_norm_of_the_work_done(self):
        self.stock_up(qty=20_000)
        as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 4_800}])
        self.done(self.footing, 10)  # 10 m3 of 38.5 done: the norm is 10 x 353.5 = 3,535 kg
        row = self.row_of(materials.usage(self.project), self.footing, CEMENT)
        self.assertAlmostEqual(row.norm_done, 3_535)
        # not finished: the cement waits at the work face, issued ahead of the work, not over the norm
        self.assertEqual((row.over_norm, row.ahead, row.finished), (False, True, False))
        self.assertFalse([h for h in materials.over_norm(frappe._dict(), None) if h.task == self.footing])
        # finished: 38.5 m3 need 13,609.75 kg; 14,800 used is more than 5 % over
        as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 10_000}])
        self.done(self.footing, 38.5)
        row = self.row_of(materials.usage(self.project), self.footing, CEMENT)
        self.assertEqual((row.over_norm, row.ahead, row.finished), (True, False, True))
        hits = [h for h in materials.over_norm(frappe._dict(), None) if h.task == self.footing]
        self.assertEqual([h.episode for h in hits], [CEMENT])
        rule = frappe.get_doc("PM Alert Rule", K.OVER_NORM)
        alerts.evaluate_rule(rule)
        alert = frappe.db.get_value("PM Alert", {"rule": rule.name, "reference_name": self.footing, "episode": CEMENT},
                                    ["state", "recipients"], as_dict=True)
        self.assertEqual(alert.state, alerts.OPEN)
        self.assertIn(MANAGER, alert.recipients)
        as_user(KEEPER, materials.give_back, self.project, [{"task": self.footing, "item": CEMENT, "qty": 600}])
        self.assertFalse(self.row_of(materials.usage(self.project), self.footing, CEMENT).over_norm)  # 14,200: within 5 %
        alerts.evaluate_rule(rule)
        self.assertEqual(frappe.db.get_value("PM Alert", {"rule": rule.name, "reference_name": self.footing}, "state"),
                         alerts.OVER)

    def test_more_than_the_whole_design_needs_is_over_at_once(self):
        self.stock_up(qty=20_000)
        as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 15_000}])
        row = self.row_of(materials.usage(self.project), self.footing, CEMENT)  # nothing done yet, 13,609.75 for it all
        self.assertEqual((row.over_norm, row.finished), (True, False))

    def test_what_each_role_reads(self):
        self.stock_up()
        as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 100}])
        seen = as_user(ENGINEER, materials.overview, self.project)
        self.assertEqual((seen["store"], seen["can"]["request"], seen["can"]["manage"], seen["can"]["finance"]),
                         (self.store, True, False, False))
        self.assertNotIn("value", self.row_of(seen["rows"], self.footing, CEMENT))
        self.assertNotIn("rate", seen["stock"][0])
        boss = as_user(MANAGER, materials.overview, self.project)
        self.assertEqual(self.row_of(boss["rows"], self.footing, CEMENT).value, 100 * PRICE)
        self.assertTrue(any(i.name == CEMENT for i in boss["items"]))
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, materials.overview, self.project)

    def test_the_cost_of_the_whole_project_is_refreshed_from_the_ledgers(self):
        self.stock_up()
        as_user(KEEPER, materials.issue, self.project, [{"task": self.footing, "item": CEMENT, "qty": 100}])
        frappe.db.set_value("Task", self.footing, "pmc_material_cost", 1)  # drifted
        self.assertEqual(costs.refresh(self.project), 1)
        self.assertEqual(flt(frappe.db.get_value("Task", self.footing, "pmc_actual_cost")), 100 * PRICE)
