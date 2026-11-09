"""M6: reading a BOQ from Excel, keeping versions, and the WBS that follows the approved one.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_boq
"""

import frappe
from frappe.utils import flt

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import boq, boq_import
from pm_construction.tests.construction_helpers import (
    ENGINEER,
    MANAGER,
    OUTSIDER,
    ConstructionBase,
    as_user,
    sheet,
)


class TestReading(ConstructionBase):
    def test_the_sample_sheet(self):
        parsed = boq_import.parse(boq_import.template_file())
        self.assertEqual((parsed["sections"], parsed["works"]), (5, 12))
        self.assertEqual(parsed["issues"], [])
        by_code = {item["code"]: item for item in parsed["items"]}
        self.assertEqual([by_code[c]["level"] for c in ("A", "B", "I", "II", "C")], [1, 1, 2, 2, 1])
        self.assertEqual(by_code["I"]["parent_line"], by_code["B"]["line_no"])  # I, II under B
        self.assertEqual(by_code["9"]["parent_line"], by_code["II"]["line_no"])
        self.assertEqual(by_code["C"]["parent_line"], 0)  # C follows B: a letter, not the Roman 100
        self.assertAlmostEqual(by_code["3"]["amount"], 4.25 * 23_800_000)
        self.assertEqual(parsed["total"], sum(i["amount"] for i in parsed["items"] if not i["is_group"]))

    def test_numbers_written_either_way(self):
        cases = {"1.234,5": 1234.5, "1,234.5": 1234.5, "12,5": 12.5, "1.234.567": 1234567.0, "1,234,567": 1234567.0,
                 "86.4": 86.4, 86.4: 86.4, "": None, "-": None, "abc": None}
        for value, expected in cases.items():
            self.assertEqual(boq_import.number(value), expected, value)

    def test_other_layouts(self):
        content = sheet([("1", "AB.111", "Đào đất", "m3", "1.234,5", "100.000", None),
                         ("", "", "Tổng cộng", "", None, None, "123450000")],
                        header=("TT", "Mã số", "Tên công việc", "ĐVT", "KL", "Đơn giá", "Giá trị"),
                        above=[("BẢNG DỰ TOÁN CHI TIẾT",), ("Công trình: Nhà xưởng",), ()])
        parsed = boq_import.parse(content)
        self.assertEqual(parsed["works"], 1)  # the total row is not a work item
        item = parsed["items"][0]
        self.assertEqual((item["norm_code"], item["uom"], item["qty"], item["unit_price"]), ("AB.111", "m3", 1234.5, 100000))
        self.assertEqual(item["amount"], 123450000)

    def test_problems_are_reported(self):
        content = sheet([("1", "", "Bê tông", "m3", 10, 1000, 99999), ("2", "", "Cốt thép", "", 0, 5, 0)])
        messages = [issue["message"] for issue in boq_import.parse(content)["issues"]]
        self.assertTrue(any("khác khối lượng × đơn giá" in m for m in messages))
        self.assertTrue(any("khối lượng bằng 0" in m for m in messages))
        self.assertTrue(any("thiếu đơn vị" in m for m in messages))
        with self.assertRaises(frappe.ValidationError):
            boq_import.parse(sheet([("1", "x")], header=("STT", "Ghi chú")))  # no header found
        with self.assertRaises(frappe.ValidationError):
            boq_import.parse(sheet([("A", "", "PHẦN MÓNG", "", None, None, None)]))  # sections only
        with self.assertRaises(frappe.ValidationError):
            boq_import.parse(b"not an excel file")


class TestVersions(ConstructionBase):
    def test_preview_writes_nothing(self):
        result = as_user(MANAGER, boq.preview, self.project, boq_import.template_file())
        self.assertEqual((result["works"], result["next_version"]), (12, 1))
        self.assertEqual(frappe.db.count("PMC BOQ", {"project": self.project}), 0)

    def test_approving_builds_the_wbs(self):
        tasks = self.approved_sample()
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_rollup_method"), K.ESTIMATE_METHOD)
        section = frappe.db.get_value("Task", tasks["PHẦN MÓNG"], ["is_group", "pm_node_type"], as_dict=True)
        self.assertEqual((section.is_group, section.pm_node_type), (1, K.NODE_SECTION))
        work = frappe.db.get_value("Task", tasks["Bê tông móng đá 1x2, mác 250"],
                                   ["pm_node_type", "pmc_uom", "pmc_planned_qty", "pmc_unit_price", "pmc_estimate_value",
                                    "pmc_norm_code", "pm_rollup_weight", "parent_task"], as_dict=True)
        self.assertEqual((work.pm_node_type, work.pmc_uom, work.pmc_planned_qty), (K.NODE_WORK, "m3", 38.5))
        self.assertEqual(flt(work.pmc_estimate_value), 38.5 * 1_950_000)
        self.assertEqual(flt(work.pm_rollup_weight), flt(work.pmc_estimate_value))  # weighed by estimate value
        self.assertEqual(work.parent_task, tasks["PHẦN MÓNG"])
        self.assertEqual(frappe.db.get_value("Task", tasks["Kết cấu"], "parent_task"), tasks["PHẦN THÂN"])
        items = frappe.get_all("PMC BOQ Item", filters={"project": self.project, "is_group": 0}, pluck="task")
        self.assertTrue(all(items))

    def test_a_new_version_updates_adds_and_reports(self):
        tasks = self.approved_sample()
        rows = [list(r) for r in boq_import.SAMPLE if r[2] != "Ván khuôn móng băng"]  # a line removed
        for row in rows:
            if row[2] == "Bê tông móng đá 1x2, mác 250":
                row[4] = 42.0  # a quantity changed
        rows.insert(5, ["5a", "AF.11000", "Bê tông giằng móng", "m3", 5.0, 2_000_000])  # a line added, in A
        content = sheet([(*r, (r[4] * r[5]) if r[4] is not None else None) for r in rows])
        version = as_user(MANAGER, boq.import_version, self.project, content, "v2.xlsx", "Điều chỉnh")
        self.assertEqual(version.version_no, 2)
        result = as_user(MANAGER, boq.approve, version.name)["sync"]
        self.assertEqual(result["created"], 1)
        self.assertGreaterEqual(result["updated"], 1)
        self.assertEqual(result["missing"], [tasks["Ván khuôn móng băng"]])
        self.assertTrue(frappe.db.exists("Task", tasks["Ván khuôn móng băng"]))  # kept: it may have history
        self.assertEqual(frappe.db.get_value("Task", tasks["Bê tông móng đá 1x2, mác 250"], "pmc_planned_qty"), 42.0)
        added = frappe.db.get_value("Task", {"project": self.project, "subject": "Bê tông giằng móng"},
                                    ["parent_task", "pmc_planned_qty"], as_dict=True)
        self.assertEqual((added.parent_task, added.pmc_planned_qty), (tasks["PHẦN MÓNG"], 5.0))
        states = dict(frappe.get_all("PMC BOQ", filters={"project": self.project}, fields=["version_no", "status"],
                                     as_list=True))
        self.assertEqual(states, {1: K.BOQ_REPLACED, 2: K.BOQ_APPROVED})
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, boq.approve, version.name)  # approved once

    def test_who_may_import_and_read(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, boq.import_version, self.project, boq_import.template_file())
        version = as_user(MANAGER, boq.import_version, self.project, boq_import.template_file())
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, boq.approve, version.name)
        self.assertEqual(len(as_user(ENGINEER, boq.versions, self.project)["versions"]), 1)
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, boq.versions, self.project)
        self.assertFalse(as_user(OUTSIDER, frappe.get_list, "PMC BOQ Item", filters={"project": self.project}))
