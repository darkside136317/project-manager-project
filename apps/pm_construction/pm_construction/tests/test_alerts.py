"""M7 in the construction layer: a phase passes by itself once every work item is accepted in full, and the alert of a
missing site diary.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_alerts
"""

import json

import frappe
from frappe.utils import nowdate
from project_manager.project_manager.services import alerts, forms, phases, rollup
from project_manager.project_manager.setup import install as core_install
from project_manager.tests.helpers import memory_store

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import acceptance, diary
from pm_construction.pm_construction.services import alerts as layer_alerts
from pm_construction.tests.construction_helpers import (
    COMMANDER,
    ENGINEER,
    MANAGER,
    ConstructionBase,
    as_user,
)

PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
FOUNDATION = "PHẦN MÓNG"


class LayerAlertBase(ConstructionBase):
    def setUp(self):
        super().setUp()
        self.store = memory_store(self)
        self.tasks = self.approved_sample()
        frappe.db.set_value("Project", self.project, {"pm_state": "Đang thực hiện", "expected_start_date": None})
        self.phase = frappe.db.get_value("Task", {"project": self.project, "subject": FOUNDATION, "is_group": 1}, "name")
        self.works = frappe.get_all("Task", filters={"project": self.project, "is_group": 0,
                                                     "pm_path": ["like", frappe.db.get_value("Task", self.phase, "pm_path") + ".%"]},
                                    fields=["name", "subject", "pmc_planned_qty"], order_by="pm_path asc")

    def diary_of(self, day, rows):
        saved = as_user(ENGINEER, diary.save, self.project, day, {"weather": "Nắng", "workers": 10,
                                                                  "work_summary": "Dọn mặt bằng"}, rows)
        return as_user(ENGINEER, diary.submit, saved["name"])

    def accept(self, work) -> str:
        def fill():
            name = forms.start(K.QTY_ACCEPTANCE_CODE, self.project, work.name)["name"]
            signature = forms.attach(name, PIXEL, "ky.png")
            forms.submit(name, {"ngay_nghiem_thu": nowdate(), K.QTY_FIELD: work.pmc_planned_qty,
                                "thanh_phan_truc_tiep_nghiem_thu": [{"ho_va_ten": "Nguyễn A"}],
                                "chat_luong_cong_viec": [{"ket_qua": "Đạt"} for _ in range(4)],
                                "ket_luan": "Chấp nhận nghiệm thu",
                                "dai_dien_nha_thau_ky": [signature], "dai_dien_tu_van_giam_sat_ky": [signature]})
            return name

        return as_user(ENGINEER, fill)


class TestPhaseByAcceptance(LayerAlertBase):
    def test_the_foundation_passes_when_its_last_acceptance_is_approved(self):
        frappe.db.set_value("Task", self.phase, "pm_gate_mode", phases.AUTO)
        self.diary_of(nowdate(), [{"task": w.name, "qty": w.pmc_planned_qty} for w in self.works])
        rollup.reconcile(self.project)
        self.assertEqual(frappe.db.get_value("Task", self.phase, "status"), "Completed")
        result = phases.check(self.project)
        self.assertEqual(result["missing"], [f"còn {len(self.works)} công tác chưa nghiệm thu đủ khối lượng"])
        records = [self.accept(work) for work in self.works]
        for record in records[:-1]:
            as_user(COMMANDER, forms.approve, record)
        self.assertEqual(acceptance.gate_check(frappe._dict(project=self.project, pm_path=frappe.db.get_value(
            "Task", self.phase, "pm_path"))), ["còn 1 công tác chưa nghiệm thu đủ khối lượng"])
        self.assertNotEqual(frappe.db.get_value("Task", self.phase, "pm_gate_state"), phases.PASSED)
        as_user(COMMANDER, forms.approve, records[-1])  # the last one: the phase passes by itself
        self.assertEqual(frappe.db.get_value("Task", self.phase, "pm_gate_state"), phases.PASSED)
        following = frappe.db.get_value("Project", self.project, "pm_current_phase")
        self.assertEqual(frappe.db.get_value("Task", following, "subject"), "PHẦN THÂN")
        self.assertTrue(frappe.db.exists("PM Activity", {"reference_name": self.project,
                                                         "content": ["like", f"%{FOUNDATION} sang PHẦN THÂN%"]}))

    def test_a_partial_acceptance_is_not_enough(self):
        work = self.works[0]
        frappe.db.set_value("Task", work.name, "pmc_accepted_qty", work.pmc_planned_qty / 2)
        phase = frappe.db.get_value("Task", self.phase, ["project", "pm_path"], as_dict=True)
        self.assertEqual(len(acceptance.gate_check(phase)), 1)


class TestMissingDiary(LayerAlertBase):
    def test_yesterday_without_a_diary(self):
        day = layer_alerts.last_working_day(self.project, nowdate())
        rule = frappe.get_doc("PM Alert Rule", K.MISSING_DIARY)
        hits = [h for h in layer_alerts.missing_diary(rule, nowdate()) if h.project == self.project]
        self.assertEqual([h.episode for h in hits], [day.isoformat()])
        alerts.evaluate_rule(rule, nowdate())
        alert = frappe.db.get_value("PM Alert", {"rule": rule.name, "reference_name": self.project,
                                                 "state": alerts.OPEN}, ["name", "recipients"], as_dict=True)
        self.assertEqual(sorted(json.loads(alert.recipients)), sorted([COMMANDER, MANAGER]))
        self.diary_of(day, [])
        self.assertFalse([h for h in layer_alerts.missing_diary(rule, nowdate()) if h.project == self.project])
        alerts.evaluate_rule(rule, nowdate())
        self.assertEqual(frappe.db.get_value("PM Alert", alert.name, "state"), alerts.OVER)

    def test_a_project_not_started_or_without_boq_is_left_alone(self):
        rule = frappe.get_doc("PM Alert Rule", K.MISSING_DIARY)
        frappe.db.set_value("Project", self.project, "pm_state", "Tạm dừng")
        self.assertFalse([h for h in layer_alerts.missing_diary(rule, nowdate()) if h.project == self.project])


class TestRegistered(ConstructionBase):
    def test_the_layer_type_and_rule(self):
        core_install.ensure_alert_rules()
        self.assertIn(K.MISSING_DIARY, alerts.types())
        self.assertTrue(frappe.db.exists("PM Alert Rule", K.MISSING_DIARY))
        options = frappe.get_meta("PM Alert Rule").get_field("rule_type").options.split("\n")
        self.assertIn(K.MISSING_DIARY, options)
        self.assertIn(acceptance.__name__ + ".gate_check", frappe.get_hooks("pm_gate_checks"))
