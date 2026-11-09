"""M6: the site diary — quantities done each day move each work item's progress, and the project's, weighed by
estimate value; confirmation, sending back, offline resend, photos; and acceptance records with their quantities.

Run: bench --site <site> run-tests --app pm_construction --module pm_construction.tests.test_diary
"""

import uuid

import frappe
from frappe.utils import add_days, flt, nowdate
from project_manager.project_manager.services import forms, gates, media, rollup, timeline
from project_manager.tests.helpers import memory_store

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import acceptance, boq, diary
from pm_construction.tests.construction_helpers import (
    COMMANDER,
    ENGINEER,
    LEAD,
    MANAGER,
    OUTSIDER,
    ConstructionBase,
    as_user,
)

DIG, LEAN, FOOTING = "Đào móng băng bằng thủ công, đất cấp II", "Bê tông lót móng đá 4x6, vữa mác 100", \
    "Bê tông móng đá 1x2, mác 250"
PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


class DiaryBase(ConstructionBase):
    def setUp(self):
        super().setUp()
        self.store = memory_store(self)
        self.tasks = self.approved_sample()

    def write(self, rows, day=None, user=ENGINEER, submit=True, **values):
        day = day or nowdate()
        saved = as_user(user, diary.save, self.project, day, {"weather": "Nắng", "workers": 12, **values},
                        [{"task": self.tasks[name], "qty": qty} for name, qty in rows])
        return as_user(user, diary.submit, saved["name"]) if submit else saved

    def task(self, name, *fields):
        return frappe.db.get_value("Task", self.tasks[name], list(fields), as_dict=True)


class TestQuantities(DiaryBase):
    def test_quantities_move_progress_by_value(self):
        """Definition of done of M6: BOQ → WBS with quantities → daily quantities → progress by estimate value."""
        self.write([(DIG, 43.2), (LEAN, 9.6)], day=add_days(nowdate(), -1))
        self.write([(DIG, 21.6)])
        dig = self.task(DIG, "pmc_done_qty", "progress", "status")
        self.assertEqual((flt(dig.pmc_done_qty), flt(dig.progress)), (64.8, 75.0))
        self.assertEqual(flt(self.task(LEAN, "progress").progress), 100.0)
        rollup.reconcile(self.project)
        works = frappe.get_all("Task", filters={"project": self.project, "is_group": 0},
                               fields=["pmc_estimate_value", "progress"])
        expected = sum(flt(w.pmc_estimate_value) * flt(w.progress) for w in works) / sum(flt(w.pmc_estimate_value) for w in works)
        self.assertAlmostEqual(flt(frappe.db.get_value("Project", self.project, "percent_complete")), expected, places=1)
        self.assertGreater(expected, 0)
        summary = boq.summary(self.project)
        self.assertAlmostEqual(summary["done_value"], 64.8 * 285_000 + 9.6 * 1_350_000)

    def test_a_draft_does_not_count(self):
        self.write([(DIG, 10)], submit=False)
        self.assertEqual(flt(self.task(DIG, "pmc_done_qty").pmc_done_qty), 0)

    def test_sent_back_stops_counting_confirmed_locks(self):
        submitted = self.write([(DIG, 43.2)])
        self.assertEqual(flt(self.task(DIG, "progress").progress), 50.0)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, diary.confirm, submitted["name"])
        with self.assertRaises(frappe.ValidationError):
            as_user(COMMANDER, diary.send_back, submitted["name"], "")
        as_user(COMMANDER, diary.send_back, submitted["name"], "Khối lượng đào chưa đúng")
        self.assertEqual(flt(self.task(DIG, "pmc_done_qty").pmc_done_qty), 0)
        self.assertEqual(flt(self.task(DIG, "progress").progress), 0)
        fixed = as_user(ENGINEER, diary.save, self.project, nowdate(), {"weather": "Âm u"},
                        [{"task": self.tasks[DIG], "qty": 40}])
        as_user(ENGINEER, diary.submit, fixed["name"])
        confirmed = as_user(COMMANDER, diary.confirm, fixed["name"])
        self.assertEqual(confirmed["status"], K.DIARY_CONFIRMED)
        self.assertEqual(flt(self.task(DIG, "pmc_done_qty").pmc_done_qty), 40)
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, diary.save, self.project, nowdate(), {}, [])  # locked once submitted

    def test_a_resent_diary_counts_once(self):
        key = str(uuid.uuid4())
        args = (self.project, nowdate(), {"weather": "Nắng"}, [{"task": self.tasks[DIG], "qty": 8.64}], key)
        first = as_user(ENGINEER, diary.record, *args)
        again = as_user(ENGINEER, diary.record, *args)
        self.assertEqual(first["name"], again["name"])
        self.assertEqual(frappe.db.count("PMC Diary Quantity", {"diary": first["name"]}), 1)
        self.assertEqual(flt(self.task(DIG, "pmc_done_qty").pmc_done_qty), 8.64)

    def test_what_a_diary_refuses(self):
        cases = [
            (add_days(nowdate(), 1), [{"task": self.tasks[DIG], "qty": 1}]),  # a day still to come
            (nowdate(), [{"task": self.tasks[DIG], "qty": 0}]),
            (nowdate(), [{"task": self.tasks["PHẦN MÓNG"], "qty": 1}]),  # a section, not a work item
            (nowdate(), [{"task": self.tasks[DIG], "qty": 1}, {"task": self.tasks[DIG], "qty": 2}]),
        ]
        for day, rows in cases:
            with self.assertRaises(frappe.ValidationError):
                as_user(ENGINEER, diary.save, self.project, day, {}, rows)
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, diary.save, self.project, nowdate(), {"weather": "Bão tuyết"}, [])
        empty = as_user(ENGINEER, diary.save, self.project, nowdate(), {}, [])
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, diary.submit, empty["name"])  # nothing in it
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, diary.save, self.project, nowdate(), {}, [])
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, diary.listing, self.project)

    def test_photos_of_the_day(self):
        import io

        from PIL import Image

        saved = self.write([(DIG, 5)], submit=False)
        key = str(uuid.uuid4())
        out = io.BytesIO()
        Image.new("RGB", (40, 30), (120, 90, 60)).save(out, "JPEG")
        as_user(ENGINEER, media.upload, "PMC Site Diary", saved["name"], key, out.getvalue(), "nhat-ky.jpg")
        done = as_user(ENGINEER, diary.submit, saved["name"], [key])
        self.assertEqual(len(done["photos"]), 1)
        self.assertEqual([p["name"] for p in as_user(LEAD, media.gallery, self.project)["photos"]],
                         [p["name"] for p in done["photos"]])  # on the project's photo wall, with its comment
        feed = as_user(MANAGER, timeline.feed, "PMC Site Diary", saved["name"])
        self.assertTrue(any(entry["photos"] for entry in feed["entries"]))

    def test_a_task_waiting_for_its_form_stops_at_99(self):
        gates.add(self.tasks[LEAN], "NT-CONGVIEC", "Nghiệm thu bê tông lót")
        self.write([(LEAN, 9.6)])
        lean = self.task(LEAN, "progress", "status")
        self.assertEqual(flt(lean.progress), 99.0)
        self.assertNotEqual(lean.status, "Completed")

    def test_a_task_with_quantities_is_not_deleted(self):
        self.write([(DIG, 1)])
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("Task", self.tasks[DIG], ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Task", self.tasks[DIG]))


class TestAcceptance(DiaryBase):
    def test_an_approved_work_acceptance_sets_the_accepted_quantity(self):
        self.write([(FOOTING, 38.5)])
        signature = None

        def fill():
            nonlocal signature
            name = forms.start("NT-CONGVIEC", self.project, self.tasks[FOOTING])["name"]
            signature = forms.attach(name, PIXEL, "ky.png")
            forms.submit(name, {"ngay_nghiem_thu": nowdate(), K.QTY_FIELD: 30,
                                "thanh_phan_truc_tiep_nghiem_thu": [{"ho_va_ten": "Nguyễn A"}],
                                "chat_luong_cong_viec": [{"ket_qua": "Đạt"} for _ in range(4)],
                                "ket_luan": "Chấp nhận nghiệm thu",
                                "dai_dien_nha_thau_ky": [signature], "dai_dien_tu_van_giam_sat_ky": [signature]})
            return name

        record = as_user(ENGINEER, fill)
        self.assertEqual(flt(self.task(FOOTING, "pmc_accepted_qty").pmc_accepted_qty), 0)  # not approved yet
        as_user(COMMANDER, forms.approve, record)
        self.assertEqual(flt(self.task(FOOTING, "pmc_accepted_qty").pmc_accepted_qty), 30)
        overview = as_user(MANAGER, acceptance.overview, self.project)
        row = next(w for w in overview["works"] if w.name == self.tasks[FOOTING])
        self.assertEqual(flt(row.waiting_qty), 8.5)  # done but not accepted yet
        self.assertEqual(overview["records"][0]["qty"], 30)
        self.assertEqual({t.code for t in overview["templates"]}, set(K.ACCEPTANCE_CODES))
        self.assertAlmostEqual(overview["summary"]["accepted_value"], 30 * 1_950_000)
