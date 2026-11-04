"""M2: progress reports — leaf only, late work says why, approval, Kanban moves, idempotent offline sends, history.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_progress
"""

import frappe
from frappe.utils import add_days, flt, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import assignments, progress, tree
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

MANAGER = f"pg.manager.{TAG}@example.com"
ENGINEER = f"pg.engineer.{TAG}@example.com"
REVIEWER = f"pg.reviewer.{TAG}@example.com"
STRANGER = f"pg.stranger.{TAG}@example.com"
USERS = (MANAGER, ENGINEER, REVIEWER, STRANGER)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class TestProgress(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        cls.project = make_project("PG")
        cls.other_project = make_project("PG other")
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, REVIEWER, "Chỉ huy trưởng")
        add_member(cls.other_project, STRANGER, "Kỹ sư")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.project)
        drop_project(cls.other_project)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.group = make_task(self.project, "Phần móng", is_group=1)
        self.task = make_task(self.project, "Cốt thép móng", parent=self.group, exp_start_date=nowdate(),
                              exp_end_date=add_days(nowdate(), 5))
        self.late = make_task(self.project, "Ván khuôn móng", parent=self.group,
                              exp_start_date=add_days(nowdate(), -10), exp_end_date=add_days(nowdate(), -2))

    def test_report_moves_the_status_and_keeps_a_record(self):
        state = as_user(ENGINEER, progress.report, self.task, 40, "Xong 2/5 móng")
        self.assertEqual((state.status, flt(state.progress)), (C.WORKING, 40))
        entry = frappe.get_all("PM Progress Entry", filters={"task": self.task},
                               fields=["progress_before", "progress_after", "reporter", "project", "note"])[0]
        self.assertEqual((flt(entry.progress_before), flt(entry.progress_after)), (0, 40))
        self.assertEqual((entry.reporter, entry.project, entry.note), (ENGINEER, self.project, "Xong 2/5 móng"))
        self.assertTrue(frappe.db.get_value("Task", self.task, "act_start_date"))
        timeline = frappe.get_all("PM Activity", filters={"reference_name": self.task, "activity_type": "Tiến độ"},
                                  pluck="content")
        self.assertTrue(any("0% → 40%" in text for text in timeline))

    def test_finishing_without_a_reviewer_completes(self):
        name = assignments.assign(self.task, C.ACCOUNTABLE, user=ENGINEER)
        state = as_user(ENGINEER, progress.report, self.task, 100)
        self.assertEqual(state.status, C.COMPLETED)
        self.assertEqual(frappe.db.get_value("PM Task Assignment", name, "state"), C.DONE)

    def test_finishing_with_a_reviewer_waits_for_approval(self):
        assignments.assign(self.task, C.REVIEWER, user=REVIEWER)
        self.assertEqual(as_user(ENGINEER, progress.report, self.task, 100).status, C.REVIEW)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, progress.review, self.task, True)
        with self.assertRaises(frappe.ValidationError):
            as_user(REVIEWER, progress.review, self.task, False, "")
        state = as_user(REVIEWER, progress.review, self.task, False, "Thiếu thép đai")
        self.assertEqual((state.status, flt(state.progress)), (C.WORKING, 95))
        as_user(ENGINEER, progress.report, self.task, 100)
        self.assertEqual(as_user(REVIEWER, progress.review, self.task, True).status, C.COMPLETED)

    def test_late_work_says_why(self):
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, progress.report, self.late, 30)
        reason = frappe.get_all("PM Delay Reason", pluck="name", limit=1)[0]
        source = frappe.get_all("PM Delay Source", pluck="name", limit=1)[0]
        as_user(ENGINEER, progress.report, self.late, 30, "", reason, source, "Thiếu ván khuôn")
        task = frappe.db.get_value("Task", self.late, ["pm_delay_reason", "pm_delay_source", "pm_delay_note",
                                                       "pm_is_overdue", "pm_delay_days"], as_dict=True)
        self.assertEqual((task.pm_delay_reason, task.pm_delay_source, task.pm_delay_note),
                         (reason, source, "Thiếu ván khuôn"))
        self.assertEqual((task.pm_is_overdue, task.pm_delay_days), (1, 2))
        # once given, the next report does not ask again
        as_user(ENGINEER, progress.report, self.late, 60)
        entry = frappe.get_all("PM Progress Entry", filters={"task": self.late}, fields=["delay_reason"],
                               order_by="name desc", limit=1)[0]
        self.assertEqual(entry.delay_reason, reason)

    def test_groups_are_computed_not_reported(self):
        with self.assertRaises(frappe.ValidationError):
            progress.report(self.group, 50)

    def test_outsiders_cannot_report(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(STRANGER, progress.report, self.task, 10)

    def test_the_same_send_twice_is_one_report(self):
        uuid = frappe.generate_hash(length=20)
        as_user(ENGINEER, progress.report, self.task, 20, client_uuid=uuid)
        as_user(ENGINEER, progress.report, self.task, 20, client_uuid=uuid)
        self.assertEqual(frappe.db.count("PM Progress Entry", {"task": self.task}), 1)

    def test_kanban_moves(self):
        state = as_user(ENGINEER, progress.move, self.task, C.WORKING)
        self.assertEqual((state.status, flt(state.progress)), (C.WORKING, 1))
        state = as_user(ENGINEER, progress.move, self.task, C.COMPLETED)
        self.assertEqual((state.status, flt(state.progress)), (C.COMPLETED, 100))
        state = as_user(ENGINEER, progress.move, self.task, C.WORKING, "Làm lại")
        self.assertEqual((state.status, flt(state.progress)), (C.WORKING, 95))
        state = as_user(ENGINEER, progress.move, self.task, C.OPEN)
        self.assertEqual((state.status, flt(state.progress)), (C.OPEN, 0))

    def test_deadline_changes_need_a_reason_once_work_is_given(self):
        new_end = add_days(nowdate(), 9)
        as_user(MANAGER, tree.update, self.task, {"exp_end_date": add_days(nowdate(), 7)})  # still planning
        assignments.assign(self.task, C.ACCOUNTABLE, user=ENGINEER)
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, tree.update, self.task, {"exp_end_date": new_end})
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, tree.update, self.task, {"exp_end_date": new_end}, "Mưa")
        as_user(MANAGER, tree.update, self.task, {"exp_end_date": new_end}, "Chờ thép về")
        entries = frappe.get_all("PM Activity", filters={"reference_name": self.task, "activity_type": "Đổi hạn"},
                                 fields=["content", "actor"], order_by="name desc")
        self.assertIn("Chờ thép về", entries[0].content)
        self.assertEqual(entries[0].actor, MANAGER)
        self.assertEqual(len(entries), 2)

    def test_history_lists_the_reports(self):
        as_user(ENGINEER, progress.report, self.task, 10)
        as_user(ENGINEER, progress.report, self.task, 35)
        rows = as_user(ENGINEER, progress.history, self.task)
        self.assertEqual([flt(r.progress_after) for r in rows], [35, 10])
