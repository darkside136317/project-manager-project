"""M4: dependencies, the critical path of a real project, moving dates with what follows them, the forecast, baselines.

Dates are fixed in January 2030 with a calendar of the test's own: Sundays off (6, 13, 20...) and a public holiday on
Wednesday the 16th, so working days run 7 8 9 10 11 12 | 14 15 | 17 18 19 | 21...

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_schedule
"""

from unittest.mock import patch

import frappe
from frappe.utils import flt, getdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import assignments, baseline, projects, rollup, schedule, tree, workdays
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

MANAGER = f"sc.manager.{TAG}@example.com"
ENGINEER = f"sc.engineer.{TAG}@example.com"
LEAD = f"sc.lead.{TAG}@example.com"
OUTSIDER = f"sc.outsider.{TAG}@example.com"
USERS = (MANAGER, ENGINEER, LEAD, OUTSIDER)
HOLIDAYS = f"Lich thu {TAG}"


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


def day(number: int) -> str:
    return f"2030-01-{number:02d}"


class ScheduleBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": HOLIDAYS, "from_date": "2030-01-01", "to_date": "2030-12-31",
                        "holidays": [{"holiday_date": "2030-01-06", "description": "Chủ nhật", "weekly_off": 1},
                                     {"holiday_date": "2030-01-16", "description": "Lễ"}]}).insert(ignore_permissions=True)
        cls.project = make_project("SC")
        cls.other = make_project("SC khác")
        frappe.db.set_value("Project", cls.project, {"pm_holiday_list": HOLIDAYS, "expected_end_date": day(31)})
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, LEAD, "Tổ trưởng")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for project in (cls.project, cls.other, *frappe.get_all("Project", filters={"project_name": ["like", f"%{TAG}%"]}, pluck="name")):
            if frappe.db.exists("Project", project):
                drop_project(project)
        frappe.delete_doc("Holiday List", HOLIDAYS, force=True, ignore_permissions=True, ignore_missing=True)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.local.pm_calendars = {}
        frappe.local.pm_milestone_types = None
        # a chain a -> b -> c (the critical path) and d, which only has to finish before c
        self.a = self.task("A", 7, 9)
        self.b = self.task("B", 10, 11)
        self.c = self.task("C", 12, 15)
        self.d = self.task("D", 7, 8)
        schedule.add_dependency(self.a, self.b)
        schedule.add_dependency(self.b, self.c)
        schedule.add_dependency(self.d, self.c)

    def task(self, subject, first=None, last=None, **values):
        dates = {"exp_start_date": day(first), "exp_end_date": day(last)} if first else {}
        return make_task(self.project, subject, **dates, **values)

    def plan(self) -> dict:
        schedule.refresh(self.project)
        rows = frappe.get_all("Task", filters={"project": self.project},
                              fields=["subject", "pm_total_float", "pm_is_critical", "pm_conflict_days"], limit_page_length=0)
        return {row.subject: row for row in rows}

    def dates(self, task) -> tuple:
        row = frappe.db.get_value("Task", task, ["exp_start_date", "exp_end_date"], as_dict=True)
        return getdate(row.exp_start_date).day, getdate(row.exp_end_date).day


class TestPlan(ScheduleBase):
    def test_critical_path_and_float(self):
        plan = self.plan()
        self.assertEqual({k: plan[k].pm_is_critical for k in "ABCD"}, {"A": 1, "B": 1, "C": 1, "D": 0})
        self.assertEqual(plan["D"].pm_total_float, 3)  # it may finish as late as the 11th: 9 10 11
        self.assertEqual(getdate(frappe.db.get_value("Project", self.project, "pm_plan_end")), getdate(day(15)))

    def test_only_changes_are_written(self):
        frappe.db.set_value("Task", self.d, "pm_total_float", 99)
        self.assertEqual(schedule.refresh(self.project), 1)
        self.assertEqual(schedule.refresh(self.project), 0)

    def test_a_start_earlier_than_its_dependency_allows_is_flagged(self):
        late = self.task("Sớm quá", 8, 8)
        schedule.add_dependency(self.c, late)
        plan = self.plan()
        self.assertEqual(plan["Sớm quá"].pm_conflict_days, 7)  # could only start on the 17th: 9 10 11 12 14 15 17
        self.assertEqual(plan["A"].pm_conflict_days, 0)

    def test_dates_follow_the_calendar(self):
        calendar = workdays.calendar_of(self.project)
        self.assertEqual(calendar.count(day(12), day(17)), 4)  # 12 14 15 17
        self.assertFalse(calendar.is_working(day(16)))
        self.assertFalse(calendar.is_working("2030-06-02"))  # a Sunday, known from the weekly days off
        over_a_holiday = frappe._dict(exp_start_date=day(15), exp_end_date=day(17), pm_node_type=None)
        self.assertEqual(schedule.Network(self.project).span(over_a_holiday)[1], 2)

    def test_a_milestone_on_the_day_its_predecessor_ends_is_fine(self):
        milestone = self.task("Mốc xong", 15, 15, pm_node_type="Mốc")
        after = self.task("Sau mốc", 17, 18)
        schedule.add_dependency(self.c, milestone)
        schedule.add_dependency(milestone, after)
        plan = self.plan()
        self.assertEqual((plan["Mốc xong"].pm_conflict_days, plan["Sau mốc"].pm_conflict_days), (0, 0))
        self.assertEqual(plan["Mốc xong"].pm_is_critical, 1)

    def test_tasks_without_dates_stay_out(self):
        self.task("Chưa có ngày")
        plan = self.plan()
        self.assertEqual(plan["Chưa có ngày"].pm_is_critical, 0)
        self.assertEqual(schedule.summary(self.project)["unscheduled"], 1)

    def test_one_phase_after_another(self):
        first = make_task(self.project, "Giai đoạn 1", is_group=1)
        second = make_task(self.project, "Giai đoạn 2", is_group=1)
        make_task(self.project, "1a", parent=first, exp_start_date=day(21), exp_end_date=day(23))
        make_task(self.project, "2a", parent=second, exp_start_date=day(22), exp_end_date=day(22))
        make_task(self.project, "2b", parent=second, exp_start_date=day(24), exp_end_date=day(25))
        schedule.add_dependency(first, second)
        plan = self.plan()
        self.assertEqual(plan["2a"].pm_conflict_days, 2)  # the whole of phase 2 must wait for phase 1
        self.assertEqual(plan["2b"].pm_conflict_days, 0)
        self.assertEqual(plan["1a"].pm_is_critical, 1)

    def test_every_kind_of_link_on_real_tasks(self):
        x = self.task("X", 21, 23)
        y = self.task("Y", 21, 22)
        schedule.add_dependency(x, y, "FF", 1)
        self.assertEqual(self.plan()["Y"].pm_conflict_days, 2)  # must finish on the 24th at the earliest


class TestDependencies(ScheduleBase):
    def test_what_is_refused(self):
        group = make_task(self.project, "Nhóm", is_group=1)
        inside = make_task(self.project, "Trong nhóm", parent=group)
        foreign = make_task(self.other, "Dự án khác")
        for predecessor, successor, kind in ((self.a, self.a, "FS"), (group, inside, "FS"), (inside, group, "FS"),
                                             (self.a, foreign, "FS"), (self.a, self.d, "XX"), (group, self.d, "SS"),
                                             (self.a, self.b, "FS")):  # the last one exists already
            with self.assertRaises(frappe.ValidationError, msg=f"{predecessor}->{successor} {kind}"):
                schedule.add_dependency(predecessor, successor, kind)

    def test_circles_are_refused_whatever_their_length(self):
        with self.assertRaises(frappe.ValidationError) as caught:
            schedule.add_dependency(self.c, self.a)
        self.assertIn("vòng tròn", str(caught.exception))
        tasks = [self.task(f"Dài {i}") for i in range(30)]  # no dates: a circle is a circle
        for before, after in zip(tasks, tasks[1:]):
            schedule.add_dependency(before, after)
        with self.assertRaises(frappe.ValidationError):
            schedule.add_dependency(tasks[-1], tasks[0])

    def test_circles_through_a_group_are_refused(self):
        group = make_task(self.project, "Nhóm", is_group=1)
        inside = make_task(self.project, "Trong nhóm", parent=group)
        outside = self.task("Ngoài", 21, 22)
        schedule.add_dependency(group, outside)
        with self.assertRaises(frappe.ValidationError):
            schedule.add_dependency(outside, inside)

    def test_changing_a_link_cannot_make_a_circle_either(self):
        name = frappe.db.get_value("PM Task Dependency", {"predecessor": self.a, "successor": self.b}, "name")
        schedule.update_dependency(name, "SS", 2)
        row = frappe.db.get_value("PM Task Dependency", name, ["dep_type", "lag_days"], as_dict=True)
        self.assertEqual((row.dep_type, row.lag_days), ("SS", 2))
        with self.assertRaises(frappe.ValidationError):
            schedule.update_dependency(name, "XX")

    def test_who_may(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, schedule.add_dependency, self.a, self.d)
        name = frappe.db.get_value("PM Task Dependency", {"predecessor": self.a}, "name")
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, schedule.remove_dependency, name)
        self.assertFalse(frappe.has_permission("PM Task Dependency", "write", doc=frappe.get_doc("PM Task Dependency", name), user=MANAGER))
        as_user(MANAGER, schedule.remove_dependency, name)
        self.assertFalse(frappe.db.exists("PM Task Dependency", name))

    def test_of_task_reads_both_ways(self):
        self.plan()
        view = as_user(ENGINEER, schedule.of_task, self.c)
        self.assertEqual({row.task for row in view["predecessors"]}, {self.b, self.d})
        self.assertEqual(view["successors"], [])
        self.assertEqual((view["critical"], view["can_edit"]), (1, False))
        self.assertEqual(as_user(MANAGER, schedule.of_task, self.a)["successors"][0].label.split()[-1], "B")
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, schedule.of_task, self.a)

    def test_a_change_of_links_shows_at_once(self):
        self.assertEqual(frappe.db.get_value("Task", self.d, "pm_total_float"), 3)  # no job has run
        schedule.add_dependency(self.d, self.b)
        self.assertEqual(frappe.db.get_value("Task", self.d, "pm_total_float"), 1)

    def test_the_change_is_in_the_timeline(self):
        texts = frappe.get_all("PM Activity", filters={"task": self.b, "activity_type": "Thay đổi"}, pluck="content")
        self.assertTrue(any("phụ thuộc" in text for text in texts))

    def test_a_task_without_history_leaves_with_its_links(self):
        fresh = self.task("Nhập nhầm", 21, 22)
        schedule.add_dependency(self.d, fresh)
        frappe.db.delete("PM Activity", {"task": fresh})
        tree.delete(fresh)
        self.assertFalse(frappe.db.exists("PM Task Dependency", {"successor": fresh}))

    def test_a_project_from_a_template_brings_its_links(self):
        frappe.db.set_value("Project", self.project, "pm_is_template", 1)
        created = projects.create({"project_name": f"Từ mẫu có phụ thuộc {TAG}"}, self.project)
        links = frappe.get_all("PM Task Dependency", filters={"project": created["name"]}, fields=["predecessor", "successor"])
        self.assertEqual(len(links), 3)
        subjects = {t.name: t.subject for t in frappe.get_all("Task", filters={"project": created["name"]}, fields=["name", "subject"])}
        self.assertIn(("A", "B"), {(subjects[l.predecessor], subjects[l.successor]) for l in links})


class TestMoving(ScheduleBase):
    def test_a_preview_shows_what_follows_and_writes_nothing(self):
        result = as_user(MANAGER, schedule.preview, self.a, day(8), day(10))
        changes = {c["label"].split()[-1]: c for c in result["changes"]}
        self.assertEqual(set(changes), {"A", "B", "C"})  # d is free to stay
        self.assertTrue(changes["A"]["direct"])
        self.assertFalse(changes["B"]["direct"])
        self.assertEqual((changes["B"]["to_start"], changes["B"]["to_end"]), (day(11), day(12)))
        self.assertEqual((changes["C"]["to_start"], changes["C"]["to_end"]), (day(14), day(17)))  # over the Sunday and the holiday
        self.assertEqual((result["plan_end_before"], result["plan_end_after"]), (day(15), day(17)))
        self.assertFalse(result["over_contract"])
        self.assertEqual(self.dates(self.a), (7, 9))

    def test_applying_writes_the_dates_and_the_history(self):
        schedule.refresh(self.project)
        as_user(MANAGER, schedule.apply, self.a, day(8), day(10))
        self.assertEqual((self.dates(self.a), self.dates(self.b), self.dates(self.c), self.dates(self.d)),
                         ((8, 10), (11, 12), (14, 17), (7, 8)))
        moved = frappe.get_all("PM Activity", filters={"task": self.c, "activity_type": "Đổi hạn"}, fields=["content", "actor"])[0]
        self.assertIn("theo", moved.content)  # it says why it moved
        self.assertEqual(moved.actor, MANAGER)
        schedule.refresh(self.project)
        self.assertEqual(getdate(frappe.db.get_value("Project", self.project, "pm_plan_end")), getdate(day(17)))

    def test_nothing_is_pulled_earlier_by_itself(self):
        result = schedule.preview(self.a, "2030-01-02", "2030-01-04")
        self.assertEqual([c["name"] for c in result["changes"]], [self.a])

    def test_a_date_breaking_a_dependency_is_corrected(self):
        result = schedule.preview(self.b, day(7), day(8))
        self.assertTrue(result["clamped"])
        change = next((c for c in result["changes"] if c["name"] == self.b), None)
        self.assertTrue(change is None or change["to_start"] == day(10))

    def test_what_is_finished_stays(self):
        frappe.db.set_value("Task", self.c, "status", C.COMPLETED)
        result = schedule.preview(self.a, day(14), day(17))
        self.assertNotIn(self.c, [c["name"] for c in result["changes"]])
        with self.assertRaises(frappe.ValidationError):
            schedule.preview(self.c, day(21), day(22))

    def test_shifting_a_whole_phase(self):
        group = make_task(self.project, "Khối", is_group=1)
        first = make_task(self.project, "k1", parent=group, exp_start_date=day(21), exp_end_date=day(22))
        second = make_task(self.project, "k2", parent=group, exp_start_date=day(23), exp_end_date=day(24))
        rollup.reconcile(self.project)
        result = schedule.preview(group, day(23))
        by_name = {c["name"]: c for c in result["changes"]}
        self.assertEqual((by_name[first]["to_start"], by_name[first]["to_end"]), (day(23), day(24)))
        self.assertEqual((by_name[second]["to_start"], by_name[second]["to_end"]), (day(25), day(26)))
        with self.assertRaises(frappe.ValidationError):
            schedule.preview(group)

    def test_a_reason_is_needed_once_work_is_given(self):
        assignments.assign(self.c, C.ACCOUNTABLE, user=ENGINEER)
        result = as_user(MANAGER, schedule.preview, self.a, day(8), day(10))
        self.assertTrue(result["reason_required"])
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, schedule.apply, self.a, day(8), day(10))
        as_user(MANAGER, schedule.apply, self.a, day(8), day(10), "Chờ thép")
        self.assertIn("Chờ thép", frappe.get_all("PM Activity", filters={"task": self.c, "activity_type": "Đổi hạn"}, pluck="content")[0])
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": ENGINEER, "subject": ["like", "Kế hoạch đổi%"]}))

    def test_who_may_move(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, schedule.preview, self.a, day(8), day(10))
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, schedule.apply, self.a, day(8), day(10))

    def test_going_past_the_contract_is_said(self):
        result = schedule.preview(self.c, "2030-02-01", "2030-02-05")
        self.assertTrue(result["over_contract"])

    def test_the_weight_follows_the_move(self):
        schedule.apply(self.a, day(8), day(14))  # now a longer task
        self.assertEqual(flt(frappe.db.get_value("Task", self.a, "pm_rollup_weight")), 7)

    def test_fixing_every_conflict(self):
        late = self.task("Sớm quá", 8, 8)
        schedule.add_dependency(self.c, late)
        preview = as_user(MANAGER, schedule.conflicts_preview, self.project)
        self.assertEqual([c["name"] for c in preview["changes"]], [late])
        self.assertEqual(self.dates(late), (8, 8))
        as_user(MANAGER, schedule.conflicts_apply, self.project)
        self.assertEqual(self.dates(late), (17, 17))
        self.assertEqual(self.plan()["Sớm quá"].pm_conflict_days, 0)


class TestForecast(ScheduleBase):
    def forecast(self, today):
        return schedule.compute_forecast(schedule.Network(self.project), today=today)

    def test_on_plan_it_is_the_plan(self):
        result = self.forecast("2030-01-02")
        self.assertEqual(result["end"], getdate(day(15)))

    def test_what_has_not_started_cannot_start_before_today(self):
        result = self.forecast(day(14))  # nothing started: a (3) b (2) c (3) from the 14th: 14 15 17 | 18 19 | 21 22 23
        self.assertEqual(result["end"], getdate(day(23)))

    def test_work_under_way_runs_at_its_pace(self):
        frappe.db.set_value("Task", self.a, {"status": C.COMPLETED, "act_end_date": day(9), "act_start_date": day(7), "progress": 100})
        frappe.db.set_value("Task", self.b, {"status": C.WORKING, "act_start_date": day(10), "progress": 50})
        result = self.forecast(day(10))  # 50 % on its first day: pace 0.4 x 50 = 20 % a day, so 3 more days: 10 11 12
        self.assertEqual(getdate(result["tasks"][self.b]["pm_forecast_end"]), getdate(day(12)))
        self.assertEqual(result["end"], getdate(day(17)))  # c follows: 14 15 17
        self.assertEqual(result["tasks"][self.b]["pm_spi"], 1.0)  # half the plan by the end of today, and half done

    def test_recent_pace_counts_more(self):
        calendar = workdays.calendar_of(self.project)
        row = frappe._dict(name="t", status=C.WORKING, progress=40)
        slow = schedule.remaining_days(row, 10, day(7), day(21), calendar, {})  # nothing lately: 0.4 x 40 % over 12 days
        fast = schedule.remaining_days(row, 10, day(7), day(21), calendar, {"t": 0})  # all 40 % in the last 14 days
        self.assertIn(slow, (45, 46))
        self.assertEqual(fast, 18)

    def test_a_stalled_task_does_not_wreck_the_forecast(self):
        calendar = workdays.calendar_of(self.project)
        row = frappe._dict(name="t", status=C.WORKING, progress=1)
        self.assertEqual(schedule.remaining_days(row, 2, "2029-06-01", day(21), calendar, {}), 11)
        self.assertEqual(schedule.remaining_days(frappe._dict(name="t", status=C.WORKING, progress=0), 4, day(21), day(21), calendar, {}), 4)
        self.assertEqual(schedule.remaining_days(frappe._dict(name="t", status=C.REVIEW, progress=100), 4, day(7), day(21), calendar, {}), 1)

    def test_what_is_done_keeps_its_real_dates(self):
        frappe.db.set_value("Task", self.a, {"status": C.COMPLETED, "act_start_date": day(7), "act_end_date": day(11), "progress": 100})
        result = self.forecast(day(11))  # finished two days late, so everything after it is late too: 12 14 | 15 17 18
        self.assertEqual(getdate(result["tasks"][self.a]["pm_forecast_end"]), getdate(day(11)))
        self.assertEqual(result["end"], getdate(day(18)))

    def test_project_spi(self):
        frappe.db.set_value("Task", self.a, {"status": C.WORKING, "progress": 50, "act_start_date": day(7)})
        rollup.reconcile(self.project)
        result = self.forecast(day(9))  # a should be done (3 of 3 days) but is at 50 %; d (2 days) should be done, is at 0
        self.assertEqual(result["spi"], round((3 * 0.5) / (3 + 2), 2))

    def test_a_group_has_a_forecast_too(self):
        group = make_task(self.project, "Khối", is_group=1)
        make_task(self.project, "k1", parent=group, exp_start_date=day(21), exp_end_date=day(22))
        rollup.reconcile(self.project)
        result = self.forecast("2030-01-02")
        self.assertEqual(getdate(result["tasks"][group]["pm_forecast_end"]), getdate(day(22)))


class TestBackground(ScheduleBase):
    def test_a_saved_task_marks_its_project(self):
        frappe.cache.srem(schedule.DIRTY, self.project)
        # no job of this project running: a real one (from setting the test up) may still be on a slow machine
        with patch("frappe.enqueue") as enqueue, patch("frappe.utils.background_jobs.get_job_status", return_value=None):
            doc = frappe.get_doc("Task", self.a)
            doc.exp_end_date = day(10)
            doc.save(ignore_permissions=True)
            frappe.db.after_commit.run()
        self.assertIn(self.project, schedule._dirty())
        self.assertTrue(any(c.kwargs.get("job_id") == f"pm-cpm:{self.project}" and c.kwargs.get("queue") == "pm"
                            for c in enqueue.call_args_list))
        schedule.process(self.project)
        self.assertNotIn(self.project, schedule._dirty())
        self.assertEqual(frappe.db.get_value("Task", self.d, "pm_total_float"), 4)  # c now starts later: d has more room

    def test_a_failed_job_stays_marked(self):
        frappe.cache.sadd(schedule.DIRTY, self.project)
        with patch.object(schedule, "refresh", side_effect=RuntimeError("boom")), patch.object(frappe.db, "rollback"), \
                self.assertRaises(RuntimeError):
            schedule.process(self.project)
        self.assertIn(self.project, schedule._dirty())
        frappe.cache.srem(schedule.DIRTY, self.project)

    def test_a_sweep_picks_up_what_was_missed(self):
        frappe.cache.sadd(schedule.DIRTY, self.project)
        with patch("frappe.enqueue") as enqueue:
            self.assertGreaterEqual(schedule.sweep(), 1)
        self.assertTrue(any(c.kwargs.get("project") == self.project for c in enqueue.call_args_list))
        frappe.cache.srem(schedule.DIRTY, self.project)


class TestScreens(ScheduleBase):
    def row(self, payload, name) -> dict:
        return dict(zip(payload["columns"], next(r for r in payload["rows"] if r[0] == name)))

    def test_gantt_payload(self):
        schedule.refresh(self.project)
        payload = as_user(ENGINEER, schedule.gantt, self.project)
        self.assertEqual(len(payload["rows"][0]), len(payload["columns"]))
        row = self.row(payload, self.c)
        self.assertEqual((row["start"], row["end"], row["critical"], row["group"]), (day(12), day(15), 1, 0))
        self.assertEqual(len(payload["links"]), 3)
        self.assertIn(day(13), payload["days_off"])
        self.assertIn(day(16), payload["days_off"])
        self.assertEqual(payload["can"], {"plan": False, "dates": False})
        self.assertTrue(as_user(MANAGER, schedule.gantt, self.project)["can"]["plan"])
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, schedule.gantt, self.project)

    def test_a_crew_lead_sees_their_tasks_only(self):
        assignments.assign(self.b, C.RESPONSIBLE, user=LEAD)
        payload = as_user(LEAD, schedule.gantt, self.project)
        self.assertTrue(payload["flat"])
        self.assertEqual([r[0] for r in payload["rows"]], [self.b])
        self.assertEqual(payload["links"], [])  # the other ends are not theirs to see

    def test_calendar(self):
        only_deadline = make_task(self.project, "Chỉ có hạn", exp_end_date=day(21))
        view = as_user(ENGINEER, schedule.calendar_view, self.project, day(10), day(21))
        names = {t.name for t in view["tasks"]}
        self.assertEqual(names, {self.b, self.c, only_deadline})  # a and d are over by the 10th
        self.assertIn(day(13), view["days_off"])
        with self.assertRaises(frappe.ValidationError):
            schedule.calendar_view(self.project, "2030-01-01", "2032-01-01")
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, schedule.calendar_view, self.project, day(10), day(21))

    def test_task_search(self):
        found = as_user(ENGINEER, schedule.search_tasks, self.project, "B", self.a)
        self.assertIn(self.b, [row["value"] for row in found])
        self.assertNotIn(self.a, [row["value"] for row in as_user(ENGINEER, schedule.search_tasks, self.project, "", self.a)])


class TestBaseline(ScheduleBase):
    def test_the_curve_adds_up(self):
        calendar = workdays.calendar_of(self.project)
        rows = [frappe._dict(is_group=0, weight=3, start_date=day(7), end_date=day(9)),
                frappe._dict(is_group=0, weight=1, start_date=day(10), end_date=day(10)),
                frappe._dict(is_group=1, weight=4, start_date=day(7), end_date=day(10)),
                frappe._dict(is_group=0, weight=0, start_date=day(7), end_date=day(30))]
        points = baseline.curve_points(rows, calendar)
        self.assertEqual(points[0], (getdate(day(7)), 25.0))
        self.assertEqual(points[-1], (getdate(day(10)), 100.0))
        values = [value for _day, value in points]
        self.assertEqual(values, sorted(values))
        self.assertEqual(baseline.curve_points([], calendar), [])

    def test_capture(self):
        first = as_user(MANAGER, baseline.capture, self.project, "Kế hoạch gốc")
        self.assertEqual((first["title"], first["is_primary"]), ("Kế hoạch gốc", 1))
        doc = frappe.get_doc("PM Baseline", first["name"])
        self.assertEqual((doc.task_count, doc.baseline_no), (4, 1))
        self.assertEqual(getdate(doc.end_date), getdate(day(15)))
        self.assertEqual(frappe.db.count("PM Baseline Task", {"baseline": doc.name}), 4)
        points = baseline.curve_of(self.project)
        self.assertEqual(flt(points[-1].value), 100)
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_primary_baseline"), doc.name)

        second = baseline.capture(self.project)
        self.assertEqual(second["is_primary"], 0)
        self.assertTrue(second["name"].endswith("BL02"))
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_primary_baseline"), doc.name)

    def test_what_is_refused(self):
        empty = make_project("SC rỗng")
        with self.assertRaises(frappe.ValidationError):
            baseline.capture(empty)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, baseline.capture, self.project)
        name = baseline.capture(self.project)["name"]
        doc = frappe.get_doc("PM Baseline", name)
        doc.title = "Sửa lén"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        self.assertFalse(frappe.has_permission("PM Baseline", "write", doc=doc, user=MANAGER))
        with self.assertRaises(frappe.ValidationError):
            baseline.remove(name)  # the main one

    def test_changing_the_main_one(self):
        first = baseline.capture(self.project)["name"]
        second = baseline.capture(self.project)["name"]
        as_user(MANAGER, baseline.set_primary, second)
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_primary_baseline"), second)
        self.assertEqual(frappe.db.get_value("PM Baseline", first, "is_primary"), 0)
        as_user(MANAGER, baseline.remove, first)
        self.assertFalse(frappe.db.exists("PM Baseline", first))
        self.assertEqual(frappe.db.count("PM Baseline Task", {"baseline": first}), 0)

    def test_a_task_in_a_baseline_cannot_be_deleted(self):
        baseline.capture(self.project)
        frappe.db.delete("PM Activity", {"task": self.d})
        frappe.db.delete("PM Task Dependency", {"predecessor": self.d})
        with self.assertRaises(frappe.ValidationError):
            tree.delete(self.d)

    def test_baseline_move_gantt_forecast(self):
        """The definition of done of M4: take a baseline, move a critical task, see the gap and the new forecast."""
        taken = baseline.capture(self.project, "Gốc")["name"]
        schedule.refresh(self.project)
        before = schedule.summary(self.project)
        self.assertEqual((before["forecast_slip"], before["plan_slip"], before["critical"]), (0, 0, 3))

        as_user(MANAGER, schedule.apply, self.b, day(12), day(14))  # b is critical: two days later
        schedule.refresh(self.project)

        after = schedule.summary(self.project)
        self.assertEqual((getdate(after["plan_end"]), getdate(after["forecast_end"])), (getdate(day(18)), getdate(day(18))))
        self.assertEqual((after["forecast_slip"], after["plan_slip"]), (2, 2))
        self.assertEqual(getdate(after["baseline_end"]), getdate(day(15)))

        payload = as_user(ENGINEER, schedule.gantt, self.project)
        row = dict(zip(payload["columns"], next(r for r in payload["rows"] if r[0] == self.b)))
        self.assertEqual((row["start"], row["end"]), (day(12), day(14)))
        self.assertEqual((row["base_start"], row["base_end"]), (day(10), day(11)))
        self.assertEqual(payload["baseline"], taken)

        view = as_user(ENGINEER, baseline.compare, taken)
        self.assertEqual((view["moved"], view["later"], view["earlier"], view["total"]), (2, 2, 0, 4))
        self.assertEqual(view["rows"][0]["plan_slip"], 2)
        self.assertEqual(as_user(ENGINEER, baseline.compare, taken, 1)["total"], 2)  # late only

    def test_new_tasks_are_counted_against_a_baseline(self):
        taken = baseline.capture(self.project)["name"]
        self.task("Phát sinh", 21, 22)
        self.assertEqual(baseline.compare(taken)["added"], 1)

    def test_an_older_baseline_can_be_shown(self):
        first = baseline.capture(self.project)["name"]
        schedule.apply(self.a, day(8), day(10))
        second = baseline.capture(self.project)["name"]
        payload = schedule.gantt(self.project, first)
        self.assertEqual(payload["baseline"], first)
        row = dict(zip(payload["columns"], next(r for r in payload["rows"] if r[0] == self.a)))
        self.assertEqual(row["base_start"], day(7))
        self.assertEqual(dict(zip(payload["columns"], next(r for r in schedule.gantt(self.project, second)["rows"] if r[0] == self.a)))["base_start"], day(8))

    def test_the_plan_line_follows_the_baseline(self):
        self.assertEqual(baseline.planned_on(self.project, day(9), 42.0), 42.0)  # no baseline yet: the straight line
        baseline.capture(self.project)
        at_start, at_end = baseline.planned_on(self.project, day(7), 0), baseline.planned_on(self.project, day(15), 0)
        self.assertGreater(at_end, at_start)
        self.assertEqual(at_end, 100)
        self.assertEqual(baseline.planned_on(self.project, "2029-12-01", 0), 0)
        self.assertEqual(baseline.interpolate([{"day": day(1), "value": 0}, {"day": day(11), "value": 50}], day(6)), 25)

    def test_the_chart_runs_to_the_end_of_the_plan(self):
        baseline.capture(self.project)
        rows = baseline.curve_for_chart(self.project, [{"snapshot_date": day(8), "progress": 10, "planned_progress": 99}])
        self.assertEqual(rows[-1]["snapshot_date"], day(15))
        self.assertIsNone(rows[-1]["progress"])
        actual = next(r for r in rows if r["snapshot_date"] == day(8))
        self.assertEqual(actual["progress"], 10)
        self.assertLess(actual["planned_progress"], 99)  # the plan comes from the baseline
        no_baseline = make_project("SC chưa chụp")
        same = [{"snapshot_date": day(8), "progress": 10, "planned_progress": 99}]
        self.assertEqual(baseline.curve_for_chart(no_baseline, same), same)

    def test_scope(self):
        name = baseline.capture(self.project)["name"]
        doc = frappe.get_doc("PM Baseline", name)
        self.assertTrue(frappe.has_permission("PM Baseline", "read", doc=doc, user=ENGINEER))
        self.assertFalse(frappe.has_permission("PM Baseline", "read", doc=doc, user=OUTSIDER))
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, baseline.compare, name)
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, baseline.list_baselines, self.project)
        self.assertEqual(as_user(OUTSIDER, frappe.get_list, "PM Baseline Task", filters={"baseline": name}), [])

    def test_overview_says_how_the_schedule_stands(self):
        baseline.capture(self.project)
        schedule.refresh(self.project)
        view = as_user(MANAGER, projects.overview, self.project)
        self.assertEqual(view["schedule"]["links"], 3)
        self.assertEqual(view["schedule"]["baseline_title"], "Baseline 1")

