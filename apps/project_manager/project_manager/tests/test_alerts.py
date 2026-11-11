"""M7: health (Xanh / Vàng / Đỏ), alerts with escalation and quiet hours, phase gates, digests.

Work dates are in January 2030 on a calendar of the test's own where every day is a working day; "today" is passed in.
Alerts open "now" (the real clock), so escalation is driven by `now` = now + N days.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_alerts
"""

import json
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import alerts, assignments, digest, phases, risk, rollup, schedule
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

MANAGER = f"al.manager.{TAG}@example.com"
CHIEF = f"al.chief.{TAG}@example.com"
ENGINEER = f"al.engineer.{TAG}@example.com"
OUTSIDER = f"al.outsider.{TAG}@example.com"
USERS = (MANAGER, CHIEF, ENGINEER, OUTSIDER)
HOLIDAYS = f"Lich canh bao {TAG}"
GATE_PATH = "project_manager.tests.test_alerts.missing_acceptance"
LIMITS = frappe._dict(red_days=3, stalled_days=5, hold_days=3)


def day(number: int) -> str:
    return f"2030-01-{number:02d}"


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


def missing_acceptance(phase):
    """A layer's gate check, as the construction layer has one."""
    return ["chưa nghiệm thu giai đoạn"] if frappe.flags.pm_test_block_gate else []


def notices(user, text, doctype=None) -> int:
    filters = {"for_user": user, "subject": ["like", f"%{text}%"]}
    if doctype:
        filters["document_type"] = doctype
    return frappe.db.count("Notification Log", filters)


def alert_notices(user, text) -> int:
    """Notices of alerts only (giving the task told the assignee too)."""
    return notices(user, text, "PM Alert")


class AlertBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": HOLIDAYS, "from_date": "2030-01-01",
                        "to_date": "2030-12-31",
                        "holidays": [{"holiday_date": "2030-12-25", "description": "Lễ"}]}).insert(ignore_permissions=True)
        cls.project = make_project("AL")
        frappe.db.set_value("Project", cls.project, {"pm_holiday_list": HOLIDAYS, "pm_manager": MANAGER,
                                                     "pm_state": "Đang thực hiện", "expected_start_date": day(1),
                                                     "expected_end_date": day(12)})
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, CHIEF, "Chỉ huy trưởng")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for project in frappe.get_all("Project", filters={"project_name": ["like", f"%{TAG}%"]}, pluck="name"):
            drop_project(project)
        frappe.delete_doc("Holiday List", HOLIDAYS, force=True, ignore_permissions=True, ignore_missing=True)
        for user in USERS:
            frappe.delete_doc("PM Notification Preference", user, force=True, ignore_permissions=True, ignore_missing=True)
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()

    def setUp(self):
        super().setUp()
        frappe.flags.pm_test_block_gate = False

    def leaf(self, subject, start, end, accountable=ENGINEER, parent=None, **values):
        name = make_task(self.project, subject, parent=parent, exp_start_date=day(start), exp_end_date=day(end), **values)
        if accountable:
            assignments.assign(name, C.ACCOUNTABLE, user=accountable)
        return name

    def rule(self, name):
        return frappe.get_doc("PM Alert Rule", name)

    def alert_of(self, rule, task, **filters):
        return frappe.db.get_value("PM Alert", {"rule": rule, "reference_name": task, **filters}, alerts.FIELDS,
                                   as_dict=True, order_by="name desc")


# --- health ----------------------------------------------------------------------------------------------------------------

class TestHealthRules(PMTestCase):
    def test_classify(self):
        self.assertEqual(risk.classify(0, 10, None, False, False, LIMITS)[0], risk.GREEN)
        self.assertEqual(risk.classify(2, 10, None, False, False, LIMITS)[0], risk.YELLOW)
        self.assertEqual(risk.classify(4, 10, None, False, False, LIMITS)[0], risk.RED)
        self.assertEqual(risk.classify(5, 60, None, False, False, LIMITS)[0], risk.YELLOW)  # 10 % of 60 days is 6
        self.assertEqual(risk.classify(1, 10, None, True, False, LIMITS)[0], risk.RED)  # critical: any slip
        self.assertEqual(risk.classify(0, 10, 0.9, False, False, LIMITS)[0], risk.YELLOW)
        self.assertEqual(risk.classify(0, 10, 0.7, False, False, LIMITS)[0], risk.RED)
        level, reasons = risk.classify(0, 10, None, False, True, LIMITS)
        self.assertEqual(level, risk.YELLOW)
        self.assertIn("không cập nhật tiến độ", reasons)

    def test_worse_at_once_better_after_it_holds(self):
        self.assertEqual(risk.settle(None, None, None, risk.YELLOW, day(1), 3), (risk.YELLOW, None, None))
        self.assertEqual(risk.settle(risk.GREEN, None, None, risk.RED, day(1), 3), (risk.RED, None, None))
        shown, candidate, since = risk.settle(risk.RED, None, None, risk.GREEN, day(1), 3)
        self.assertEqual((shown, candidate, str(since)), (risk.RED, risk.GREEN, day(1)))
        self.assertEqual(risk.settle(risk.RED, risk.GREEN, day(1), risk.GREEN, day(2), 3)[0], risk.RED)
        self.assertEqual(risk.settle(risk.RED, risk.GREEN, day(1), risk.GREEN, day(3), 3), (risk.GREEN, None, None))
        # a different better reading starts counting again
        self.assertEqual(risk.settle(risk.RED, risk.GREEN, day(1), risk.YELLOW, day(3), 3)[1:], (risk.YELLOW, frappe.utils.getdate(day(3))))


class TestHealth(AlertBase):
    def test_a_task_far_behind_turns_red_and_so_does_the_project(self):
        a = self.leaf("Móng", 7, 9)
        schedule.refresh(self.project, today=day(2))
        self.assertEqual(frappe.db.get_value("Task", a, "pm_health"), risk.GREEN)
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_health"), risk.GREEN)
        frappe.db.set_value("Task", a, {"status": C.WORKING, "progress": 10, "act_start_date": day(7),
                                        "pm_last_progress_on": day(7)})
        schedule.refresh(self.project, today=day(14))
        task = frappe.db.get_value("Task", a, ["pm_health", "pm_health_reason", "pm_forecast_slip"], as_dict=True)
        self.assertEqual(task.pm_health, risk.RED)
        self.assertGreater(task.pm_forecast_slip, 3)
        self.assertIn("dự báo trễ", task.pm_health_reason)
        project = frappe.db.get_value("Project", self.project, ["pm_health", "pm_health_reason"], as_dict=True)
        self.assertEqual(project.pm_health, risk.RED)
        # worse: said in the project's history and to its manager (rule "Sức khỏe dự án xấu đi")
        self.assertTrue(frappe.db.exists("PM Activity", {"reference_name": self.project, "content": ["like", "%Xanh → Đỏ%"]}))
        alert = frappe.db.get_value("PM Alert", {"reference_doctype": "Project", "reference_name": self.project,
                                                 "state": alerts.OPEN}, ["rule_type", "recipients"], as_dict=True)
        self.assertEqual(alert.rule_type, alerts.HEALTH)
        self.assertIn(MANAGER, json.loads(alert.recipients))

    def test_better_shows_once_it_held(self):
        a = self.leaf("Thân", 7, 9)
        frappe.db.set_value("Task", a, {"status": C.WORKING, "progress": 10, "act_start_date": day(7),
                                        "pm_last_progress_on": day(7)})
        schedule.refresh(self.project, today=day(14))
        self.assertEqual(frappe.db.get_value("Task", a, "pm_health"), risk.RED)
        frappe.db.set_value("Task", a, {"status": C.COMPLETED, "progress": 100, "act_end_date": day(14)})
        schedule.refresh(self.project, today=day(14))
        self.assertEqual(frappe.db.get_value("Task", a, ["pm_health", "pm_health_candidate"]), (risk.RED, risk.GREEN))
        schedule.refresh(self.project, today=day(15))
        self.assertEqual(frappe.db.get_value("Task", a, "pm_health"), risk.RED)
        schedule.refresh(self.project, today=day(16))
        self.assertEqual(frappe.db.get_value("Task", a, ["pm_health", "pm_health_candidate"]), (risk.GREEN, None))

    def test_a_stalled_task_is_yellow(self):
        a = self.leaf("Xây tường", 1, 20)
        frappe.db.set_value("Task", a, {"status": C.WORKING, "progress": 40, "act_start_date": day(1),
                                        "pm_last_progress_on": day(2)})
        schedule.refresh(self.project, today=day(9))
        task = frappe.db.get_value("Task", a, ["pm_stalled", "pm_health", "pm_health_reason"], as_dict=True)
        self.assertEqual(task.pm_stalled, 1)
        self.assertNotEqual(task.pm_health, risk.GREEN)
        self.assertIn("không cập nhật tiến độ", task.pm_health_reason)

    def test_the_snapshot_keeps_the_health(self):
        self.leaf("Mái", 7, 9)
        schedule.refresh(self.project, today=day(2))
        rollup.take_snapshots(day(2))
        self.assertEqual(frappe.db.get_value("PM Snapshot", {"project": self.project, "task": ["is", "not set"],
                                                             "snapshot_date": day(2)}, "health"), risk.GREEN)


# --- alerts ----------------------------------------------------------------------------------------------------------------

class TestAlerts(AlertBase):
    def test_once_per_episode_and_closed_when_it_is_over(self):
        late = self.leaf("Đổ bê tông", 1, 5)
        rule = self.rule("Quá hạn")
        result = alerts.evaluate_rule(rule, day(7))
        self.assertGreaterEqual(result["opened"], 1)
        alert = self.alert_of(rule.name, late)
        self.assertEqual((alert.state, alert.level, alert.episode), (alerts.OPEN, 0, day(5)))
        self.assertEqual(json.loads(alert.recipients), [ENGINEER])
        self.assertEqual(alert_notices(ENGINEER, "Đổ bê tông"), 1)
        alerts.evaluate_rule(rule, day(8))  # still late: the same alert, nobody told twice
        self.assertEqual(frappe.db.count("PM Alert", {"rule": rule.name, "reference_name": late}), 1)
        self.assertEqual(alert_notices(ENGINEER, "Đổ bê tông"), 1)
        # a new due date is a new episode: the old alert is over, a new one opens
        frappe.db.set_value("Task", late, "exp_end_date", day(6))
        alerts.evaluate_rule(rule, day(8))
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "state"), alerts.OVER)
        self.assertEqual(self.alert_of(rule.name, late, state=alerts.OPEN).episode, day(6))
        frappe.db.set_value("Task", late, {"status": C.COMPLETED, "progress": 100})
        alerts.evaluate_rule(rule, day(9))
        self.assertFalse(frappe.db.exists("PM Alert", {"rule": rule.name, "reference_name": late,
                                                       "state": ["in", [alerts.OPEN, alerts.ACKED]]}))

    def test_back_in_the_same_episode_it_opens_again(self):
        late = self.leaf("Xây bậc", 1, 5)
        rule = self.rule("Quá hạn")
        alerts.evaluate_rule(rule, day(7))
        frappe.db.set_value("Task", late, {"status": C.COMPLETED, "progress": 100})
        alerts.evaluate_rule(rule, day(8))
        alert = self.alert_of(rule.name, late)
        self.assertEqual(alert.state, alerts.OVER)
        frappe.db.set_value("Task", late, {"status": C.WORKING, "progress": 60})  # reopened: still late, same due date
        self.assertEqual(alerts.evaluate_rule(rule, day(9))["opened"] >= 1, True)
        again = self.alert_of(rule.name, late)
        self.assertEqual((again.name, again.state, again.level), (alert.name, alerts.OPEN, 0))
        self.assertEqual(frappe.db.count("PM Alert", {"rule": rule.name, "reference_name": late}), 1)

    def test_many_at_once_make_one_notice(self):
        tasks = [self.leaf(f"Hạng mục gộp {n}", 1, 5) for n in range(alerts.GROUP_AFTER + 2)]
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        self.assertEqual(alert_notices(ENGINEER, "Hạng mục gộp"), 0)
        self.assertEqual(notices(ENGINEER, f"{len(tasks)} cảnh báo mới: Quá hạn {len(tasks)}"), 1)
        for task in tasks:  # each alert still knows who was told
            self.assertEqual(json.loads(self.alert_of("Quá hạn", task).recipients), [ENGINEER])

    def test_due_soon(self):
        soon = self.leaf("Lắp cốp pha", 1, 9)
        alerts.evaluate_rule(self.rule("Sắp đến hạn"), day(7))  # 2 days ahead
        self.assertTrue(self.alert_of("Sắp đến hạn", soon))
        far = self.leaf("Hoàn thiện", 1, 20)
        alerts.evaluate_rule(self.rule("Sắp đến hạn"), day(7))
        self.assertFalse(self.alert_of("Sắp đến hạn", far))

    def test_escalation_climbs_its_steps(self):
        late = self.leaf("Cốt thép", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))  # steps: 2 days → Chỉ huy trưởng, 5 days → manager
        alert = self.alert_of("Quá hạn", late)
        self.assertEqual(alerts.escalate(now_datetime() + timedelta(days=1)), 0)
        alerts.escalate(now_datetime() + timedelta(days=2))
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "level"), 1)
        self.assertEqual(alert_notices(CHIEF, "Leo thang bậc 1"), 1)
        self.assertEqual(alert_notices(MANAGER, "Cốt thép"), 0)
        alerts.escalate(now_datetime() + timedelta(days=3))  # nothing new
        self.assertEqual(alert_notices(CHIEF, "Cốt thép"), 1)
        alerts.escalate(now_datetime() + timedelta(days=5))
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "level"), 2)
        self.assertEqual(alert_notices(MANAGER, "Leo thang bậc 2"), 1)
        self.assertEqual(sorted(json.loads(frappe.db.get_value("PM Alert", alert.name, "recipients"))),
                         sorted([ENGINEER, CHIEF, MANAGER]))

    def test_two_steps_at_once_keep_everyone(self):
        late = self.leaf("Chống thấm", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        alert = self.alert_of("Quá hạn", late)
        alerts.escalate(now_datetime() + timedelta(days=6))
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "level"), 2)
        self.assertEqual(sorted(json.loads(frappe.db.get_value("PM Alert", alert.name, "recipients"))),
                         sorted([ENGINEER, CHIEF, MANAGER]))

    def test_acknowledged_stops_climbing(self):
        late = self.leaf("Lát nền", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        alert = self.alert_of("Quá hạn", late)
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, alerts.acknowledge, alert.name)
        done = as_user(ENGINEER, alerts.acknowledge, alert.name, "đang xử lý")
        self.assertEqual(done["state"], alerts.ACKED)
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "acknowledged_by"), ENGINEER)
        alerts.escalate(now_datetime() + timedelta(days=6))
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "level"), 0)
        self.assertTrue(frappe.db.exists("PM Activity", {"reference_name": late, "content": ["like", "%Đã xác nhận cảnh báo%"]}))

    def test_a_rule_turned_off_ends_its_alerts(self):
        late = self.leaf("Rào chắn", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        frappe.db.set_value("PM Alert Rule", "Quá hạn", "is_active", 0)
        alerts.escalate(now_datetime() + timedelta(days=6))
        self.assertEqual(self.alert_of("Quá hạn", late).level, 0)
        with patch.object(frappe.db, "rollback"):
            alerts.run_daily(day(7))
        self.assertEqual(self.alert_of("Quá hạn", late).state, alerts.OVER)

    def test_a_notice_is_claimed_once(self):
        late = self.leaf("Sơn", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        alert = self.alert_of("Quá hạn", late)
        self.assertEqual(alerts.deliver(alert, {ENGINEER}, 0), [])  # already told at level 0

    def test_who_hears_of_it_must_see_it(self):
        task = self.leaf("Điện nước", 1, 5)
        for user in (OUTSIDER, CHIEF):
            frappe.get_doc({"doctype": "PM Follow", "user": user, "reference_doctype": "Task", "reference_name": task,
                            "project": self.project, "watching": 1}).insert(ignore_permissions=True)
        hit = alerts._hit("Task", task, self.project, task, day(5), "x")
        self.assertEqual(alerts.recipients({"to_followers": 1}, hit), {CHIEF, ENGINEER})  # the assignee follows it
        self.assertEqual(alerts.recipients({"to_manager": 1, "to_role": "Chỉ huy trưởng"}, hit), {MANAGER, CHIEF})

    def test_supervisor_from_the_employee_record(self):
        company = frappe.defaults.get_global_default("company")
        boss = frappe.get_doc({"doctype": "Employee", "first_name": f"Sếp {TAG}", "gender": "Male", "company": company,
                               "date_of_birth": "1980-01-01", "date_of_joining": "2020-01-01", "user_id": MANAGER})
        boss.insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Employee", "first_name": f"Kỹ sư {TAG}", "gender": "Male", "company": company,
                        "date_of_birth": "1990-01-01", "date_of_joining": "2021-01-01", "user_id": ENGINEER,
                        "reports_to": boss.name}).insert(ignore_permissions=True)
        task = self.leaf("Trát", 1, 5)
        hit = alerts._hit("Task", task, self.project, task, day(5), "x")
        self.assertEqual(alerts.recipients({"to_supervisor": 1}, hit), {MANAGER})

    def test_not_accepted_tells_the_assignee(self):
        task = self.leaf("Lợp mái", 1, 20, accountable=None)
        assignment = assignments.assign(task, C.RESPONSIBLE, user=CHIEF)
        frappe.db.set_value("PM Task Assignment", assignment, "assigned_on", "2030-01-01 08:00:00")
        alerts.evaluate_rule(self.rule("Chưa nhận việc"), day(7))
        alert = frappe.db.get_value("PM Alert", {"reference_doctype": "PM Task Assignment",
                                                 "reference_name": str(assignment)}, ["recipients", "task"], as_dict=True)
        self.assertEqual((json.loads(alert.recipients), alert.task), ([CHIEF], task))

    def test_quiet_hours(self):
        night = frappe._dict(quiet_start="21:00:00", quiet_end="07:00:00")
        self.assertTrue(alerts.quiet(night, "2030-01-07 22:00:00"))
        self.assertTrue(alerts.quiet(night, "2030-01-07 06:59:00"))
        self.assertFalse(alerts.quiet(night, "2030-01-07 07:00:00"))
        self.assertFalse(alerts.quiet(night, "2030-01-07 12:00:00"))
        noon = frappe._dict(quiet_start=timedelta(hours=12), quiet_end=timedelta(hours=13))
        self.assertTrue(alerts.quiet(noon, "2030-01-07 12:30:00"))
        self.assertFalse(alerts.quiet(frappe._dict(quiet_start=None, quiet_end=None), "2030-01-07 12:30:00"))

    def test_email_waits_for_the_end_of_quiet_hours(self):
        task = self.leaf("Ốp lát", 1, 5)
        rule = self.rule("Quá hạn")
        rule.send_email = 1
        with patch.object(alerts, "email_ready", return_value=True), \
                patch.object(alerts, "send_email") as send, patch.object(alerts, "quiet", return_value=True):
            alerts.evaluate_rule(rule, day(7))
            alert = self.alert_of("Quá hạn", task)
            self.assertEqual(json.loads(alert.email_pending), [ENGINEER])
            send.assert_not_called()
            self.assertEqual(alert_notices(ENGINEER, "Ốp lát"), 1)  # the in-app notice does not wait
        with patch.object(alerts, "email_ready", return_value=True), \
                patch.object(alerts, "send_email") as send, patch.object(alerts, "quiet", return_value=False):
            self.assertGreaterEqual(alerts.send_pending_emails(), 1)  # (other projects of the site may wait too)
            self.assertIn(ENGINEER, [call.args[0] for call in send.call_args_list])
            self.assertIsNone(frappe.db.get_value("PM Alert", alert.name, "email_pending"))

    def test_muted_types_and_preferences(self):
        as_user(ENGINEER, alerts.save_preference, {"muted_types": "Quá hạn", "quiet_start": "22:00", "digest_daily": 0})
        mine = as_user(ENGINEER, alerts.my_preference)
        self.assertEqual((mine["muted_types"], mine["quiet_start"], mine["digest_daily"]), (["Quá hạn"], "22:00", 0))
        self.assertIn("Quá hạn", mine["types"])
        task = self.leaf("Kính", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        self.assertEqual(alert_notices(ENGINEER, "Kính"), 0)
        self.assertTrue(self.alert_of("Quá hạn", task))
        # through the services only: nobody but administrators reads the DocType
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, frappe.get_list, "PM Notification Preference")

    def test_what_each_person_sees(self):
        task = self.leaf("Cửa", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        alert = self.alert_of("Quá hạn", task)
        mine = as_user(ENGINEER, alerts.mine)
        self.assertIn(alert.name, [row.name for row in mine["alerts"]])
        self.assertGreaterEqual(mine["open"], 1)
        self.assertEqual(as_user(OUTSIDER, alerts.mine)["alerts"], [])
        self.assertEqual(as_user(OUTSIDER, frappe.get_list, "PM Alert", filters={"project": self.project}), [])
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, alerts.of_project, self.project)
        self.assertIn(alert.name, [row.name for row in as_user(MANAGER, alerts.of_project, self.project)])
        doc = frappe.get_doc("PM Alert", alert.name)
        self.assertFalse(as_user(ENGINEER, frappe.has_permission, "PM Alert", "write", doc))

    def test_an_alert_cannot_be_edited(self):
        task = self.leaf("Trần", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        doc = frappe.get_doc("PM Alert", self.alert_of("Quá hạn", task).name)
        doc.message = "khác"
        self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)

    def test_rule_checks(self):
        doc = frappe.get_doc({"doctype": "PM Alert Rule", "rule_name": f"Thử {TAG}", "rule_type": alerts.OVERDUE,
                              "escalations": [{"after_days": 3, "to_manager": 1}, {"after_days": 2, "to_manager": 1}]})
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)
        doc.escalations = []
        doc.append("escalations", {"after_days": 2})
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)
        doc.escalations = []
        doc.is_builtin = 1
        doc.insert(ignore_permissions=True)
        self.assertRaises(frappe.ValidationError, frappe.delete_doc, "PM Alert Rule", doc.name, ignore_permissions=True)
        frappe.db.set_value("PM Alert Rule", doc.name, "is_builtin", 0)
        frappe.delete_doc("PM Alert Rule", doc.name, ignore_permissions=True)  # one of the administrator's own: it goes

    def test_the_default_rules_are_installed_once(self):
        for rule in C.DEFAULT_ALERT_RULES:
            self.assertTrue(frappe.db.exists("PM Alert Rule", rule["rule_name"]))
        frappe.db.set_value("PM Alert Rule", "Sắp đến hạn", "days", 4)
        install.ensure_alert_rules()
        self.assertEqual(frappe.db.get_value("PM Alert Rule", "Sắp đến hạn", "days"), 4)  # the administrator's choice stays
        self.assertEqual(len(frappe.get_all("PM Alert Rule", filters={"rule_name": "Quá hạn"})), 1)
        options = frappe.get_meta("PM Alert Rule").get_field("rule_type").options.split("\n")
        self.assertTrue(set(alerts.TYPES) <= set(options))

    def test_a_failing_rule_does_not_stop_the_others(self):
        self.leaf("Bả", 1, 5)
        real = alerts.evaluate_rule

        def flaky(rule, today=None):
            if rule.name == "Sắp đến hạn":
                raise RuntimeError("hỏng")
            return real(rule, today)

        with patch.object(alerts, "evaluate_rule", side_effect=flaky), patch.object(frappe.db, "rollback"), \
                patch.object(frappe, "log_error") as logged:
            out = alerts.run_daily(day(7))
        self.assertNotIn("Sắp đến hạn", out)
        self.assertGreaterEqual(out["Quá hạn"]["opened"], 1)
        logged.assert_called()


# --- phases ----------------------------------------------------------------------------------------------------------------

class TestPhases(AlertBase):
    def build(self, mode):
        first = make_task(self.project, f"Giai đoạn 1 {mode}", is_group=1, pm_gate_mode=mode)
        second = make_task(self.project, f"Giai đoạn 2 {mode}", is_group=1)
        a = self.leaf(f"Việc A {mode}", 1, 5, parent=first)
        b = self.leaf(f"Việc B {mode}", 6, 9, parent=second)
        rollup.reconcile(self.project)
        return first, second, a, b

    def finish(self, task):
        frappe.db.set_value("Task", task, {"status": C.COMPLETED, "progress": 100})
        rollup.reconcile(self.project)

    def test_automatic_passes_when_its_work_is_done(self):
        first, second, a, _b = self.build(phases.AUTO)
        result = phases.check(self.project)
        self.assertEqual(result["phase"], first)
        self.assertIn("còn 1 việc chưa xong", result["missing"])
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_current_phase"), first)
        self.finish(a)
        phases.check(self.project)
        self.assertEqual(frappe.db.get_value("Task", first, "pm_gate_state"), phases.PASSED)
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_current_phase"), second)
        self.assertTrue(frappe.db.exists("PM Activity", {"reference_name": self.project,
                                                         "content": ["like", "%Chuyển từ giai đoạn%"]}))
        self.assertEqual(notices(MANAGER, "Chuyển từ giai đoạn"), 1)

    def test_the_rollup_moves_the_phase_on(self):
        first, second, a, _b = self.build(phases.AUTO)
        frappe.db.set_value("Task", a, {"status": C.COMPLETED, "progress": 100})
        frappe.cache.sadd(rollup._key(self.project), first)
        rollup.process(self.project)
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_current_phase"), second)

    def test_approval_waits_for_the_manager(self):
        first, second, a, _b = self.build(phases.APPROVAL)
        self.finish(a)
        phases.check(self.project)
        self.assertEqual(frappe.db.get_value("Task", first, "pm_gate_state"), phases.WAITING)
        self.assertEqual(notices(MANAGER, "chờ bạn duyệt chuyển giai đoạn"), 1)
        phases.check(self.project)  # asked once
        self.assertEqual(notices(MANAGER, "chờ bạn duyệt chuyển giai đoạn"), 1)
        alerts.evaluate_rule(self.rule("Chờ duyệt chuyển giai đoạn"), day(7))
        self.assertTrue(self.alert_of("Chờ duyệt chuyển giai đoạn", first))
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, phases.pass_phase, first)
        state = as_user(MANAGER, phases.pass_phase, first, "đủ hồ sơ")
        self.assertEqual(state["current"]["name"], second)
        self.assertEqual(frappe.db.get_value("Task", first, "pm_gate_state"), phases.PASSED)
        alerts.evaluate_rule(self.rule("Chờ duyệt chuyển giai đoạn"), day(8))
        self.assertEqual(self.alert_of("Chờ duyệt chuyển giai đoạn", first).state, alerts.OVER)

    def test_reopened_work_takes_the_request_back(self):
        first, _second, a, _b = self.build(phases.APPROVAL)
        self.finish(a)
        phases.check(self.project)
        frappe.db.set_value("Task", a, {"status": C.WORKING, "progress": 80})
        rollup.reconcile(self.project)
        phases.check(self.project)
        self.assertFalse(frappe.db.get_value("Task", first, "pm_gate_state"))
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, phases.pass_phase, first)

    def test_manual_is_passed_by_hand(self):
        first, second, a, _b = self.build(phases.MANUAL)
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, phases.pass_phase, second)  # not the current one
        self.finish(a)
        phases.check(self.project)
        self.assertFalse(frappe.db.get_value("Task", first, "pm_gate_state"))
        state = as_user(MANAGER, phases.state, self.project)
        self.assertEqual((state["current"]["name"], state["current"]["can_pass"]), (first, True))
        self.assertTrue(state["current"]["next"].endswith(f"Giai đoạn 2 {phases.MANUAL}"))
        self.assertFalse(as_user(ENGINEER, phases.state, self.project)["current"]["can_pass"])
        as_user(MANAGER, phases.pass_phase, first)
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_current_phase"), second)

    def test_a_layer_condition_holds_the_phase(self):
        first, _second, a, _b = self.build(phases.AUTO)
        self.finish(a)
        frappe.flags.pm_test_block_gate = True
        real = frappe.get_hooks

        def hooks(name=None, *args, **kwargs):
            return [GATE_PATH] if name == "pm_gate_checks" else real(name, *args, **kwargs)

        with patch.object(frappe, "get_hooks", side_effect=hooks):
            result = phases.check(self.project)
            self.assertIn("chưa nghiệm thu giai đoạn", result["missing"])
            self.assertNotEqual(frappe.db.get_value("Task", first, "pm_gate_state"), phases.PASSED)
            frappe.flags.pm_test_block_gate = False
            phases.check(self.project)
        self.assertEqual(frappe.db.get_value("Task", first, "pm_gate_state"), phases.PASSED)

    def test_the_last_phase(self):
        first, second, a, b = self.build(phases.AUTO)
        frappe.db.set_value("Task", second, "pm_gate_mode", phases.AUTO)
        self.finish(a)
        self.finish(b)
        self.assertIsNone(phases.check(self.project))
        self.assertIsNone(frappe.db.get_value("Project", self.project, "pm_current_phase"))
        state = phases.state(self.project)
        self.assertEqual((state["done"], state["current"]), (2, None))


# --- digests ---------------------------------------------------------------------------------------------------------------

class TestDigest(AlertBase):
    def test_daily_once_with_what_matters(self):
        self.leaf("Hàn", 1, 5)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        lines = digest.daily_lines(ENGINEER, day(7))
        self.assertTrue(any("cảnh báo đang mở" in line for line in lines))
        self.assertTrue(any("việc quá hạn" in line for line in lines))
        frappe.db.set_single_value("PM Settings", "daily_reminders", 1)
        digest.daily(day(7))
        digest.daily(day(7))
        self.assertEqual(notices(ENGINEER, digest.DAILY), 1)

    def test_daily_can_be_turned_off(self):
        self.leaf("Mài", 1, 5)
        as_user(ENGINEER, alerts.save_preference, {"digest_daily": 0})
        frappe.db.set_single_value("PM Settings", "daily_reminders", 1)
        digest.daily(day(7))
        self.assertEqual(notices(ENGINEER, digest.DAILY), 0)

    def test_weekly_for_the_manager(self):
        self.leaf("Dọn dẹp", 1, 5)
        frappe.db.set_single_value("PM Settings", "digest_weekly", 1)
        digest.weekly(day(7))
        digest.weekly(day(7))
        self.assertEqual(notices(MANAGER, digest.WEEKLY), 1)
        name = frappe.db.get_value("Project", self.project, "project_name")
        self.assertIn(name, frappe.db.get_value("Notification Log", {"for_user": MANAGER,
                                                                     "subject": ["like", f"{digest.WEEKLY}%"]}, "subject"))


# --- what the screens read -------------------------------------------------------------------------------------------------

class TestScreens(AlertBase):
    def test_portfolio(self):
        from project_manager.project_manager.services import portfolio

        late = self.leaf("Nghiệm thu", 1, 5)
        frappe.db.set_value("Project", self.project, {"pm_health": risk.RED, "pm_health_reason": "dự báo trễ 9 ngày"})
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        view = as_user(MANAGER, portfolio.portfolio)
        row = next(r for r in view["rows"] if r.name == self.project)
        self.assertEqual((row.pm_health, row.alerts_open, row.manager_name is not None), (risk.RED, 1, True))
        self.assertGreaterEqual(view["totals"][risk.RED], 1)
        self.assertNotIn(self.project, [r.name for r in as_user(OUTSIDER, portfolio.portfolio)["rows"]])
        self.assertTrue(frappe.db.exists("PM Alert", {"reference_name": late}))

    def test_overview_has_health_gate_and_alerts(self):
        from project_manager.project_manager.services import projects

        first = make_task(self.project, "Giai đoạn chuẩn bị", is_group=1, pm_gate_mode=phases.APPROVAL)
        self.leaf("Dọn mặt bằng", 1, 5, parent=first)
        rollup.reconcile(self.project)
        alerts.evaluate_rule(self.rule("Quá hạn"), day(7))
        view = as_user(MANAGER, projects.overview, self.project)
        self.assertEqual(view["gate"]["current"]["name"], first)
        self.assertEqual(view["gate"]["current"]["mode"], phases.APPROVAL)
        self.assertEqual(view["alerts_open"], 1)
        self.assertIn("health", view)
        self.assertIn("pm_health", view["project"])


class TestGateMode(AlertBase):
    def test_a_planner_sets_the_mode_and_a_ready_phase_passes(self):
        from project_manager.project_manager.services import tree

        first = make_task(self.project, "Giai đoạn đặt chế độ", is_group=1)
        work = self.leaf("Việc đặt chế độ", 1, 5, parent=first)
        frappe.db.set_value("Task", work, {"status": C.COMPLETED, "progress": 100})
        rollup.reconcile(self.project)
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, tree.update, first, {"pm_gate_mode": phases.AUTO})
        as_user(MANAGER, tree.update, first, {"pm_gate_mode": phases.AUTO})
        self.assertEqual(frappe.db.get_value("Task", first, "pm_gate_state"), phases.PASSED)
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, tree.update, first, {"pm_gate_mode": "Bất kỳ"})
