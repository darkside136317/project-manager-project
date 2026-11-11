"""M9: workload against capacity, conflicts between projects, the overload alert, performance and who sees whose.

The week under test starts on Monday 2030-01-07 ("today"); the company's calendar decides the working days, so the
expected capacities are read from it.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_people
"""

from datetime import timedelta

import frappe
from frappe.utils import getdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import alerts, assignments, performance, portfolio, workload
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import TAG, PMTestCase, add_member, drop_project, drop_user, make_project, make_task, make_user

ENGINEER = f"pp.engineer.{TAG}@example.com"
LEAD = f"pp.lead.{TAG}@example.com"
MANAGER = f"pp.manager.{TAG}@example.com"
OUTSIDER = f"pp.outsider.{TAG}@example.com"
DIRECTOR = f"pp.director.{TAG}@example.com"
USERS = (ENGINEER, LEAD, MANAGER, OUTSIDER, DIRECTOR)
MONDAY = getdate("2030-01-07")


def day(offset: int) -> str:
    return (MONDAY + timedelta(days=offset)).isoformat()


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


def working(first, last) -> int:
    calendar = workload.company_calendar()
    return sum(1 for k in range((getdate(last) - getdate(first)).days + 1)
               if calendar.is_working(getdate(first) + timedelta(days=k)))


class PeopleBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in (ENGINEER, LEAD, MANAGER, OUTSIDER):
            make_user(user, [C.STAFF_ROLE])
        make_user(DIRECTOR, [C.DIRECTOR_ROLE])
        cls.p1, cls.p2 = make_project("PP 1"), make_project("PP 2")
        for project in (cls.p1, cls.p2):
            frappe.db.set_value("Project", project, {"pm_state": "Đang thực hiện", "pm_manager": MANAGER})
        add_member(cls.p1, MANAGER, "Quản lý dự án")
        add_member(cls.p1, ENGINEER, "Kỹ sư")
        add_member(cls.p2, ENGINEER, "Kỹ sư")
        add_member(cls.p1, LEAD, "Tổ trưởng")
        cls.team = frappe.get_doc({"doctype": "PM Team", "team_name": f"Tổ thử {TAG}", "team_type": "Tổ đội", "leader": LEAD,
                                   "is_active": 1, "members": [{"user": ENGINEER}]}).insert(ignore_permissions=True).name
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("PM Resource Capacity", {"user": ["in", USERS]})
        frappe.db.delete("PM Performance Snapshot", {"project": ["in", [cls.p1, cls.p2]]})
        frappe.db.delete("PM Performance Snapshot", {"subject": ["in", [*USERS, cls.p1, cls.p2]]})
        frappe.db.delete("PM Team Member", {"parent": cls.team})
        frappe.db.delete("PM Team", {"name": cls.team})
        for project in (cls.p1, cls.p2):
            drop_project(project)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def task(self, project, subject, first, last, doing=(), accountable=None, **values):
        name = make_task(project, f"{subject} {TAG}", exp_start_date=day(first), exp_end_date=day(last), **values)
        if accountable:
            assignments.assign(name, C.ACCOUNTABLE, user=accountable)
        for user in doing:
            assignments.assign(name, C.RESPONSIBLE, user=user)
        return name

    def overview(self, user=None, **kwargs):
        call = (lambda: workload.overview(MONDAY, 1, today=MONDAY, **kwargs))
        return as_user(user, call) if user else call()

    def row(self, view, user):
        return next((r for r in view["rows"] if r["user"] == user), None)


class TestWorkload(PeopleBase):
    def test_demand_against_capacity(self):
        self.task(self.p1, "Đổ bê tông", 0, 4, doing=[ENGINEER])  # Mon–Fri, all day
        self.task(self.p1, "Giám sát", 0, 2, doing=[ENGINEER], pm_load_pct=50)  # half of Mon–Wed
        self.task(self.p2, "Lắp dựng", 0, 5, doing=[ENGINEER])  # Mon–Sat
        week = self.row(self.overview(), ENGINEER)["weeks"][0]
        expected = working(day(0), day(4)) + 0.5 * working(day(0), day(2)) + working(day(0), day(5))
        self.assertAlmostEqual(week["demand"], expected)
        self.assertAlmostEqual(week["capacity"], working(day(0), day(6)))
        self.assertEqual(week["level"], "Quá tải")
        self.assertEqual(set(week["projects"]), {self.p1, self.p2})

    def test_leave_lowers_capacity(self):
        self.task(self.p1, "Cốp pha", 0, 4, doing=[ENGINEER])
        workload.save_capacity(ENGINEER, day(3), day(4), 0, "Nghỉ phép")
        week = self.row(self.overview(), ENGINEER)["weeks"][0]
        leave = working(day(3), day(4))
        self.assertAlmostEqual(week["capacity"], working(day(0), day(6)) - leave)
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, workload.save_capacity, ENGINEER, day(0), day(1), 0)

    def test_who_carries_the_load(self):
        shared = self.task(self.p1, "Xây tường", 0, 0, doing=[ENGINEER, LEAD])
        alone = self.task(self.p1, "Nghiệm thu", 1, 1, accountable=MANAGER)  # nobody doing it: the accountable
        view = self.overview()
        if working(day(0), day(0)):
            self.assertAlmostEqual(self.row(view, ENGINEER)["weeks"][0]["demand"], 0.5)
            self.assertAlmostEqual(self.row(view, LEAD)["weeks"][0]["demand"], 0.5)
        if working(day(1), day(1)):
            self.assertAlmostEqual(self.row(view, MANAGER)["weeks"][0]["demand"], 1)
        self.assertTrue(shared and alone)
        own = self.overview(ENGINEER)  # seen by the engineer alone: still half of it, and nobody else's row
        self.assertEqual([r["user"] for r in own["rows"]], [ENGINEER])
        if working(day(0), day(0)):
            self.assertAlmostEqual(own["rows"][0]["weeks"][0]["demand"], 0.5)
            self.assertAlmostEqual(as_user(ENGINEER, workload.cell, ENGINEER, MONDAY)["tasks"][0]["days"], 0.5)

    def test_late_work_lands_on_the_coming_days(self):
        late = self.task(self.p1, "Chống thấm", -10, -7, doing=[ENGINEER])  # ended last week, half done
        frappe.db.set_value("Task", late, {"status": C.WORKING, "progress": 50})
        week = self.row(self.overview(), ENGINEER)["weeks"][0]
        calendar = workload.company_calendar()
        length = calendar.count(day(-10), day(-7))
        self.assertAlmostEqual(week["demand"], max(1, -(-length // 2)))

    def test_conflicts_and_the_alert(self):
        self.task(self.p1, "Cốt thép", 0, 5, doing=[ENGINEER])
        self.task(self.p2, "Ván khuôn", 0, 5, doing=[ENGINEER])
        view = self.overview()
        conflict = next(c for c in view["conflicts"] if c.get("user") == ENGINEER)
        self.assertEqual(set(conflict["projects"]), {self.p1, self.p2})
        rule = frappe.get_doc("PM Alert Rule", alerts.OVERLOADED)
        hits = [h for h in workload.overloaded(rule, MONDAY) if h.reference_name == ENGINEER]
        self.assertEqual([h.episode for h in hits], [MONDAY.isoformat()])
        self.assertIn(MANAGER, hits[0].direct)
        alerts.evaluate_rule(rule, MONDAY)
        alert = frappe.db.get_value("PM Alert", {"rule": rule.name, "reference_name": ENGINEER}, ["state", "recipients"],
                                    as_dict=True)
        self.assertEqual(alert.state, alerts.OPEN)
        self.assertIn(ENGINEER, alert.recipients)

    def test_who_sees_whose_workload(self):
        self.task(self.p1, "Trát", 0, 2, doing=[ENGINEER])
        self.task(self.p2, "Sơn", 0, 2, doing=[ENGINEER])
        mine = self.overview(OUTSIDER)
        self.assertIsNone(self.row(mine, ENGINEER))
        boss = self.row(self.overview(MANAGER), ENGINEER)["weeks"][0]["projects"]
        self.assertEqual(set(boss), {self.p1, workload.OTHER})  # P2 is not theirs to name
        leader = self.row(self.overview(LEAD), ENGINEER)["weeks"][0]["projects"]
        self.assertEqual(set(leader), {self.p1, workload.OTHER})  # their crew member, within what they read
        everything = self.row(self.overview(DIRECTOR), ENGINEER)["weeks"][0]["projects"]
        self.assertEqual(set(everything), {self.p1, self.p2})
        cell = as_user(MANAGER, workload.cell, ENGINEER, MONDAY)
        self.assertEqual({t["project"] for t in cell["tasks"]}, {self.p1})
        self.assertGreater(cell["other"], 0)
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, workload.cell, ENGINEER, MONDAY)


class TestPerformance(PeopleBase):
    def finished(self, project, subject, planned_end, real_end):
        name = self.task(project, subject, planned_end - 3, planned_end, doing=[ENGINEER])
        frappe.db.set_value("Task", name, {"status": C.COMPLETED, "progress": 100, "act_end_date": day(real_end)})
        return name

    def test_figures_of_a_person(self):
        self.finished(self.p1, "Móng", 2, 1)  # early
        self.finished(self.p1, "Cột", 2, 4)  # two days late
        self.finished(self.p2, "Dầm", 3, 3)  # on the day
        self.task(self.p1, "Sàn", -5, -1, doing=[ENGINEER])  # open and late
        view = performance.overview(start=day(0), end=day(6))
        row = next(r for r in view["people"] if r["user"] == ENGINEER)
        self.assertEqual((row["done"], row["on_time"], row["late_done"], row["open_late"], row["delay_days"]),
                         (3, 2, 1, 1, 2))
        self.assertAlmostEqual(row["on_time_rate"], round(2 / 3, 3))
        self.assertEqual(row["avg_delay"], 2.0)

    def test_who_sees_whose_performance(self):
        self.finished(self.p1, "Móng", 2, 1)
        self.finished(self.p2, "Dầm", 3, 3)
        own = as_user(ENGINEER, performance.overview, start=day(0), end=day(6))
        self.assertEqual([r["user"] for r in own["people"]], [ENGINEER])  # themselves, in both projects
        self.assertEqual(own["people"][0]["done"], 2)
        boss = as_user(MANAGER, performance.overview, start=day(0), end=day(6))
        self.assertEqual(next(r for r in boss["people"] if r["user"] == ENGINEER)["done"], 1)  # only P1
        self.assertEqual(as_user(OUTSIDER, performance.overview, start=day(0), end=day(6))["people"], [])
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, performance.person, ENGINEER, None, day(0), day(6))
        detail = as_user(DIRECTOR, performance.person, ENGINEER, None, day(0), day(6))
        self.assertEqual({p["project"] for p in detail["projects"]}, {self.p1, self.p2})
        self.assertEqual(as_user(LEAD, performance.person, ENGINEER, None, day(0), day(6))["total"]["done"], 1)

    def test_the_week_is_kept_and_read_back(self):
        self.finished(self.p1, "Móng", 2, 1)
        self.task(self.p1, "Sàn", -5, -1, doing=[ENGINEER])
        performance.snapshot_week(MONDAY)
        kept = frappe.db.get_value("PM Performance Snapshot", {"week_start": MONDAY, "kind": "Người", "subject": ENGINEER,
                                                               "project": self.p1}, ["tasks_done", "open_late"], as_dict=True)
        self.assertEqual((kept.tasks_done, kept.open_late), (1, 1))
        self.assertTrue(frappe.db.exists("PM Performance Snapshot", {"week_start": MONDAY, "kind": "Dự án",
                                                                     "subject": self.p1}))
        performance.snapshot_week(MONDAY)  # again: the same rows, updated
        self.assertEqual(frappe.db.count("PM Performance Snapshot", {"week_start": MONDAY, "subject": ENGINEER}), 1)


class TestPortfolio(PeopleBase):
    def test_v2_columns(self):
        self.task(self.p1, "Cốt thép", 0, 5, doing=[ENGINEER])
        self.task(self.p2, "Ván khuôn", 0, 5, doing=[ENGINEER])
        with _today(MONDAY):
            view = portfolio.portfolio()
        row = next(r for r in view["rows"] if r.name == self.p1)
        self.assertIn("on_time_rate", row)
        self.assertEqual(row.overloaded, 1)  # the engineer, by both projects
        self.assertIsInstance(row.trend, list)
        self.assertIsInstance(row.extra, dict)


class _today:
    """Freeze "today" for the services that read nowdate()."""

    def __init__(self, value):
        self.value = getdate(value)

    def __enter__(self):
        from unittest.mock import patch

        self.patches = [patch("project_manager.project_manager.services.portfolio.nowdate", return_value=str(self.value)),
                        patch("project_manager.project_manager.services.workload.nowdate", return_value=str(self.value))]
        for item in self.patches:
            item.start()
        return self

    def __exit__(self, *args):
        for item in self.patches:
            item.stop()
