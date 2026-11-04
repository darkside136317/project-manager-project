"""M2: clear responsibility — one accountable person per task, accept / decline with a reason, revoke, history kept.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_assignments
"""

import frappe

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import assignments
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import (
    TAG,
    PMTestCase,
    add_member,
    drop_project,
    drop_team,
    drop_user,
    make_project,
    make_task,
    make_user,
)

MANAGER = f"as.manager.{TAG}@example.com"
ENGINEER = f"as.engineer.{TAG}@example.com"
ENGINEER2 = f"as.engineer2.{TAG}@example.com"
LEAD = f"as.lead.{TAG}@example.com"
CREW = f"as.crew.{TAG}@example.com"
OUTSIDER = f"as.outsider.{TAG}@example.com"
USERS = (MANAGER, ENGINEER, ENGINEER2, LEAD, CREW, OUTSIDER)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class TestAssignments(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        cls.project = make_project("AS")
        cls.group = make_task(cls.project, "Phần thân", is_group=1)
        cls.task = make_task(cls.project, "Đổ bê tông cột tầng 1", parent=cls.group)
        cls.other = make_task(cls.project, "Xây tường tầng 1", parent=cls.group)
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, ENGINEER2, "Kỹ sư")
        add_member(cls.project, LEAD, "Tổ trưởng")
        add_member(cls.project, CREW, "Tổ trưởng")
        team = frappe.get_doc({"doctype": "PM Team", "team_name": f"Tổ cốp pha {TAG}", "team_type": "Tổ đội",
                               "leader": LEAD, "is_active": 1, "members": [{"user": CREW}]})
        team.insert(ignore_permissions=True)
        cls.team = team.name
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.project)
        drop_team(cls.team)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def live(self, task, raci=None):
        filters = {"task": task, "is_active": 1, "state": ["in", C.LIVE_STATES]}
        if raci:
            filters["raci"] = raci
        return frappe.get_all("PM Task Assignment", filters=filters, fields=["name", "user", "team", "raci", "state"])

    def test_one_accountable_person_at_a_time(self):
        first = as_user(MANAGER, assignments.assign, self.task, C.ACCOUNTABLE, user=ENGINEER)
        self.assertEqual(frappe.db.get_value("Task", self.task, "pm_accountable"), ENGINEER)
        as_user(MANAGER, assignments.assign, self.task, C.ACCOUNTABLE, user=ENGINEER2)
        live = self.live(self.task, C.ACCOUNTABLE)
        self.assertEqual([r.user for r in live], [ENGINEER2])
        previous = frappe.db.get_value("PM Task Assignment", first, ["state", "is_active", "end_reason"], as_dict=True)
        self.assertEqual((previous.state, previous.is_active), (C.REVOKED, 0))
        self.assertIn("Chuyển giao", previous.end_reason)
        self.assertEqual(frappe.db.get_value("Task", self.task, "pm_accountable"), ENGINEER2)
        history = frappe.get_all("PM Activity", filters={"reference_name": self.task, "activity_type": "Giao việc"},
                                 pluck="content")
        self.assertTrue(any("Thu hồi" in text for text in history))

    def test_accountable_and_reviewer_are_people(self):
        with self.assertRaises(frappe.ValidationError):
            assignments.assign(self.task, C.ACCOUNTABLE, team=self.team)
        with self.assertRaises(frappe.ValidationError):
            assignments.assign(self.task, C.REVIEWER, team=self.team)
        assignments.assign(self.task, C.RESPONSIBLE, team=self.team)  # a crew may do the work

    def test_the_same_role_twice_is_refused(self):
        assignments.assign(self.task, C.RESPONSIBLE, user=ENGINEER)
        with self.assertRaises(frappe.ValidationError):
            assignments.assign(self.task, C.RESPONSIBLE, user=ENGINEER)

    def test_only_who_may_assign_does(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, assignments.assign, self.task, C.RESPONSIBLE, user=ENGINEER2)

    def test_nobody_outside_the_project_gets_work(self):
        with self.assertRaises(frappe.ValidationError):
            assignments.assign(self.task, C.ACCOUNTABLE, user=OUTSIDER)

    def test_accept_and_decline(self):
        name = as_user(MANAGER, assignments.assign, self.task, C.RESPONSIBLE, user=ENGINEER)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER2, assignments.respond, name, True)
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, assignments.respond, name, False, "")
        result = as_user(ENGINEER, assignments.respond, name, False, "Đang phụ trách công trình khác")
        self.assertEqual(result["state"], C.DECLINED)
        row = frappe.db.get_value("PM Task Assignment", name, ["is_active", "decline_reason"], as_dict=True)
        self.assertEqual(row.is_active, 0)
        self.assertEqual(row.decline_reason, "Đang phụ trách công trình khác")
        # the assigner hears about it
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": MANAGER, "subject": ["like", "%từ chối%"]}))
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, assignments.respond, name, True)

        again = as_user(MANAGER, assignments.assign, self.task, C.RESPONSIBLE, user=ENGINEER)
        self.assertEqual(as_user(ENGINEER, assignments.respond, again, True)["state"], C.ACCEPTED)

    def test_a_team_member_answers_for_the_team(self):
        name = assignments.assign(self.other, C.RESPONSIBLE, team=self.team)
        self.assertEqual(as_user(CREW, assignments.respond, name, True)["state"], C.ACCEPTED)

    def test_revoke_needs_a_reason_and_keeps_the_row(self):
        name = assignments.assign(self.task, C.CONSULTED, user=ENGINEER2)
        with self.assertRaises(frappe.ValidationError):
            assignments.revoke(name, " ")
        assignments.revoke(name, "Không cần tham vấn nữa")
        self.assertEqual(frappe.db.get_value("PM Task Assignment", name, "state"), C.REVOKED)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("PM Task Assignment", name, ignore_permissions=True)
        self.assertTrue(frappe.db.exists("PM Task Assignment", name))

    def test_assignments_cannot_be_written_through_the_generic_api(self):
        name = assignments.assign(self.task, C.INFORMED, user=ENGINEER2)
        doc = frappe.get_doc("PM Task Assignment", name)
        self.assertTrue(frappe.has_permission("PM Task Assignment", "read", doc=doc, user=ENGINEER2))
        self.assertFalse(frappe.has_permission("PM Task Assignment", "write", doc=doc, user=MANAGER))

    def test_a_crew_lead_sees_only_the_tasks_given_to_their_crew(self):
        def visible():
            return set(frappe.get_list("Task", filters={"project": self.project}, pluck="name", limit_page_length=0))

        self.assertEqual(as_user(CREW, visible), set())
        assignments.assign(self.other, C.RESPONSIBLE, team=self.team)
        policy.clear_cache()
        self.assertEqual(as_user(CREW, visible), {self.other})
        self.assertEqual(as_user(LEAD, visible), {self.other})  # the leader is a member of the team
        self.assertTrue(as_user(CREW, policy.is_assigned, self.other))
        self.assertFalse(as_user(CREW, policy.is_assigned, self.task))

    def test_finishing_the_task_finishes_its_assignments(self):
        name = assignments.assign(self.task, C.RESPONSIBLE, user=ENGINEER)
        assignments.complete_for(self.task)
        self.assertEqual(frappe.db.get_value("PM Task Assignment", name, "state"), C.DONE)
        rows = assignments.of_task(self.task)
        self.assertEqual(rows[0]["who"], frappe.utils.get_fullname(ENGINEER))
        self.assertFalse(rows[0]["can_revoke"])
