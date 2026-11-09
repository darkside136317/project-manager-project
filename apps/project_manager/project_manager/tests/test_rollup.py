"""M2: progress roll-up — groups and the project follow their children, incrementally, and the nightly reconcile
finds nothing to correct.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_rollup
"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.services import rollup
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import PMTestCase, drop_project, make_project, make_task


def values(task, *fields):
    return frappe.db.get_value("Task", task, list(fields), as_dict=True)


def set_progress(task, progress, status=None):
    doc = frappe.get_doc("Task", task)
    doc.progress = progress
    doc.status = status or (C.COMPLETED if progress >= 100 else C.WORKING if progress else C.OPEN)
    doc.save(ignore_permissions=True)


class TestRollup(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        cls.project = make_project("RU")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.project)
        frappe.db.commit()
        super().tearDownClass()

    def tree(self, start=None):
        """phase / (a: 2 days, b: 8 days) and phase2 / sub / c (10 days) + a milestone."""
        start = start or nowdate()
        phase = make_task(self.project, "Móng", is_group=1)
        a = make_task(self.project, "Đào đất", parent=phase, exp_start_date=start, exp_end_date=add_days(start, 1))
        b = make_task(self.project, "Đổ bê tông", parent=phase, exp_start_date=start, exp_end_date=add_days(start, 7))
        phase2 = make_task(self.project, "Thân", is_group=1)
        sub = make_task(self.project, "Tầng 1", parent=phase2, is_group=1)
        c = make_task(self.project, "Cột", parent=sub, exp_start_date=add_days(start, 8), exp_end_date=add_days(start, 17))
        milestone = make_task(self.project, "Bàn giao móng", parent=phase, pm_node_type="Mốc",
                              exp_start_date=add_days(start, 8), exp_end_date=add_days(start, 8))
        rollup.reconcile(self.project)
        return frappe._dict(phase=phase, a=a, b=b, phase2=phase2, sub=sub, c=c, milestone=milestone)

    def test_duration_weights(self):
        t = self.tree()
        self.assertEqual(flt(values(t.a, "pm_rollup_weight").pm_rollup_weight), 2)
        self.assertEqual(flt(values(t.b, "pm_rollup_weight").pm_rollup_weight), 8)
        self.assertEqual(flt(values(t.milestone, "pm_rollup_weight").pm_rollup_weight), 0)
        set_progress(t.a, 100)
        rollup.recompute(self.project, {t.phase})
        phase = values(t.phase, "progress", "status", "pm_rollup_weight", "exp_start_date", "exp_end_date")
        self.assertEqual(flt(phase.progress), 20)  # 2 of 10 days done
        self.assertEqual(phase.status, C.WORKING)
        self.assertEqual(flt(phase.pm_rollup_weight), 10)
        self.assertEqual(getdate(phase.exp_end_date), getdate(add_days(nowdate(), 8)))  # the milestone ends last
        # the project: 2 done of 20 weighted days
        self.assertEqual(flt(frappe.db.get_value("Project", self.project, "percent_complete")), 10)

    def test_every_level_up_to_the_project(self):
        t = self.tree()
        set_progress(t.c, 50)
        rollup.recompute(self.project, {t.sub})
        self.assertEqual(flt(values(t.sub, "progress").progress), 50)
        self.assertEqual(flt(values(t.phase2, "progress").progress), 50)
        self.assertEqual(flt(frappe.db.get_value("Project", self.project, "percent_complete")), 25)

    def test_equal_and_weight_methods(self):
        frappe.db.set_value("Project", self.project, "pm_rollup_method", C.ROLLUP_EQUAL)
        t = self.tree()
        set_progress(t.a, 100)
        rollup.recompute(self.project, {t.phase})
        self.assertEqual(flt(values(t.phase, "progress").progress), 50)  # 1 of 2 counted tasks (milestone weighs 0)

        frappe.db.set_value("Project", self.project, "pm_rollup_method", C.ROLLUP_WEIGHT)
        frappe.db.set_value("Task", t.a, "task_weight", 3)
        frappe.db.set_value("Task", t.b, "task_weight", 1)
        rollup.reconcile(self.project)
        self.assertEqual(flt(values(t.phase, "progress").progress), 75)

    def test_group_status(self):
        t = self.tree()
        self.assertEqual(values(t.phase, "status").status, C.OPEN)
        set_progress(t.a, 100)
        set_progress(t.b, 100)
        frappe.db.set_value("Task", t.milestone, "status", C.COMPLETED)
        rollup.recompute(self.project, {t.phase})
        self.assertEqual(values(t.phase, "status").status, C.COMPLETED)
        self.assertEqual(flt(values(t.phase, "progress").progress), 100)
        # a cancelled child no longer counts
        set_progress(t.c, 0, C.CANCELLED)
        rollup.recompute(self.project, {t.sub})
        self.assertEqual(values(t.sub, "status").status, C.CANCELLED)

    def test_saving_a_task_marks_its_parent(self):
        t = self.tree()
        frappe.cache.delete_value(rollup._key(self.project))
        with patch("frappe.enqueue") as enqueue:
            set_progress(t.c, 40)
            frappe.db.after_commit.run()
        self.assertIn(t.sub, {m.decode() if isinstance(m, bytes) else m
                              for m in frappe.cache.smembers(rollup._key(self.project))})
        self.assertTrue(any(c.kwargs.get("job_id") == f"pm-rollup:{self.project}" and c.kwargs.get("deduplicate")
                            and c.kwargs.get("queue") == "pm" for c in enqueue.call_args_list))
        rollup.process(self.project)
        self.assertEqual(flt(values(t.phase2, "progress").progress), 40)
        self.assertFalse(frappe.cache.smembers(rollup._key(self.project)))

    def test_a_mark_while_the_job_runs_queues_a_follow_up(self):
        """The running job may already have looked at the dirty set for the last time: one more job runs after it."""
        from rq.job import JobStatus

        t = self.tree()
        with patch("frappe.enqueue") as enqueue,                 patch("frappe.utils.background_jobs.get_job_status", return_value=JobStatus.STARTED):
            set_progress(t.c, 55)
            frappe.db.after_commit.run()
        self.assertTrue(any(c.kwargs.get("job_id") == f"pm-rollup:{self.project}:next" and c.kwargs.get("deduplicate")
                            for c in enqueue.call_args_list))

    def test_a_failed_job_keeps_the_work_for_the_sweeper(self):
        t = self.tree()
        frappe.cache.delete_value(rollup._key(self.project))
        frappe.cache.sadd(rollup._key(self.project), t.sub)
        with patch.object(rollup, "_recompute", side_effect=RuntimeError("boom")),                 patch.object(frappe.db, "rollback"), self.assertRaises(RuntimeError):  # the job's own rollback
            rollup.process(self.project)
        self.assertTrue(frappe.cache.smembers(rollup._key(self.project)))
        frappe.cache.delete_value(rollup._key(self.project))

    def test_moving_a_task_recomputes_both_parents(self):
        t = self.tree()
        set_progress(t.b, 100)
        rollup.reconcile(self.project)
        doc = frappe.get_doc("Task", t.b)
        doc.parent_task = t.sub
        doc.save(ignore_permissions=True)
        rollup.recompute(self.project, {t.phase, t.sub})
        self.assertEqual(flt(values(t.phase, "progress").progress), 0)  # only a (2 days, 0 %) is left
        self.assertEqual(flt(values(t.sub, "progress").progress), round(800 / 18, 2))

    def test_reconcile_finds_and_fixes_drift(self):
        t = self.tree()
        set_progress(t.c, 60)
        self.assertEqual(rollup.reconcile(self.project) > 0, True)
        self.assertEqual(rollup.reconcile(self.project), 0)  # nothing left to correct
        frappe.db.set_value("Task", t.phase2, "progress", 3, update_modified=False)
        self.assertEqual(rollup.reconcile(self.project), 1)
        self.assertEqual(flt(values(t.phase2, "progress").progress), 60)

    def test_lateness(self):
        t = self.tree(start=add_days(nowdate(), -10))
        late = values(t.a, "pm_is_overdue", "pm_delay_days")
        self.assertEqual((late.pm_is_overdue, late.pm_delay_days), (1, 9))  # set on save
        frappe.db.set_value("Task", t.a, {"pm_is_overdue": 0, "pm_delay_days": 0})
        rollup.refresh_overdue_flags()  # and every day
        late = values(t.a, "pm_is_overdue", "pm_delay_days")
        self.assertEqual((late.pm_is_overdue, late.pm_delay_days), (1, 9))
        set_progress(t.a, 100)
        self.assertEqual(values(t.a, "pm_is_overdue").pm_is_overdue, 0)
        frappe.db.set_value("Task", t.b, "pm_is_overdue", 1)
        frappe.db.set_value("Task", t.b, "exp_end_date", add_days(nowdate(), 3))
        rollup.refresh_overdue_flags()
        self.assertEqual(values(t.b, "pm_is_overdue").pm_is_overdue, 0)
        # the status is never rewritten
        self.assertNotEqual(values(t.c, "status").status, "Overdue")

    def test_daily_snapshot_is_one_row_per_day(self):
        self.tree()
        rollup.take_snapshots()
        rollup.take_snapshots()
        rows = frappe.get_all("PM Snapshot", filters={"project": self.project, "snapshot_date": nowdate()},
                              fields=["task", "total_tasks"])
        project_rows = [r for r in rows if not r.task]
        self.assertEqual(len(project_rows), 1)
        self.assertEqual(project_rows[0].total_tasks, 4)  # a, b, c, milestone
        self.assertEqual(len([r for r in rows if r.task]), 2)  # the two phases

    def test_planned_progress(self):
        self.assertEqual(rollup.planned_progress("2026-01-01", "2026-01-11", "2026-01-06"), 50)
        self.assertEqual(rollup.planned_progress("2026-01-01", "2026-01-11", "2025-12-01"), 0)
        self.assertEqual(rollup.planned_progress("2026-01-01", "2026-01-11", "2026-02-01"), 100)
