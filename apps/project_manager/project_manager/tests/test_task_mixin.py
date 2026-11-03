"""M1: ERPNext's Task adapted by the mixin — contract with ERPNext and the behaviour that replaces its own.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_task_mixin
"""

import frappe
from frappe.utils import add_days, nowdate

from erpnext.projects.doctype.task.task import Task as ERPNextTask
from project_manager.project_manager.overrides.task import OVERRIDDEN, TIMESHEET_FLAG, PMTaskMixin
from project_manager.project_manager.services import wbs
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import TAG, PMTestCase, drop_project, make_project, make_task


def field(task, name):
    return frappe.db.get_value("Task", task, name)


class TestTaskMixin(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        cls.a = make_project("TM A")
        cls.b = make_project("TM B")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.a)
        drop_project(cls.b)
        frappe.db.commit()
        super().tearDownClass()

    # --- contract with ERPNext --------------------------------------------------------------------------------

    def test_every_overridden_method_still_exists_in_erpnext(self):
        missing = [name for name in OVERRIDDEN if not callable(getattr(ERPNextTask, name, None))]
        self.assertEqual(missing, [], "ERPNext renamed or removed methods the mixin replaces: review overrides/task.py")

    def test_the_mixin_is_in_force(self):
        doc = frappe.new_doc("Task")
        self.assertIsInstance(doc, PMTaskMixin)
        self.assertIsInstance(doc, ERPNextTask)

    # --- tree kept per project --------------------------------------------------------------------------------

    def test_tree_paths(self):
        phase = make_task(self.a, "Giai đoạn 1", is_group=1)
        first = make_task(self.a, "Việc 1", parent=phase)
        second = make_task(self.a, "Việc 2", parent=phase)
        root2 = make_task(self.a, "Giai đoạn 2", is_group=1)
        self.assertEqual(field(phase, "pm_wbs_code"), "1")
        self.assertEqual(field(first, "pm_wbs_code"), "1.1")
        self.assertEqual(field(second, "pm_wbs_code"), "1.2")
        self.assertEqual(field(root2, "pm_wbs_code"), "2")
        self.assertEqual(field(second, "pm_path"), "00001.00002")
        self.assertEqual(field(second, "pm_level"), 2)
        ordered = frappe.get_all("Task", filters={"project": self.a, "name": ["in", [phase, first, second, root2]]},
                                 pluck="name", order_by="pm_path asc")
        self.assertEqual(ordered, [phase, first, second, root2])

    def test_no_global_renumbering(self):
        before = frappe.db.sql("select name, lft, rgt, modified from `tabTask` where project = %s", self.a)
        make_task(self.b, "Việc ở dự án B")
        after = frappe.db.sql("select name, lft, rgt, modified from `tabTask` where project = %s", self.a)
        self.assertEqual(before, after)
        task = make_task(self.b, "Việc khác")
        self.assertEqual((field(task, "lft"), field(task, "rgt")), (0, 0))

    def test_children_do_not_save_their_parent(self):
        phase = make_task(self.a, "Giai đoạn", is_group=1)
        modified = field(phase, "modified")
        make_task(self.a, "Việc", parent=phase)
        self.assertEqual(field(phase, "modified"), modified)
        self.assertEqual(frappe.get_all("Task Depends On", filters={"parent": phase}), [])

    def test_moving_carries_the_subtree(self):
        p1 = make_task(self.a, "P1", is_group=1)
        p2 = make_task(self.a, "P2", is_group=1)
        group = make_task(self.a, "Nhóm", parent=p1, is_group=1)
        leaf = make_task(self.a, "Lá", parent=group)
        doc = frappe.get_doc("Task", group)
        doc.parent_task = p2
        doc.save(ignore_permissions=True)
        p2_path = field(p2, "pm_path")
        self.assertEqual(field(group, "pm_path"), f"{p2_path}.00001")
        self.assertEqual(field(leaf, "pm_path"), f"{p2_path}.00001.00001")
        self.assertEqual(field(leaf, "pm_wbs_code"), f"{field(p2, 'pm_wbs_code')}.1.1")
        self.assertEqual(field(leaf, "pm_level"), 3)

    def test_a_task_cannot_move_into_its_own_branch(self):
        top = make_task(self.a, "Trên", is_group=1)
        below = make_task(self.a, "Dưới", parent=top, is_group=1)
        doc = frappe.get_doc("Task", top)
        doc.parent_task = below
        self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)

    def test_parent_must_be_in_the_same_project(self):
        parent = make_task(self.a, "Cha", is_group=1)
        self.assertRaises(frappe.ValidationError, make_task, self.b, "Con lạc", parent=parent)

    def test_rebuild_numbers_again(self):
        top = make_task(self.a, "R", is_group=1)
        kids = [make_task(self.a, f"R{i}", parent=top) for i in range(3)]
        frappe.db.set_value("Task", kids[1], "pm_path", "", update_modified=False)
        count = wbs.rebuild(self.a)
        self.assertGreaterEqual(count, 4)
        self.assertEqual([field(k, "pm_wbs_code").split(".")[-1] for k in kids], ["1", "2", "3"])

    # --- ERPNext behaviour turned off -------------------------------------------------------------------------

    def test_a_child_may_end_after_its_parent(self):
        parent = make_task(self.a, "Cha ngắn", is_group=1, exp_start_date=nowdate(), exp_end_date=add_days(nowdate(), 2))
        make_task(self.a, "Con dài", parent=parent, exp_start_date=nowdate(), exp_end_date=add_days(nowdate(), 30))

    def test_status_is_never_rewritten_to_overdue(self):
        task = make_task(self.a, "Trễ", exp_start_date=add_days(nowdate(), -10), exp_end_date=add_days(nowdate(), -1))
        frappe.get_doc("Task", task).update_status()
        self.assertEqual(field(task, "status"), "Open")
        self.assertEqual(frappe.db.get_value("Scheduled Job Type", {"method": install.ERPNEXT_OVERDUE_JOB}, "stopped"), 1)

    def test_timesheet_does_not_override_the_status(self):
        task = make_task(self.a, "Chấm công", status="Working", progress=40)
        doc = frappe.get_doc("Task", task)
        doc.status, doc.progress = "Completed", 100
        frappe.flags[TIMESHEET_FLAG] = True
        try:
            doc.save(ignore_permissions=True)
        finally:
            frappe.flags[TIMESHEET_FLAG] = False
        self.assertEqual((field(task, "status"), field(task, "progress")), ("Working", 40))
        doc = frappe.get_doc("Task", task)
        doc.progress = 60
        doc.save(ignore_permissions=True)
        self.assertEqual(field(task, "progress"), 60)

    def test_tag_is_unique_per_run(self):
        self.assertEqual(len(TAG), 5)
