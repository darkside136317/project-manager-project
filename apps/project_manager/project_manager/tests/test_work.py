"""M2: the views over the work — my tasks, Kanban, who does what, a task in full, daily reminders, project screens.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_work
"""

import frappe
from frappe.utils import add_days, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import assignments, progress, projects, reminders, work
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import (
    TAG,
    PMTestCase,
    add_member,
    drop_project,
    drop_user,
    make_project,
    make_task,
    make_user,
)

MANAGER = f"wk.manager.{TAG}@example.com"
ENGINEER = f"wk.engineer.{TAG}@example.com"
LEAD = f"wk.lead.{TAG}@example.com"
USERS = (MANAGER, ENGINEER, LEAD)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class TestWork(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        cls.project = make_project("WK")
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, LEAD, "Tổ trưởng")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.project)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.phase = make_task(self.project, "Phần móng", is_group=1)
        self.late = make_task(self.project, "Đào đất", parent=self.phase, exp_start_date=add_days(nowdate(), -5),
                              exp_end_date=add_days(nowdate(), -1))
        self.soon = make_task(self.project, "Cốt thép", parent=self.phase, exp_start_date=nowdate(),
                              exp_end_date=add_days(nowdate(), 1))
        self.later = make_task(self.project, "Cốp pha", parent=self.phase, exp_start_date=nowdate(),
                               exp_end_date=add_days(nowdate(), 20))
        self.a_late = assignments.assign(self.late, C.ACCOUNTABLE, user=ENGINEER)
        self.a_soon = assignments.assign(self.soon, C.ACCOUNTABLE, user=ENGINEER)
        assignments.assign(self.later, C.RESPONSIBLE, user=LEAD)
        as_user(ENGINEER, assignments.respond, self.a_late, True)

    def test_my_tasks_put_unanswered_work_first(self):
        mine = as_user(ENGINEER, work.my_tasks)
        self.assertEqual([r.name for r in mine["rows"]], [self.soon, self.late])  # waiting for an answer, then late
        self.assertEqual(mine["counts"], {"pending": 1, "late": 1, "soon": 1, "total": 2})
        self.assertEqual(as_user(LEAD, work.my_tasks)["counts"]["total"], 1)

    def test_kanban_shows_leaves_in_the_callers_scope(self):
        board = as_user(MANAGER, work.kanban, self.project)
        self.assertEqual({c.name for c in board["cards"]}, {self.late, self.soon, self.later})
        self.assertTrue(board["can_move"])
        self.assertEqual([c.name for c in as_user(LEAD, work.kanban, self.project)["cards"]], [self.later])
        late_only = as_user(MANAGER, work.kanban, self.project, late=1)
        self.assertEqual([c.name for c in late_only["cards"]], [self.late])
        mine = as_user(MANAGER, work.kanban, self.project, accountable=ENGINEER)
        self.assertEqual({c.name for c in mine["cards"]}, {self.late, self.soon})

    def test_who_does_what(self):
        as_user(ENGINEER, progress.report, self.soon, 30)  # the crew lead never reported
        view = as_user(MANAGER, work.who_does_what, self.project)
        rows = {r.user: r for r in view["rows"]}
        self.assertTrue(rows[ENGINEER].last_report)
        self.assertIsNone(rows[LEAD].last_report)  # their own reports only, not someone else's on their tasks
        self.assertEqual((rows[ENGINEER].accountable, rows[ENGINEER].late, rows[ENGINEER].pending), (2, 1, 1))
        self.assertEqual(rows[LEAD].responsible, 1)
        self.assertEqual(view["unassigned"], 1)  # "Cốp pha" has a crew lead but nobody accountable
        lead_view = as_user(LEAD, work.who_does_what, self.project)
        self.assertEqual([r.user for r in lead_view["rows"]], [LEAD])
        self.assertFalse(lead_view["sees_all"])

    def test_task_detail_says_what_the_caller_may_do(self):
        detail = as_user(ENGINEER, work.task_detail, self.late)
        self.assertEqual(detail["ancestors"][0].name, self.phase)
        self.assertTrue(detail["can"]["update"])
        self.assertFalse(detail["can"]["assign"])
        self.assertTrue(detail["mine"])
        self.assertEqual(detail["task"]["accountable_name"], frappe.utils.get_fullname(ENGINEER))
        self.assertTrue(detail["delay_reasons"])
        self.assertTrue(any(r.activity_type == "Giao việc" for r in detail["timeline"]))
        with self.assertRaises(frappe.PermissionError):
            as_user(LEAD, work.task_detail, self.late)

    def test_daily_reminder_once_a_day(self):
        due = reminders.due_work()
        self.assertEqual(due[ENGINEER], {"late": 1, "soon": 1})
        self.assertNotIn(LEAD, due)  # 20 days away
        frappe.db.set_single_value("PM Settings", "daily_reminders", 1)
        reminders.send_daily()
        reminders.send_daily()
        subject = reminders.message(1, 1)
        self.assertEqual(frappe.db.count("Notification Log", {"for_user": ENGINEER, "subject": subject}), 1)

    def test_project_overview_and_list(self):
        view = as_user(MANAGER, projects.overview, self.project)
        self.assertEqual(view["tasks"]["total"], 3)
        self.assertEqual(view["tasks"]["late"], 1)
        self.assertEqual(view["pending_acceptance"], 2)
        self.assertEqual([p.name for p in view["phases"]], [self.phase])
        self.assertTrue(view["can"]["plan.edit"])
        given = [r for r in view["recent"] if r.task == self.late]
        self.assertTrue(given and given[0].task_label.endswith("Đào đất"))  # an entry says which task it is about
        lead_view = as_user(LEAD, projects.overview, self.project)
        self.assertEqual(lead_view["tasks"]["total"], 1)
        self.assertEqual(lead_view["phases"], [])
        listed = as_user(ENGINEER, projects.list_projects)
        row = next(r for r in listed["rows"] if r.name == self.project)
        self.assertEqual((row["tasks"], row["late"]), (3, 1))
        self.assertFalse(listed["can_create"])

    def test_members(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, projects.add_member, self.project, LEAD, "Kỹ sư")
        member = as_user(MANAGER, projects.add_member, self.project, LEAD, "Kỹ sư")
        listed = as_user(MANAGER, projects.members, self.project)
        self.assertTrue(listed["can_manage"])
        self.assertIn(member["name"], [r.name for r in listed["rows"]])
        as_user(MANAGER, projects.set_member, member["name"], {"is_active": 0})
        self.assertEqual(frappe.db.get_value("PM Project Member", member["name"], "is_active"), 0)
