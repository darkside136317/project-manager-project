"""M2: the WBS — add, move, renumber, cancel, delete; a project from a template; import from Excel.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_tree
"""

import io

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import assignments, progress, projects, tree, wbs_import
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

MANAGER = f"tr.manager.{TAG}@example.com"
ENGINEER = f"tr.engineer.{TAG}@example.com"
USERS = (MANAGER, ENGINEER)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


def codes(project):
    return {r.subject: r.pm_wbs_code for r in frappe.get_all("Task", filters={"project": project},
                                                             fields=["subject", "pm_wbs_code"])}


def workbook(rows) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(wbs_import.HEADERS)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class TestTree(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        make_user(MANAGER, [C.STAFF_ROLE, C.DIRECTOR_ROLE])
        make_user(ENGINEER, [C.STAFF_ROLE])
        cls.project = make_project("TR")
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        cls.created = []
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for project in [cls.project, *frappe.get_all("Project", filters={"project_name": ["like", f"%{TAG}%"]},
                                                    pluck="name")]:
            drop_project(project)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def test_adding_under_a_leaf_makes_it_a_group(self):
        phase = as_user(MANAGER, tree.add, self.project, "Móng")
        self.assertEqual(phase["is_group"], 0)
        child = as_user(MANAGER, tree.add, self.project, "Đào đất", parent=phase["name"])
        self.assertEqual(frappe.db.get_value("Task", phase["name"], "is_group"), 1)
        self.assertEqual(child["pm_wbs_code"], f"{phase['pm_wbs_code']}.1")
        level = as_user(ENGINEER, tree.children, self.project, phase["name"])
        self.assertEqual([r.name for r in level["rows"]], [child["name"]])
        self.assertFalse(level["can_plan"])
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, tree.add, self.project, "Việc lạ")

    def test_a_reported_leaf_is_not_split(self):
        leaf = make_task(self.project, "Lắp cốp pha")
        progress.report(leaf, 10)
        with self.assertRaises(frappe.ValidationError):
            tree.add(self.project, "Con", parent=leaf)

    def test_move_and_reorder(self):
        a = make_task(self.project, "A", is_group=1)
        b = make_task(self.project, "B", is_group=1)
        make_task(self.project, "A1", parent=a)
        a2 = make_task(self.project, "A2", parent=a, is_group=1)
        a21 = make_task(self.project, "A21", parent=a2)
        base = codes(self.project)["A"].split(".")[0]
        as_user(MANAGER, tree.move, a2, b)  # A2 (with A21) under B
        after = codes(self.project)
        b_code = after["B"]
        self.assertEqual((after["A2"], after["A21"]), (f"{b_code}.1", f"{b_code}.1.1"))
        as_user(MANAGER, tree.move, a2, a, 0)  # back under A, first
        after = codes(self.project)
        self.assertEqual((after["A2"], after["A21"], after["A1"]), (f"{base}.1", f"{base}.1.1", f"{base}.2"))
        paths = dict(frappe.get_all("Task", filters={"project": self.project}, fields=["subject", "pm_path"],
                                    as_list=True))
        self.assertTrue(paths["A21"].startswith(paths["A2"] + "."))
        self.assertLess(paths["A2"], paths["A1"])
        self.assertEqual(frappe.db.get_value("Task", a21, "pm_level"), 3)

    def test_cancel_or_delete(self):
        leaf = make_task(self.project, "Sơn tường")
        fresh = make_task(self.project, "Việc nhập nhầm")
        assignments.assign(leaf, C.RESPONSIBLE, user=ENGINEER)
        with self.assertRaises(frappe.ValidationError):
            tree.delete(leaf)
        with self.assertRaises(frappe.ValidationError):
            tree.cancel(leaf, "")
        tree.cancel(leaf, "Chủ đầu tư bỏ hạng mục")
        row = frappe.db.get_value("Task", leaf, ["status", "pm_rollup_weight"], as_dict=True)
        self.assertEqual((row.status, flt(row.pm_rollup_weight)), (C.CANCELLED, 0))
        self.assertEqual(frappe.db.count("PM Task Assignment", {"task": leaf, "is_active": 1}), 0)
        tree.delete(fresh)
        self.assertFalse(frappe.db.exists("Task", fresh))

    def test_project_from_a_template(self):
        template = make_project("Mẫu nhà phố")
        frappe.db.set_value("Project", template, {"pm_is_template": 1, "expected_start_date": "2026-01-01",
                                                  "expected_end_date": "2026-03-31"})
        phase = make_task(template, "Phần móng", is_group=1)
        make_task(template, "Đào móng", parent=phase, exp_start_date="2026-01-05", exp_end_date="2026-01-09")
        sub = make_task(template, "Bê tông", parent=phase, is_group=1)
        make_task(template, "Đổ bê tông lót", parent=sub, exp_start_date="2026-01-10", exp_end_date="2026-01-11")
        make_task(template, "Phần thân", is_group=1)
        start = getdate(nowdate())
        created = as_user(MANAGER, projects.create, {"project_name": f"Nhà phố Q7 {TAG}", "expected_start_date": start},
                          template)
        self.assertEqual(created["tasks"], 5)
        new = created["name"]
        self.assertEqual(codes(new), codes(template))
        dig = frappe.get_all("Task", filters={"project": new, "subject": "Đào móng"},
                             fields=["exp_start_date", "exp_end_date", "status", "progress", "pm_level"])[0]
        self.assertEqual(date_diff(dig.exp_start_date, start), 4)
        self.assertEqual((dig.status, flt(dig.progress), dig.pm_level), (C.OPEN, 0, 2))
        project = frappe.db.get_value("Project", new, ["expected_end_date", "pm_manager", "pm_is_template"], as_dict=True)
        self.assertEqual(getdate(project.expected_end_date), getdate(add_days(start, 89)))
        self.assertEqual((project.pm_manager, project.pm_is_template), (MANAGER, 0))
        self.assertTrue(frappe.db.exists("PM Project Member", {"project": new, "user": MANAGER,
                                                               "project_role": "Quản lý dự án"}))
        # the copied groups were rolled up: the phase spans its children
        phase_row = frappe.get_all("Task", filters={"project": new, "subject": "Phần móng"},
                                   fields=["exp_start_date", "exp_end_date", "pm_rollup_weight"])[0]
        self.assertEqual(date_diff(phase_row.exp_end_date, phase_row.exp_start_date), 6)
        self.assertEqual(flt(phase_row.pm_rollup_weight), 7)
        # a later task gets the next number in the series
        later = make_task(new, "Thêm")
        self.assertNotIn(later, frappe.get_all("Task", filters={"project": template}, pluck="name"))
        self.assertEqual(frappe.db.get_value("Task", later, "pm_wbs_code"), "3")
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, projects.create, {"project_name": f"Không được {TAG}"})

    def test_import_preview_shows_every_problem(self):
        content = workbook([
            ["1", "Phần móng", "Giai đoạn", None, None, None, None, None],
            ["1.1", "Đào đất", None, "05/01/2026", "03/01/2026", None, "ai.do@nowhere", None],
            ["2.1", "Mồ côi", None, None, None, None, None, None],
            ["x", "", "Loại lạ", None, None, None, None, None],
            ["1", "Trùng", None, None, None, None, None, None],
        ])
        result = as_user(MANAGER, wbs_import.preview, self.project, content)
        by_line = {r["line"]: r for r in result["rows"]}
        self.assertTrue(any("Ngày kết thúc" in e for e in by_line[3]["errors"]))
        self.assertTrue(by_line[3]["warnings"])  # not a member: not assigned
        self.assertTrue(any("2" in e for e in by_line[4]["errors"]))
        self.assertGreaterEqual(len(by_line[5]["errors"]), 2)
        self.assertTrue(by_line[5]["warnings"])  # unknown node type
        self.assertTrue(by_line[6]["errors"])  # duplicate code
        self.assertEqual(result["errors"], 4)
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, wbs_import.run, self.project, content)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, wbs_import.preview, self.project, content)

    def test_import_writes_the_tree_and_the_owners(self):
        project = make_project("Nhập Excel")
        add_member(project, MANAGER, "Quản lý dự án")
        add_member(project, ENGINEER, "Kỹ sư")
        content = workbook([
            ["1", "Phần móng", "Giai đoạn", None, None, None, None, None],
            ["1.1", "Đào đất", None, "05/01/2026", "09/01/2026", None, ENGINEER, "Dùng máy đào"],
            ["1.2", "Bê tông lót", None, "10/01/2026", "11/01/2026", 2, frappe.utils.get_fullname(ENGINEER), None],
            ["2", "Phần thân", None, None, None, None, None, None],
            ["2.1", "Cột tầng 1", None, "12/01/2026", "20/01/2026", None, None, None],
        ])
        result = as_user(MANAGER, wbs_import.run, project, content)
        self.assertEqual(result, {"tasks": 5, "assigned": 2})
        rows = {r.subject: r for r in frappe.get_all(
            "Task", filters={"project": project},
            fields=["subject", "pm_wbs_code", "is_group", "pm_accountable", "exp_end_date", "description",
                    "pm_node_type"])}
        self.assertEqual(rows["Bê tông lót"].pm_wbs_code, "1.2")
        self.assertEqual((rows["Phần móng"].is_group, rows["Phần móng"].pm_node_type), (1, "Giai đoạn"))
        self.assertEqual(rows["Đào đất"].pm_accountable, ENGINEER)
        self.assertEqual(rows["Đào đất"].description, "Dùng máy đào")
        self.assertEqual(getdate(rows["Phần thân"].exp_end_date), getdate("2026-01-20"))  # rolled up
        self.assertEqual(wbs_import.template_file()[:2], b"PK")
