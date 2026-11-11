"""M9 of the construction layer: the productivity of the crews (diary quantities shared by confirmed man-days), a
machine booked by two projects, the cost and norm columns of the portfolio.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_people_layer
"""

import frappe
from frappe.utils import add_days, nowdate
from project_manager.project_manager.services import assignments, performance, workload
from project_manager.project_manager import constants as C

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import diary, labour, machines, people
from pm_construction.tests.construction_helpers import COMMANDER, ENGINEER, LEAD, MANAGER, OUTSIDER, as_user
from pm_construction.tests.test_machines_labour import MachineBase


class TestCrewProductivity(MachineBase):
    def test_quantities_by_the_man_days_of_each_crew(self):
        assignments.assign(self.footing, C.RESPONSIBLE, team=self.crew)
        day = nowdate()
        as_user(ENGINEER, diary.record, self.project, day, {"weather": "Nắng", "workers": 6},
                [{"task": self.footing, "qty": 6}])
        mine = as_user(LEAD, labour.record, self.project, self.crew, day,
                       [{"worker": self.workers[0], "task": self.footing, "man_days": 1},
                        {"worker": self.workers[1], "task": self.footing, "man_days": 1}])
        theirs = labour.record(self.project, self.other_crew, day,
                               [{"worker": self.stranger, "task": self.footing, "man_days": 1}])
        rows = people.productivity(day, day)
        self.assertEqual(rows, [])  # nothing confirmed yet
        for sheet in (mine, theirs):
            as_user(COMMANDER, labour.confirm, sheet["name"])
        rows = {r["team"]: r for r in people.productivity(day, day)}
        self.assertAlmostEqual(rows[self.crew]["qty"], 4)  # 2 of the 3 man-days
        self.assertAlmostEqual(rows[self.other_crew]["qty"], 2)
        self.assertEqual(rows[self.crew]["uom"], "m3")
        crews = {c["team"]: c for c in performance.overview(start=day, end=day)["crews"]}
        self.assertEqual(crews[self.crew]["per_man_day"], 2.0)
        led = as_user(LEAD, performance.overview, start=day, end=day)["crews"]
        self.assertEqual([c["team"] for c in led], [self.crew])  # the leader sees their crew only
        self.assertEqual(as_user(OUTSIDER, performance.overview, start=day, end=day)["crews"], [])


class TestMachineBookings(MachineBase):
    def test_a_machine_booked_by_two_projects(self):
        first, last = add_days(nowdate(), 1), add_days(nowdate(), 5)
        booked = as_user(MANAGER, machines.book, self.project, self.digger, first, last, self.footing, "đào móng")
        self.assertEqual(booked["clashes"], [])
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, machines.book, self.project, self.digger, first, last)
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, machines.book, self.project, self.digger, first, last)
        other = machines.book(self.other, self.digger, add_days(nowdate(), 4), add_days(nowdate(), 9))
        self.assertEqual([c["project"] for c in other["clashes"]], [self.project])
        found = people.machine_conflicts(nowdate(), add_days(nowdate(), 13))
        mine = [c for c in found if c["machine"] == self.digger]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["from"], mine[0]["to"]), (str(add_days(nowdate(), 4)), str(last)))
        view = as_user(MANAGER, workload.overview, nowdate(), 2)
        shown = next(c for c in view["conflicts"] if c.get("machine") == self.digger)
        self.assertEqual(set(shown["projects"]), {self.project, workload.OTHER})  # not a member of the other project
        listed = as_user(MANAGER, machines.overview, self.project)["bookings"]
        self.assertEqual(listed[0]["clashes"][0]["project_name"], "Dự án khác")
        as_user(MANAGER, machines.cancel_booking, booked["name"])
        self.assertFalse([c for c in people.machine_conflicts(nowdate(), add_days(nowdate(), 13))
                          if c["machine"] == self.digger])

    def tearDown(self):
        frappe.db.delete("PMC Machine Booking", {"machine": ["in", [self.digger, self.crane]]})
        super().tearDown()


class TestPortfolioColumns(MachineBase):
    def test_cost_and_norm(self):
        frappe.db.set_value("Task", self.footing, {"pmc_done_qty": 10, "pmc_actual_cost": 0})
        price = frappe.db.get_value("Task", self.footing, "pmc_unit_price")
        frappe.db.set_value("Task", self.footing, "pmc_actual_cost", price * 10 * 1.2)  # 120 % of the work done
        shown = as_user(MANAGER, people.portfolio_columns, [self.project])[self.project]
        self.assertAlmostEqual(shown["cost_ratio"]["value"], 1.2)
        self.assertEqual(shown["cost_ratio"]["tone"], "bad")
        hidden = as_user(COMMANDER, people.portfolio_columns, [self.project]).get(self.project, {})
        self.assertNotIn("cost_ratio", hidden)  # no finance.view
        rule = frappe.db.get_value("PM Alert Rule", {"rule_type": K.OVER_NORM}, "name")
        frappe.get_doc({"doctype": "PM Alert", "rule": rule, "rule_type": K.OVER_NORM, "project": self.project,
                        "task": self.footing, "reference_doctype": "Task", "reference_name": self.footing, "episode": "x",
                        "state": "Đang mở", "level": 0, "message": "thử"}).insert(ignore_permissions=True)
        self.assertEqual(people.portfolio_columns([self.project])[self.project]["over_norm"]["value"], 1)
