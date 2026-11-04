"""M3: dynamic forms — versions never damage what was filled in, values follow the template, who approves, PDF, Excel,
and a task that may not close until its form is approved.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_forms
"""

import base64
import hashlib
import io
import json

import frappe
from frappe.utils import add_days, flt, nowdate
from pypdf import PdfReader

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import assignments, form_output, form_templates, forms, gates, progress, projects, rollup
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

ADMIN = f"fm.admin.{TAG}@example.com"
MANAGER = f"fm.manager.{TAG}@example.com"
COMMANDER = f"fm.commander.{TAG}@example.com"
ENGINEER = f"fm.engineer.{TAG}@example.com"
LEAD = f"fm.lead.{TAG}@example.com"
OUTSIDER = f"fm.outsider.{TAG}@example.com"
USERS = (ADMIN, MANAGER, COMMANDER, ENGINEER, LEAD, OUTSIDER)
CODE = f"T{TAG.upper()}"
PIXEL = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

ROWS = [
    {"label": "Thông tin chung", "fieldtype": C.F_SECTION},
    {"label": "Ngày kiểm tra", "fieldtype": C.F_DATE, "reqd": 1},
    {"label": "Khối lượng", "fieldtype": C.F_NUMBER, "min_value": "0", "max_value": "100", "unit": "m3"},
    {"label": "Kết luận", "fieldtype": C.F_SELECT, "options": "Đạt\nKhông đạt", "reqd": 1},
    {"label": "Đã kiểm tra an toàn", "fieldtype": C.F_CHECK},
    {"label": "Ghi chú", "fieldtype": C.F_LONG},
    {"label": "Danh mục", "fieldtype": C.F_TABLE, "options": "Nội dung\nKết quả | Chọn: Đạt, Không đạt\nĐiểm | Số",
     "preset_rows": "Đúng bản vẽ\nĐủ hồ sơ"},
    {"label": "Vật tư", "fieldtype": C.F_TABLE, "options": "Tên\nSố lượng | Số\nNgày về | Ngày"},
    {"label": "Ảnh", "fieldtype": C.F_IMAGE},
    {"label": "Người kiểm tra ký", "fieldtype": C.F_SIGNATURE},
]
GOOD = {"ngay_kiem_tra": "2026-11-04", "ket_luan": "Đạt"}


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class FormsBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        make_user(ADMIN, [C.ADMIN_ROLE])
        for user in USERS[1:]:
            make_user(user, [C.STAFF_ROLE])
        cls.project = make_project("FM")
        cls.other_project = make_project("FM khác")
        frappe.db.set_value("Project", cls.project, "pm_manager", MANAGER)
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, COMMANDER, "Chỉ huy trưởng")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, LEAD, "Tổ trưởng")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for project in (cls.project, cls.other_project):
            drop_project(project)
        for name in frappe.get_all("PM Form Template", filters={"code": ["like", f"%{TAG.upper()}%"]}, pluck="name"):
            doc = frappe.get_doc("PM Form Template", name)
            doc.flags.pm_cleanup = True
            doc.delete(ignore_permissions=True)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.local.pm_form_specs = {}
        self.template = form_templates.create(CODE, {"title": "Phiếu kiểm tra"}, ROWS)["name"]
        form_templates.activate(self.template)
        self.task = make_task(self.project, "Đổ bê tông", exp_end_date=add_days(nowdate(), 5))

    def started(self, user=ENGINEER, task=None):
        return as_user(user, forms.start, CODE, self.project, task or self.task)["name"]

    def submitted(self, user=ENGINEER, task=None, data=None):
        name = self.started(user, task)
        as_user(user, forms.submit, name, data or GOOD)
        return name


class TestTemplates(FormsBase):
    def test_codes_and_versions_name_the_template(self):
        self.assertEqual(self.template, f"{CODE}-v01")
        with self.assertRaises(frappe.ValidationError):
            form_templates.create(CODE, {"title": "Trùng mã"}, ROWS)
        with self.assertRaises(frappe.ValidationError):
            form_templates.create("mã có dấu", {"title": "x"}, ROWS)

    def test_a_template_in_use_is_frozen(self):
        with self.assertRaises(frappe.ValidationError):
            form_templates.save(self.template, {"title": "Sửa lén"})
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("PM Form Template", self.template, ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("PM Form Template", self.template, "title"), "Phiếu kiểm tra")

    def test_a_new_version_leaves_filled_forms_alone(self):
        filled = self.submitted(data={**GOOD, "khoi_luong": 12})
        draft = form_templates.new_version(self.template)["name"]
        self.assertEqual(draft, f"{CODE}-v02")
        self.assertEqual(form_templates.new_version(self.template)["name"], draft)  # one draft at a time
        rows = form_templates.get(draft)["rows"]
        for row in rows:
            if row["fieldname"] == "khoi_luong":
                row["label"] = "Khối lượng thực tế"  # a new label keeps the field's key
        rows = [r for r in rows if r["fieldname"] != "ghi_chu"] + [{"label": "Thời tiết", "fieldtype": C.F_TEXT}]
        form_templates.save(draft, {"title": "Phiếu kiểm tra (mới)"}, rows)
        form_templates.activate(draft)

        self.assertEqual(frappe.db.get_value("PM Form Template", self.template, "status"), C.FORM_RETIRED)
        self.assertEqual(form_templates.active_version(CODE), draft)
        old = as_user(ENGINEER, forms.detail, filled)
        self.assertEqual((old["template"], old["version"], old["title"]), (self.template, 1, "Phiếu kiểm tra"))
        self.assertIn("ghi_chu", [f["fieldname"] for f in old["spec"]["fields"]])
        self.assertEqual(old["data"]["khoi_luong"], 12)
        new = self.started(task=make_task(self.project, "Việc khác"))
        spec = as_user(ENGINEER, forms.detail, new)["spec"]
        self.assertEqual(spec["version"], 2)
        by_key = {f["fieldname"]: f for f in spec["fields"]}
        self.assertEqual(by_key["khoi_luong"]["label"], "Khối lượng thực tế")
        self.assertIn("thoi_tiet", by_key)

    def test_only_designers_design(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(MANAGER, form_templates.create, f"X{CODE}", {"title": "x"}, ROWS)
        with self.assertRaises(frappe.PermissionError):
            as_user(MANAGER, form_templates.overview)
        self.assertIn(self.template, [t.name for t in as_user(ENGINEER, form_templates.in_use)])
        draft = form_templates.new_version(self.template)["name"]
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, form_templates.get, draft)  # a draft is not offered to anyone
        codes = {r["code"] for r in as_user(ADMIN, form_templates.overview)["rows"]}
        self.assertIn(CODE, codes)

    def test_a_badly_described_field_is_refused(self):
        for bad in ({"label": "", "fieldtype": C.F_TEXT},
                    {"label": "Chọn gì", "fieldtype": C.F_SELECT},
                    {"label": "Bảng trống", "fieldtype": C.F_TABLE},
                    {"label": "Bảng sai", "fieldtype": C.F_TABLE, "options": "Cột | Ảnh"},
                    {"label": "Chọn không có lựa chọn", "fieldtype": C.F_TABLE, "options": "Cột | Chọn"},
                    {"label": "Số", "fieldtype": C.F_NUMBER, "min_value": "10", "max_value": "1"},
                    {"label": "Lạ", "fieldtype": "Tệp"}):
            with self.assertRaises(frappe.ValidationError, msg=str(bad)):
                form_templates.create(f"B{CODE}", {"title": "x"}, [bad])

    def test_a_template_without_answers_cannot_go_live(self):
        doc = form_templates.create(f"E{CODE}", {"title": "Trống"}, [{"label": "Chỉ có tiêu đề", "fieldtype": C.F_SECTION}])
        with self.assertRaises(frappe.ValidationError):
            form_templates.activate(doc["name"])
        form_templates.remove_draft(doc["name"])
        self.assertFalse(frappe.db.exists("PM Form Template", doc["name"]))

    def test_the_general_pack_is_installed_once(self):
        self.assertEqual(frappe.db.get_value("PM Form Template", {"code": "CL-CHUNG"}, "status"), C.FORM_ACTIVE)
        before = frappe.db.count("PM Form Template", {"code": "CL-CHUNG"})
        install.ensure_form_packs()
        self.assertEqual(frappe.db.count("PM Form Template", {"code": "CL-CHUNG"}), before)
        fields = {f["fieldname"]: f for f in form_templates.spec("CL-CHUNG-v01")["fields"]}
        self.assertEqual(len(fields["danh_muc_kiem_tra"]["preset_rows"]), 5)


class TestValues(FormsBase):
    def clean(self, raw, strict=False, files=()):
        return forms.clean_data(form_templates.spec(self.template), raw, files, strict)

    def test_types(self):
        data, errors = self.clean({**GOOD, "khoi_luong": "12,5", "da_kiem_tra_an_toan": True, "ghi_chu": "  ok  ", "la": "bỏ"})
        self.assertEqual(errors, [])
        self.assertEqual(data["khoi_luong"], 12.5)
        self.assertEqual(data["da_kiem_tra_an_toan"], 1)
        self.assertEqual(data["ghi_chu"], "ok")
        self.assertNotIn("la", data)
        for bad in ({"khoi_luong": "nhiều"}, {"khoi_luong": "nan"}, {"khoi_luong": -1}, {"khoi_luong": 101},
                    {"ngay_kiem_tra": "04/11/2026"}, {"ket_luan": "Tàm tạm"}, {"ghi_chu": "x" * 10001}):
            self.assertTrue(self.clean(bad)[1], str(bad))
        self.assertEqual(self.clean({"khoi_luong": 0})[0]["khoi_luong"], 0)  # 0 is a value, and the limit is inclusive

    def test_required_only_when_submitting(self):
        self.assertEqual(self.clean({})[1], [])
        problems = self.clean({}, strict=True)[1]
        self.assertEqual(len(problems), 2)  # ngày, kết luận
        name = self.started()
        as_user(ENGINEER, forms.save, name, {"ghi_chu": "đang làm dở"})
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, forms.submit, name)
        self.assertEqual(frappe.db.get_value("PM Form Submission", name, "state"), C.SUB_DRAFT)
        self.assertEqual(as_user(ENGINEER, forms.submit, name, GOOD)["state"], C.SUB_SUBMITTED)

    def test_a_required_number_may_be_zero(self):
        doc = form_templates.create(f"Z{CODE}", {"title": "Số"}, [{"label": "Sự cố", "fieldtype": C.F_NUMBER, "reqd": 1}])
        spec = form_templates.spec(doc["name"])
        self.assertEqual(forms.clean_data(spec, {"su_co": 0}, strict=True), ({"su_co": 0}, []))

    def test_a_required_checkbox_must_be_ticked(self):
        doc = form_templates.create(f"C{CODE}", {"title": "Cam kết"}, [{"label": "Cam kết", "fieldtype": C.F_CHECK, "reqd": 1}])
        spec = form_templates.spec(doc["name"])
        self.assertTrue(forms.clean_data(spec, {"cam_ket": 0}, strict=True)[1])
        self.assertEqual(forms.clean_data(spec, {"cam_ket": 1}, strict=True)[1], [])

    def test_tables(self):
        data, errors = self.clean({"vat_tu": [{"ten": "Thép", "so_luong": "3", "ngay_ve": "2026-11-05", "la": "x"}, {"ten": ""},
                                              {"so_luong": "nhiều"}]})
        self.assertEqual(len(errors), 1)
        self.assertEqual(data["vat_tu"], [{"ten": "Thép", "so_luong": 3, "ngay_ve": "2026-11-05"}])

    def test_a_checklist_keeps_its_rows(self):
        data, errors = self.clean({"danh_muc": [{"noi_dung": "Sửa câu hỏi", "ket_qua": "Đạt"}, {"ket_qua": "Tàm tạm"}, {"noi_dung": "Thêm"}]})
        self.assertEqual(len(errors), 1)  # "Tàm tạm" is not a choice
        self.assertEqual(data["danh_muc"], [{"noi_dung": "Đúng bản vẽ", "ket_qua": "Đạt"}, {"noi_dung": "Đủ hồ sơ"}])

    def test_files_must_belong_to_this_form(self):
        self.assertTrue(self.clean({"anh": [{"file": "/private/files/cua-nguoi-khac.jpg"}]})[1])
        data, errors = self.clean({"anh": [{"file": "/private/files/a.jpg", "name": "a"}]}, files=["/private/files/a.jpg"])
        self.assertEqual(errors, [])
        self.assertEqual(data["anh"], [{"file": "/private/files/a.jpg", "name": "a"}])


class TestFiles(FormsBase):
    def test_attach_only_real_pictures(self):
        name = self.started()
        for bad in (base64.b64encode(b"<svg onload=alert(1)>").decode(), "khong-phai-base64!", ""):
            with self.assertRaises(frappe.ValidationError):
                as_user(ENGINEER, forms.attach, name, bad, "a.png")
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, forms.attach, name, PIXEL)
        added = as_user(ENGINEER, forms.attach, name, f"data:image/png;base64,{PIXEL}", "ảnh.png")
        self.assertTrue(added["file"].startswith("/private/files/"))
        self.assertTrue(added["file"].endswith(".png"))
        detail = as_user(ENGINEER, forms.save, name, {"anh": [added]})
        self.assertEqual(detail["data"]["anh"][0]["file"], added["file"])

    def test_a_form_cannot_borrow_a_private_file(self):
        mine = self.started()
        other = self.started(task=make_task(self.project, "Việc khác"))
        added = as_user(ENGINEER, forms.attach, other, PIXEL)
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, forms.save, mine, {"anh": [added]})

    def test_a_private_picture_follows_the_form(self):
        name = self.started()
        added = as_user(ENGINEER, forms.attach, name, PIXEL)
        file = frappe.get_doc("File", {"file_url": added["file"]})
        self.assertTrue(frappe.has_permission("File", "read", doc=file, user=ENGINEER))
        self.assertFalse(frappe.has_permission("File", "read", doc=file, user=OUTSIDER))


class TestWorkflow(FormsBase):
    def test_who_fills_in(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, forms.start, CODE, self.project, self.task)
        with self.assertRaises(frappe.PermissionError):
            as_user(LEAD, forms.start, CODE, self.project, self.task)  # a crew lead: only the tasks given to them
        assignments.assign(self.task, C.RESPONSIBLE, user=LEAD)
        self.assertTrue(as_user(LEAD, forms.start, CODE, self.project, self.task)["name"])

    def test_the_same_form_is_opened_again_until_submitted(self):
        first = as_user(ENGINEER, forms.start, CODE, self.project, self.task)
        again = as_user(ENGINEER, forms.start, CODE, self.project, self.task)
        self.assertEqual((again["name"], again["resumed"]), (first["name"], True))
        as_user(ENGINEER, forms.submit, first["name"], GOOD)
        self.assertNotEqual(as_user(ENGINEER, forms.start, CODE, self.project, self.task)["name"], first["name"])

    def test_a_retired_form_cannot_be_started(self):
        form_templates.retire(self.template)
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, forms.start, CODE, self.project, self.task)

    def test_a_form_of_the_project_without_a_task(self):
        name = as_user(ENGINEER, forms.start, CODE, self.project)["name"]
        self.assertIsNone(as_user(ENGINEER, forms.detail, name)["task"])
        lead_form = as_user(LEAD, forms.start, CODE, self.project)["name"]
        as_user(LEAD, forms.submit, lead_form, GOOD)
        self.assertEqual(as_user(LEAD, forms.detail, lead_form)["state"], C.SUB_SUBMITTED)  # their own stays theirs

    def test_approve(self):
        name = self.submitted()
        with self.assertRaises(frappe.PermissionError):
            as_user(LEAD, forms.approve, name)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, forms.approve, name)
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": MANAGER, "subject": ["like", "%chờ bạn duyệt%"]}))
        detail = as_user(COMMANDER, forms.approve, name, "Tốt")
        self.assertEqual((detail["state"], detail["reviewed_by"], detail["review_note"]), (C.SUB_APPROVED, COMMANDER, "Tốt"))
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": ENGINEER, "subject": ["like", "Đã duyệt%"]}))
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, forms.approve, name)  # already decided

    def test_nobody_approves_their_own_form(self):
        name = self.submitted(COMMANDER)
        detail = as_user(COMMANDER, forms.detail, name)
        self.assertFalse(detail["can"]["approve"])
        self.assertTrue(detail["can"]["self_submitted"])
        with self.assertRaises(frappe.PermissionError):
            as_user(COMMANDER, forms.approve, name)
        self.assertEqual(as_user(MANAGER, forms.approve, name)["state"], C.SUB_APPROVED)
        own = self.submitted(ADMIN, task=make_task(self.project, "Của quản trị"))
        self.assertEqual(as_user(ADMIN, forms.approve, own)["state"], C.SUB_APPROVED)  # administrators are the exception

    def test_the_reviewer_of_the_task_approves(self):
        assignments.assign(self.task, C.REVIEWER, user=ENGINEER)
        name = self.submitted(MANAGER)
        self.assertEqual(as_user(ENGINEER, forms.approve, name)["state"], C.SUB_APPROVED)

    def test_send_back_and_again(self):
        name = self.submitted()
        with self.assertRaises(frappe.ValidationError):
            as_user(COMMANDER, forms.send_back, name, "  ")
        self.assertEqual(as_user(COMMANDER, forms.send_back, name, "Thiếu ảnh")["state"], C.SUB_RETURNED)
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": ENGINEER, "subject": ["like", "Trả lại%"]}))
        with self.assertRaises(frappe.ValidationError):
            as_user(COMMANDER, forms.approve, name)
        detail = as_user(ENGINEER, forms.submit, name, {**GOOD, "ghi_chu": "Đã bổ sung"})
        self.assertEqual(detail["state"], C.SUB_SUBMITTED)
        self.assertIsNone(detail["review_note"])
        self.assertEqual(as_user(COMMANDER, forms.approve, name)["state"], C.SUB_APPROVED)
        texts = [h.content for h in as_user(ENGINEER, forms.detail, name)["history"]]
        self.assertEqual(len(texts), 4)  # nộp, trả lại, nộp, duyệt
        self.assertTrue(any("Thiếu ảnh" in t for t in texts))

    def test_an_approved_form_never_changes(self):
        name = self.submitted()
        as_user(COMMANDER, forms.approve, name)
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, forms.save, name, {"ghi_chu": "sửa sau khi duyệt"})
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, forms.attach, name, PIXEL)
        doc = frappe.get_doc("PM Form Submission", name)
        doc.review_note = "sửa lén"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("PM Form Submission", name, ignore_permissions=True)
        self.assertFalse(frappe.has_permission("PM Form Submission", "write", doc=doc, user=MANAGER))

    def test_discard_only_what_was_never_submitted(self):
        draft = self.started()
        with self.assertRaises(frappe.PermissionError):
            as_user(LEAD, forms.discard, draft)
        as_user(ENGINEER, forms.discard, draft)
        self.assertFalse(frappe.db.exists("PM Form Submission", draft))
        name = self.submitted()
        as_user(COMMANDER, forms.send_back, name, "Sai")
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, forms.discard, name)

    def test_lists_follow_the_scope(self):
        task2 = make_task(self.project, "Việc của tổ")
        name = self.submitted()
        lead_form = self.submitted(task=task2)
        draft = as_user(ENGINEER, forms.start, CODE, self.project, make_task(self.project, "Nháp"))["name"]
        names = {r.name for r in as_user(MANAGER, forms.list_forms, project=self.project)["rows"]}
        self.assertEqual(names, {name, lead_form})  # another person's draft is not shown
        self.assertEqual([r.name for r in as_user(ENGINEER, forms.list_forms, project=self.project, state=C.SUB_DRAFT)["rows"]], [draft])
        self.assertEqual(as_user(OUTSIDER, forms.list_forms, project=self.project)["rows"], [])
        self.assertEqual(as_user(LEAD, forms.list_forms, project=self.project)["rows"], [])
        assignments.assign(task2, C.RESPONSIBLE, user=LEAD)
        self.assertEqual([r.name for r in as_user(LEAD, forms.list_forms, project=self.project)["rows"]], [lead_form])
        with self.assertRaises(frappe.PermissionError):
            as_user(LEAD, forms.detail, name)
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, forms.detail, name)

    def test_waiting_for_me(self):
        name = self.submitted()
        mine = self.submitted(COMMANDER, task=make_task(self.project, "Của chỉ huy"))
        names = {r.name for r in as_user(COMMANDER, forms.waiting_for_me)["rows"]}
        self.assertIn(name, names)
        self.assertNotIn(mine, names)
        self.assertEqual(as_user(ENGINEER, forms.waiting_for_me)["rows"], [])
        assignments.assign(self.task, C.REVIEWER, user=LEAD)
        reviewed = {r.name for r in as_user(LEAD, forms.waiting_for_me)["rows"]}
        self.assertEqual(reviewed, {name})  # the reviewer of one task sees that task's form only

    def test_the_task_timeline_shows_the_form(self):
        self.submitted()
        from project_manager.project_manager.services import work

        kinds = [row.activity_type for row in as_user(ENGINEER, work.task_detail, self.task)["timeline"]]
        self.assertIn("Biểu mẫu", kinds)


class TestOutput(FormsBase):
    def full(self):
        name = self.started()
        added = as_user(ENGINEER, forms.attach, name, PIXEL)
        data = {**GOOD, "ghi_chu": '<script>alert("x")</script> & <img src=x>', "khoi_luong": 7,
                "danh_muc": [{"ket_qua": "Đạt"}], "vat_tu": [{"ten": "=1+1", "so_luong": 2}], "anh": [added],
                "nguoi_kiem_tra_ky": [added]}
        as_user(ENGINEER, forms.submit, name, data)
        return name

    def test_answers_are_escaped_in_the_print(self):
        doc = frappe.get_doc("PM Form Submission", self.full())
        html = form_output.render_html(doc)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<img src=x>", html)
        self.assertEqual(html.count("data:image/png;base64,"), 2)
        self.assertIn("BẢN CHƯA DUYỆT", html)
        self.assertIn("7 m3", html)

    def test_pictures_of_another_form_are_not_printed(self):
        name = self.full()
        other = self.started(task=make_task(self.project, "Việc khác"))
        # another picture: Frappe stores identical content once, under one URL
        foreign = as_user(ENGINEER, forms.attach, other, base64.b64encode(base64.b64decode(PIXEL) + b"khac").decode())
        doc = frappe.get_doc("PM Form Submission", name)
        data = json.loads(doc.data)
        data["anh"] = [foreign]
        frappe.db.set_value("PM Form Submission", name, "data", json.dumps(data))
        doc.reload()
        self.assertEqual(form_output.render_html(doc).count("data:image/png;base64,"), 1)  # only the signature

    def test_the_approved_pdf_is_made_once(self):
        name = self.full()
        draft_name, draft = as_user(ENGINEER, form_output.pdf_of, name)
        self.assertEqual(draft[:4], b"%PDF")
        self.assertIsNone(frappe.db.get_value("PM Form Submission", name, "pdf_file"))
        as_user(COMMANDER, forms.approve, name)
        filename, first = as_user(ENGINEER, form_output.pdf_of, name)
        self.assertEqual(filename, f"bieu-mau-{name}.pdf")
        stored = frappe.db.get_value("PM Form Submission", name, ["pdf_file", "pdf_hash"], as_dict=True)
        self.assertTrue(stored.pdf_file.startswith("/private/files/"))
        self.assertEqual(len(stored.pdf_hash), 64)
        frappe.db.set_value("Project", self.project, "project_name", "Đã đổi tên")
        _name, second = as_user(COMMANDER, form_output.pdf_of, name)
        self.assertEqual(first, second)  # what was approved stays what is printed
        self.assertEqual(hashlib.sha256(second).hexdigest(), stored.pdf_hash)
        text = PdfReader(io.BytesIO(first)).pages[0].extract_text()
        self.assertIn("Phiếu kiểm tra", text)  # Vietnamese survives the font
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, form_output.pdf_of, name)

    def test_excel_has_a_row_per_form_and_a_sheet_per_table(self):
        from openpyxl import load_workbook

        name = self.full()
        self.started(task=make_task(self.project, "Còn nháp"))  # a draft stays out
        filename, content = as_user(MANAGER, form_output.export_xlsx, self.project, CODE)
        self.assertEqual(filename, f"bieu-mau-{CODE}.xlsx")
        book = load_workbook(io.BytesIO(content))
        main = book.worksheets[0]
        rows = list(main.values)
        self.assertEqual(len(rows), 2)
        header, row = rows
        self.assertEqual(row[header.index("Số")], name)
        self.assertEqual(row[header.index("Khối lượng")], 7)
        self.assertEqual(row[header.index("Ảnh")], "1 tệp")
        self.assertNotIn("Danh mục", header)
        materials = list(book["Vật tư"].values)
        self.assertEqual(materials[1][:3], (name, "=1+1", 2))
        self.assertEqual(book["Vật tư"].cell(row=2, column=2).data_type, "s")  # text, never a formula
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, form_output.export_xlsx, self.project, CODE)


class TestGates(FormsBase):
    def setUp(self):
        super().setUp()
        self.gate = gates.add(self.task, CODE)["name"]

    def test_a_task_stays_open_until_its_form_is_approved(self):
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, progress.report, self.task, 100)
        name = self.submitted()
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, progress.report, self.task, 100)  # submitted is not approved
        self.assertEqual(frappe.db.get_value("Task", self.task, "status"), C.OPEN)
        as_user(COMMANDER, forms.approve, name)
        self.assertEqual(as_user(ENGINEER, progress.report, self.task, 100).status, C.COMPLETED)
        dates = frappe.db.get_value("Task", self.task, ["act_start_date", "act_end_date"], as_dict=True)
        self.assertTrue(dates.act_start_date and dates.act_end_date)  # finished in one report: it did start

    def test_every_way_of_closing_is_stopped(self):
        doc = frappe.get_doc("Task", self.task)
        doc.status = C.COMPLETED
        with self.assertRaises(frappe.ValidationError):  # the Desk, the REST API
            doc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):  # the board
            as_user(ENGINEER, progress.move, self.task, C.COMPLETED)

    def test_with_a_reviewer_the_form_may_still_be_waiting(self):
        assignments.assign(self.task, C.REVIEWER, user=COMMANDER)
        with self.assertRaises(frappe.ValidationError):
            as_user(ENGINEER, progress.report, self.task, 100)
        name = self.submitted()
        self.assertEqual(as_user(ENGINEER, progress.report, self.task, 100).status, C.REVIEW)
        with self.assertRaises(frappe.ValidationError):
            as_user(COMMANDER, progress.review, self.task, True)
        as_user(COMMANDER, forms.approve, name)
        self.assertEqual(as_user(COMMANDER, progress.review, self.task, True).status, C.COMPLETED)

    def test_a_form_on_any_version_counts(self):
        name = self.submitted()
        as_user(COMMANDER, forms.approve, name)
        draft = form_templates.new_version(self.template)["name"]
        form_templates.activate(draft)
        self.assertEqual(gates.unmet(self.task), [])

    def test_of_task_shows_how_far_each_form_got(self):
        self.assertEqual((gates.of_task(self.task)[0].state, gates.of_task(self.task)[0].met), (None, False))
        name = self.started()
        self.assertEqual(gates.of_task(self.task)[0].state, C.SUB_DRAFT)
        as_user(ENGINEER, forms.submit, name, GOOD)
        self.assertEqual(gates.of_task(self.task)[0].state, C.SUB_SUBMITTED)
        as_user(COMMANDER, forms.approve, name)
        row = gates.of_task(self.task)[0]
        self.assertEqual((row.state, row.met, row.submission), (C.SUB_APPROVED, True, name))
        view = as_user(ENGINEER, forms.for_task, self.task)
        self.assertEqual(view["gates"][0].form_code, CODE)
        self.assertEqual([f.name for f in view["forms"]], [name])
        self.assertTrue(view["can_fill"])
        self.assertFalse(view["can_gate"])

    def test_a_group_waits_for_its_form(self):
        group = make_task(self.project, "Phần móng", is_group=1)
        leaf = make_task(self.project, "Đào đất", parent=group)
        gates.add(group, CODE)
        as_user(ENGINEER, progress.report, leaf, 100)
        rollup.recompute(self.project, {group})
        row = frappe.db.get_value("Task", group, ["status", "progress"], as_dict=True)
        self.assertEqual((row.status, flt(row.progress)), (C.WORKING, 100))
        name = self.submitted(task=group)
        as_user(COMMANDER, forms.approve, name)
        rollup.recompute(self.project, {group})
        self.assertEqual(frappe.db.get_value("Task", group, "status"), C.COMPLETED)

    def test_who_sets_requirements(self):
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, gates.add, make_task(self.project, "Khác"), CODE)
        with self.assertRaises(frappe.ValidationError):
            gates.add(self.task, CODE)  # already required
        with self.assertRaises(frappe.ValidationError):
            gates.add(self.task, "KHONG-CO")
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, gates.remove, self.gate)
        as_user(MANAGER, gates.remove, self.gate)
        self.assertEqual(gates.of_task(self.task), [])
        self.assertEqual(as_user(ENGINEER, progress.report, self.task, 100).status, C.COMPLETED)

    def test_a_required_form_cannot_be_retired(self):
        with self.assertRaises(frappe.ValidationError):
            form_templates.retire(self.template)
        as_user(MANAGER, gates.remove, self.gate)
        self.assertEqual(form_templates.retire(self.template)["status"], C.FORM_RETIRED)

    def test_a_project_from_a_template_brings_its_requirements(self):
        template = make_project("Mẫu có điều kiện")
        frappe.db.set_value("Project", template, "pm_is_template", 1)
        source = make_task(template, "Nghiệm thu")
        gates.add(source, CODE)
        created = projects.create({"project_name": f"Dự án từ mẫu {TAG}"}, template)
        new_task = frappe.db.get_value("Task", {"project": created["name"], "subject": "Nghiệm thu"}, "name")
        self.assertEqual([g.form_code for g in gates.of_task(new_task)], [CODE])
        self.assertEqual(frappe.db.get_value("PM Gate Requirement", {"task": new_task}, "project"), created["name"])

    def test_scope_of_requirements(self):
        doc = frappe.get_doc("PM Gate Requirement", self.gate)
        self.assertTrue(frappe.has_permission("PM Gate Requirement", "read", doc=doc, user=ENGINEER))
        self.assertFalse(frappe.has_permission("PM Gate Requirement", "read", doc=doc, user=OUTSIDER))
        self.assertFalse(frappe.has_permission("PM Gate Requirement", "write", doc=doc, user=MANAGER))
