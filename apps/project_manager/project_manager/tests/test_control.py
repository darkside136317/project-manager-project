"""M10: budgets and earned value, risks, issues, change requests, reports and their scheduled sending, MS Project XML,
closing a project and its dossier.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_control
"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.services import (
    alerts,
    assignments,
    budget,
    closing,
    control,
    msproject,
    reports,
    schedule,
)
from project_manager.project_manager.services.reports import output
from project_manager.project_manager.services.reports import schedule as sending
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import TAG, PMTestCase, add_member, drop_project, drop_user, make_project, make_task, make_user

MANAGER = f"ct.manager.{TAG}@example.com"
ENGINEER = f"ct.engineer.{TAG}@example.com"
ACCOUNTANT = f"ct.accountant.{TAG}@example.com"
LEAD = f"ct.lead.{TAG}@example.com"
OUTSIDER = f"ct.outsider.{TAG}@example.com"
USERS = (MANAGER, ENGINEER, ACCOUNTANT, LEAD, OUTSIDER)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class ControlBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        cls.project, cls.other = make_project("CT"), make_project("CT khác")
        today = getdate(nowdate())
        frappe.db.set_value("Project", cls.project, {"pm_state": "Đang thực hiện", "pm_manager": MANAGER,
                                                     "expected_start_date": add_days(today, -10),
                                                     "expected_end_date": add_days(today, 10)})
        for user, role in ((MANAGER, "Quản lý dự án"), (ENGINEER, "Kỹ sư"), (ACCOUNTANT, "Kế toán dự án"),
                           (LEAD, "Tổ trưởng")):
            add_member(cls.project, user, role)
        add_member(cls.other, OUTSIDER, "Kỹ sư")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("PM Report Recipient", {"user": ["in", USERS]})
        frappe.db.delete("PM Report Subscription", {"owner_user": ["in", USERS]})
        for project in (cls.project, cls.other):
            for name in frappe.get_all("File", filters={"attached_to_doctype": "Project", "attached_to_name": project},
                                       pluck="name"):
                frappe.delete_doc("File", name, force=True, ignore_permissions=True)
            drop_project(project)
        for user in USERS:
            frappe.db.delete("Notification Log", {"for_user": user})
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def task(self, subject, start=0, end=3, **values):
        today = getdate(nowdate())
        return make_task(self.project, f"{subject} {TAG}", exp_start_date=add_days(today, start),
                         exp_end_date=add_days(today, end), **values)


class TestBudget(ControlBase):
    def draft(self, user=MANAGER, lines=None):
        work = self.task("Móng")
        lines = lines or [{"category": "Vật tư", "task": work, "amount": 600}, {"category": "Nhân công", "amount": 400}]
        return as_user(user, budget.save_draft, self.project, "Ngân sách gốc", lines)

    def test_draft_approve_and_replace(self):
        first = self.draft()
        self.assertEqual((first["total"], first["version"]), (1000, 1))
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, budget.save_draft, self.project, "Hai", [])  # one draft
        as_user(MANAGER, budget.approve, first["name"])
        self.assertEqual(budget.current(self.project), first["name"])
        second = as_user(ACCOUNTANT, budget.start_from_current, self.project)  # the accountant revises it
        as_user(ACCOUNTANT, budget.save_draft, self.project, "Điều chỉnh", [{"category": "Vật tư", "amount": 1500}],
                name=second["name"])
        as_user(ACCOUNTANT, budget.approve, second["name"])
        self.assertEqual(frappe.db.get_value("PM Budget", first["name"], "status"), budget.REPLACED)
        self.assertEqual(budget.bac(self.project), 1500)
        view = as_user(MANAGER, budget.overview, self.project)
        self.assertEqual(view["in_use"]["name"], second["name"])
        self.assertEqual([b["version"] for b in view["budgets"]], [2, 1])

    def test_who_reads_and_manages(self):
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, budget.overview, self.project)
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, budget.save_draft, self.project, "x", [])
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, budget.overview, self.project)
        self.assertTrue(as_user(ACCOUNTANT, budget.overview, self.project)["can"]["manage"])

    def test_earned_value(self):
        name = self.draft()["name"]
        as_user(MANAGER, budget.approve, name)
        frappe.db.set_value("Project", self.project, "percent_complete", 40)
        figures = budget.evm(self.project, costs=[{"task": None, "category": "Vật tư", "amount": 500}])
        self.assertEqual(figures["bac"], 1000)
        self.assertAlmostEqual(figures["pv"], round(1000 * figures["planned_pct"] / 100), delta=1)
        self.assertEqual((figures["ev"], figures["ac"]), (400, 500))
        self.assertEqual(figures["cpi"], 0.8)
        self.assertEqual(figures["eac"], 500 + (1000 - 400) / 0.8)
        self.assertEqual(figures["vac"], 1000 - figures["eac"])
        with patch.object(budget, "actual_costs", return_value=[{"task": None, "category": "Nhân công", "amount": 700}]):
            view = as_user(MANAGER, budget.overview, self.project)
        labour = next(r for r in view["by_category"] if r["category"] == "Nhân công")
        self.assertEqual((labour["budget"], labour["actual"]), (400, 700))


class TestRegister(ControlBase):
    def test_risks_and_issues(self):
        risk = as_user(ENGINEER, control.save_risk, self.project, {"title": "Mưa kéo dài", "probability": 4, "impact": 4,
                                                                    "owner_user": MANAGER})
        self.assertEqual((risk["score"], risk["level"]), (16, "Cao"))
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": MANAGER, "document_name": risk["name"]}))
        self.assertRaises(frappe.ValidationError, as_user, ENGINEER, control.save_risk, self.project, {"title": "x",
                                                                                                     "probability": 6})
        happened = as_user(MANAGER, control.risk_happened, risk["name"], "Mưa 5 ngày liền")
        self.assertEqual(frappe.db.get_value("PM Risk", risk["name"], "status"), "Đã xảy ra")
        issue = frappe.get_doc("PM Issue", happened["issue"])
        self.assertEqual((issue.risk, issue.priority), (risk["name"], "Cao"))
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, control.save_issue, self.project,
                          {"status": "Đã giải quyết"}, issue.name)  # how it was solved first
        as_user(MANAGER, control.save_issue, self.project, {"status": "Đã giải quyết", "resolution": "Làm bù"}, issue.name)
        self.assertEqual(str(frappe.db.get_value("PM Issue", issue.name, "resolved_on")), nowdate())

    def test_who_sees_the_register(self):
        self.assertRaises(frappe.PermissionError, as_user, LEAD, control.register, self.project)  # sees only their tasks
        self.assertRaises(frappe.PermissionError, as_user, OUTSIDER, control.register, self.project)
        self.assertRaises(frappe.PermissionError, as_user, ACCOUNTANT, control.save_risk, self.project, {"title": "x"})
        view = as_user(ENGINEER, control.register, self.project)
        self.assertTrue(view["can"]["risk"] and view["can"]["request"] and not view["can"]["approve"])

    def test_overdue_issue_alert(self):
        issue = as_user(MANAGER, control.save_issue, self.project, {"title": "Thiếu bản vẽ", "owner_user": ENGINEER,
                                                                    "due_date": add_days(nowdate(), -1)})
        install.ensure_alert_rules()
        rule = frappe.get_doc("PM Alert Rule", alerts.OVERDUE_ISSUE)
        hits = [h for h in control.overdue_issues(rule, nowdate()) if h.reference_name == issue["name"]]
        self.assertEqual(len(hits), 1)
        self.assertEqual(set(hits[0].direct), {ENGINEER, MANAGER})


class TestChanges(ControlBase):
    def test_from_request_to_budget_and_plan(self):
        name = as_user(MANAGER, budget.save_draft, self.project, "Gốc", [{"category": "Vật tư", "amount": 1000}])["name"]
        as_user(MANAGER, budget.approve, name)
        work = self.task("Cột", 0, 3)
        new_end = add_days(nowdate(), 6)
        change = as_user(ENGINEER, control.save_change, self.project, {"title": "Thêm cột trục 9", "cost_impact": 250,
                                                                       "days_impact": 3},
                         [{"task": work, "new_end": new_end}])
        self.assertEqual(change["tasks"][0]["old_end"], add_days(getdate(nowdate()), 3))
        as_user(ENGINEER, control.submit_change, change["name"])
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": MANAGER, "document_name": change["name"]}))
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, control.decide, change["name"], True)
        decided = as_user(MANAGER, control.decide, change["name"], True, "Đồng ý")
        self.assertEqual(decided["budget"], name)
        self.assertEqual(budget.bac(self.project), 1250)
        self.assertEqual(getdate(frappe.db.get_value("Task", work, "exp_end_date")), getdate(new_end))
        self.assertTrue(frappe.db.exists("PM Budget Line", {"parent": name, "change_request": change["name"]}))

    def test_rejected_and_cancelled(self):
        change = as_user(ENGINEER, control.save_change, self.project, {"title": "Đổi gạch", "cost_impact": 10})
        as_user(ENGINEER, control.submit_change, change["name"])
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, control.decide, change["name"], False)  # no reason
        as_user(MANAGER, control.decide, change["name"], False, "Không cần")
        self.assertEqual(frappe.db.get_value("PM Change Request", change["name"], "status"), control.REJECTED)
        other = as_user(ENGINEER, control.save_change, self.project, {"title": "Thêm cửa"})
        as_user(ENGINEER, control.cancel_change, other["name"])
        self.assertEqual(frappe.db.get_value("PM Change Request", other["name"], "status"), control.CANCELLED)
        self.assertRaises(frappe.PermissionError, as_user, LEAD, control.save_change, self.project, {"title": "x"})


class TestReports(ControlBase):
    def test_every_report_runs_within_scope(self):
        late = self.task("Trễ", -6, -2)
        frappe.db.set_value("Task", late, {"pm_is_overdue": 1, "pm_delay_days": 2})
        assignments.assign(late, C.ACCOUNTABLE, user=ENGINEER)
        for slug in [r.slug for r in as_user(MANAGER, reports.visible)]:
            filters = {}
            spec = reports.get(slug)
            if any(f.get("reqd") for f in spec.filters):
                filters = {"project": self.project}
            result = as_user(MANAGER, reports.run, slug, filters)
            self.assertIn("rows", result, slug)
        mine = as_user(MANAGER, reports.run, "cong-viec-tre", {"project": self.project})
        self.assertIn(late, [r["task"] for r in mine["rows"]])
        theirs = as_user(OUTSIDER, reports.run, "cong-viec-tre", {})
        self.assertNotIn(late, [r["task"] for r in theirs["rows"]])
        self.assertEqual(as_user(ENGINEER, reports.run, "ngan-sach-evm", {})["rows"], [])  # no finance.view

    def test_files(self):
        result, applied = as_user(MANAGER, output.prepare, "tien-do-du-an", {}, 100)
        self.assertTrue(as_user(MANAGER, output.to_csv, result).startswith("﻿".encode("utf-8")))
        self.assertTrue(as_user(MANAGER, output.to_xlsx, result, applied).startswith(b"PK"))
        self.assertIn(result["title"], as_user(MANAGER, output.render_html, result, applied))


class TestSending(ControlBase):
    def test_subscriptions(self):
        saved = as_user(MANAGER, sending.save, "cong-viec-tre", {"frequency": sending.WEEKLY, "weekday": "Thứ Hai",
                                                                  "hour": 7}, [MANAGER, ENGINEER])
        self.assertRaises(frappe.ValidationError, as_user, ENGINEER, sending.save, "cong-viec-tre", {}, [OUTSIDER])
        row = frappe.get_doc("PM Report Subscription", saved["name"])
        monday = getdate("2030-01-07")
        self.assertTrue(sending.is_due(row, f"{monday} 07:10:00"))
        self.assertFalse(sending.is_due(row, f"{monday} 08:10:00"))
        self.assertFalse(sending.is_due(row, f"{add_days(monday, 1)} 07:10:00"))
        row.last_sent_on = f"{monday} 07:01:00"
        self.assertFalse(sending.is_due(row, f"{monday} 07:50:00"))
        seen = []

        def build(slug, filters, file_format):
            seen.append(frappe.session.user)
            return "x.pdf", b"%PDF", {"title": "Công việc trễ", "total": 0}

        with patch.object(sending, "build", side_effect=build), patch.object(alerts, "email_ready", return_value=False):
            quiet = sending.send(saved["name"])
        self.assertEqual((quiet["sent"], quiet["emailed"]), ([MANAGER, ENGINEER], []))  # no email account: notices only
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": ENGINEER, "document_name": str(saved["name"])}))
        seen.clear()
        with patch.object(sending, "build", side_effect=build), patch.object(alerts, "email_ready", return_value=True),                 patch.object(frappe, "sendmail") as mail:
            result = sending.send(saved["name"])
        self.assertEqual(seen, [MANAGER, ENGINEER])  # each recipient as themselves
        self.assertEqual(frappe.session.user, "Administrator")
        self.assertEqual(result["emailed"], [MANAGER, ENGINEER])
        self.assertEqual([c.kwargs["recipients"] for c in mail.call_args_list], [[MANAGER], [ENGINEER]])
        self.assertEqual(mail.call_args.kwargs["attachments"], [{"fname": "x.pdf", "fcontent": b"%PDF"}])
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, sending.remove, saved["name"])


class TestMSProject(ControlBase):
    def test_round_trip(self):
        group = make_task(self.project, f"Phần móng {TAG}", is_group=1)
        today = getdate(nowdate())
        first = make_task(self.project, f"Đào đất {TAG}", parent=group, exp_start_date=today,
                          exp_end_date=add_days(today, 2))
        second = make_task(self.project, f"Đổ bê tông {TAG}", parent=group, exp_start_date=add_days(today, 3),
                           exp_end_date=add_days(today, 5))
        assignments.assign(first, C.ACCOUNTABLE, user=ENGINEER)
        schedule.add_dependency(first, second, "FS", 1)
        name, content = as_user(MANAGER, msproject.export, self.project)
        self.assertIn(b"<PredecessorLink>", content)
        target = make_project("CT nhập")
        try:
            add_member(target, MANAGER, "Quản lý dự án")
            add_member(target, ENGINEER, "Kỹ sư")
            preview = as_user(MANAGER, msproject.preview, target, content)
            self.assertEqual((preview["total"], preview["groups"], preview["links"], preview["errors"]), (3, 1, 1, 0))
            done = as_user(MANAGER, msproject.run, target, content)
            self.assertEqual((done["tasks"], done["links"], done["assigned"]), (3, 1, 1))
            link = frappe.db.get_value("PM Task Dependency", {"project": target}, ["dep_type", "lag_days"], as_dict=True)
            self.assertEqual((link.dep_type, link.lag_days), ("FS", 1))
            self.assertEqual(frappe.db.count("Task", {"project": target, "parent_task": ["is", "set"]}), 2)
            self.assertRaises(frappe.PermissionError, as_user, ENGINEER, msproject.preview, target, content)
        finally:
            drop_project(target)

    def test_what_is_refused(self):
        bad = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Project xmlns="http://schemas.microsoft.com/project"/>'
        self.assertRaises(frappe.ValidationError, msproject.parse, self.project, bad)
        jump = (b'<Project xmlns="http://schemas.microsoft.com/project"><Tasks>'
                b'<Task><UID>1</UID><Name>A</Name><OutlineLevel>1</OutlineLevel></Task>'
                b'<Task><UID>2</UID><Name>B</Name><OutlineLevel>3</OutlineLevel></Task></Tasks></Project>')
        self.assertEqual(msproject.parse(self.project, jump)["errors"], 1)
        self.assertRaises(frappe.ValidationError, msproject.parse, self.project, b"<Tasks/>")
        circle = (b'<Project xmlns="http://schemas.microsoft.com/project"><Tasks>'
                  b'<Task><UID>1</UID><Name>A</Name><OutlineLevel>1</OutlineLevel>'
                  b'<PredecessorLink><PredecessorUID>2</PredecessorUID><Type>1</Type></PredecessorLink></Task>'
                  b'<Task><UID>2</UID><Name>B</Name><OutlineLevel>1</OutlineLevel>'
                  b'<PredecessorLink><PredecessorUID>1</PredecessorUID><Type>1</Type></PredecessorLink></Task>'
                  b'</Tasks></Project>')
        done = msproject.run(self.project, circle)
        self.assertEqual((done["tasks"], done["links"], len(done["skipped"])), (2, 1, 1))  # one of the two closes a circle


class TestClosing(ControlBase):
    def test_close_reopen_and_dossier(self):
        self.task("Còn mở")
        left = as_user(MANAGER, closing.check, self.project)
        self.assertGreaterEqual(left["tasks_open"], 1)
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, closing.close, self.project, "xong")
        self.assertRaises(frappe.ValidationError, as_user, MANAGER, closing.close, self.project, "")
        original = frappe.get_hooks

        def hooks(name=None, *args, **kwargs):
            if name == "project_close_handlers":
                return ["project_manager.tests.test_control.record_close"]
            return original(name, *args, **kwargs)

        RECORDED.clear()
        with patch.object(frappe, "get_hooks", side_effect=hooks):
            as_user(MANAGER, closing.close, self.project, "Bàn giao xong")
        self.assertEqual(RECORDED, [self.project])
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_state"), closing.CLOSED)
        as_user(MANAGER, closing.reopen, self.project, "Còn bảo hành")
        self.assertEqual(frappe.db.get_value("Project", self.project, "pm_state"), closing.RUNNING)
        url = closing.build_dossier(self.project, MANAGER)
        manifest = closing.manifest_of(url)
        paths = {e["path"] for e in manifest["entries"]}
        self.assertTrue({"du-an.json", "cong-viec.csv", "thanh-vien.csv", "rui-ro.csv"} <= paths)
        self.assertEqual((manifest["project"], manifest["built_by"]), (self.project, MANAGER))
        self.assertTrue(all(len(e["sha256"]) == 64 for e in manifest["entries"]))
        self.assertTrue(frappe.db.exists("Notification Log", {"for_user": MANAGER, "link": url}))
        self.assertRaises(frappe.PermissionError, closing.build_dossier, self.project, ENGINEER)


RECORDED = []


def record_close(project):
    RECORDED.append(project)

