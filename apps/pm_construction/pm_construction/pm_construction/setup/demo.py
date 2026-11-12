"""Demo data of the construction layer, the pilot scenario of M7 (docs/HUONG_DAN_THI_DIEM.md): a factory project
built from the sample BOQ, three weeks of site diaries, acceptances. Uses the core demo's people (demo.*@pm.localhost).

* PHẦN MÓNG (Tự động): every work item is done; four are accepted, the last acceptance waits for the site commander.
  Approving it passes the phase by itself to PHẦN THÂN (Cần duyệt).
* PHẦN THÂN: the columns are three days late and slow: their alert "Quá hạn" opened three days ago and climbed to the
  site commander; the column rebar is at risk.
* Yesterday's site diary is missing: alert "Thiếu nhật ký thi công".
* M9: the crew leader does the structure here and in the town house (core demo): overloaded, a conflict between
  projects; the crane is booked for the columns, and by the town house on some of the same days.
* M10: a cost budget made from the estimate (illustrative split), so the earned value has actual costs to weigh; a
  high risk on the rebar supply, an issue about the crane booked twice, a change request waiting for the manager.

    bench --site <site> execute pm_construction.pm_construction.setup.demo.up
    bench --site <site> execute pm_construction.pm_construction.setup.demo.down   (before the core demo's down)
"""

import io
import uuid
from datetime import timedelta

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import boq, boq_import, diary
from project_manager.project_manager import constants as C
from project_manager.project_manager.services import (
    alerts,
    assignments,
    forms,
    media,
    object_storage,
    phases,
    projects,
    rollup,
    schedule,
)
from project_manager.project_manager.setup import demo as core_demo

from pm_construction.pm_construction.setup import demo_site

PROJECT_CODE = "DEMO-XD01"
# planned window of each work item, in days from today, in the order of the BOQ (pm_path)
WINDOWS = [(-18, -15), (-14, -13), (-13, -10), (-11, -9), (-9, -7),  # PHẦN MÓNG
           (-6, -3), (-4, 1), (2, 8), (9, 15), (14, 20),  # PHẦN THÂN
           (21, 26), (25, 30)]  # PHẦN HOÀN THIỆN
FOUNDATION = 5  # the first five work items
SLOW = {5: 0.3, 6: 0.1}  # share of its quantity a late work item reached (index in WINDOWS)
GATES = {"PHẦN MÓNG": phases.AUTO, "PHẦN THÂN": phases.APPROVAL, "PHẦN HOÀN THIỆN": phases.MANUAL}
LATE_ALERT_AGE = 3  # days the overdue alert of the columns has been open


def up():
    if frappe.db.exists("Project", {"pm_code": PROJECT_CODE}):
        print("Construction demo already present")
        return
    frappe.set_user("Administrator")
    core_demo._people()
    manager, commander, engineer, supervisor, lead = (p[0] for p in core_demo.PEOPLE)
    today = getdate(nowdate())
    project = projects.create({"project_name": "Nhà xưởng Tân Uyên – Bình Dương", "pm_code": PROJECT_CODE,
                               "pm_state": "Đang thực hiện", "expected_start_date": add_days(today, WINDOWS[0][0]),
                               "expected_end_date": add_days(today, WINDOWS[-1][1]), "pm_manager": manager})["name"]
    for email, _name, role in core_demo.PEOPLE[1:]:
        projects.add_member(project, email, role)
    demo_site.masters()  # materials and norms first: approving the BOQ builds the material plan from them
    frappe.set_user(manager)
    version = boq.import_version(project, boq_import.template_file(), "du-toan-nha-xuong.xlsx", "Dự toán được duyệt")
    boq.approve(version.name)
    frappe.set_user("Administrator")
    works = frappe.get_all("Task", filters={"project": project, "is_group": 0},
                           fields=["name", "subject", "pmc_planned_qty"], order_by="pm_path asc")
    _dates(works, today)
    for index, work in enumerate(works):  # the engineer answers for every work item, the crew does the structure
        given = [(assignments.assign(work.name, C.ACCOUNTABLE, user=engineer), engineer)]
        if index < len(WINDOWS) - 2:
            given.append((assignments.assign(work.name, C.RESPONSIBLE, user=lead), lead))
        for assignment, person in given:  # and they took it
            frappe.set_user(person)
            assignments.respond(assignment, True)
        frappe.set_user("Administrator")
    for subject, mode in GATES.items():
        group = frappe.db.get_value("Task", {"project": project, "subject": subject, "is_group": 1}, "name")
        if group:
            frappe.db.set_value("Task", group, "pm_gate_mode", mode, update_modified=False)
    _diaries(project, works, today, engineer, commander)
    _acceptances(project, works[:FOUNDATION], engineer, commander)
    demo_site.build(project, works, today, {"manager": manager, "commander": commander, "engineer": engineer,
                                            "lead": lead}, WINDOWS)
    demo_site.bookings(project, works, today, core_demo.PROJECT_CODE)
    _control(project, works, today, manager, commander, engineer)
    rollup.reconcile(project)
    schedule.refresh(project)
    phases.check(project)
    frappe.db.commit()
    if len(works) > FOUNDATION:
        _alerts(works[FOUNDATION])
    from project_manager.project_manager.services import performance, workload

    for weeks in (2, 1):  # the crews' productivity of the last weeks, kept
        performance.snapshot_week(add_days(workload.monday(today), -7 * weeks))
    frappe.db.commit()
    print(f"Construction demo created: {project}")


SPLIT = (("Vật tư", 0.6), ("Nhân công", 0.25), ("Máy thi công", 0.15))  # illustrative split of the estimate


def _control(project, works, today, manager, commander, engineer) -> None:
    from project_manager.project_manager.services import budget, control

    sections = frappe.get_all("Task", filters={"project": project, "is_group": 1, "pm_level": 1},
                              fields=["name", "pm_path"], order_by="pm_path asc")
    lines = []
    for section in sections:
        estimate = frappe.db.sql("""select sum(pmc_estimate_value) from `tabTask` where project = %s and is_group = 0
                                    and pm_path like %s""", (project, f"{section.pm_path}.%"))[0][0] or 0
        for category, share in SPLIT:
            if estimate:
                lines.append({"category": category, "task": section.name, "amount": round(estimate * 0.92 * share, -3),
                              "description": "92% giá trị dự toán, chia minh họa"})
    if lines:
        frappe.set_user(manager)
        draft = budget.save_draft(project, "Ngân sách chi phí", lines, "Lập từ dự toán được duyệt")
        budget.approve(draft["name"])
    frappe.set_user(commander)
    control.save_risk(project, {"title": "Thép cột về chậm", "category": "Cung ứng", "probability": 3, "impact": 4,
                                "owner_user": commander, "status": "Đang xử lý", "due_date": add_days(today, 3),
                                "plan": "Đặt thêm nhà cung cấp thứ hai, điều thép từ kho công ty"})
    control.save_issue(project, {"title": "Cần trục trùng lịch với dự án nhà phố", "priority": "Cao", "owner_user": manager,
                                 "due_date": add_days(today, 3), "description": "Hai dự án đặt cùng cần trục 3 ngày."})
    if len(works) > 6:
        frappe.set_user(engineer)
        change = control.save_change(project, {"title": "Tăng mác bê tông cột lên 300", "reason": "Thay đổi thiết kế",
                                               "cost_impact": 28_000_000, "days_impact": 2},
                                     [{"task": works[6].name, "new_end": add_days(today, 3)}])
        control.submit_change(change["name"])
    frappe.set_user("Administrator")


def _dates(works, today) -> None:
    for row, (first, last) in zip(works, WINDOWS, strict=False):
        frappe.db.set_value("Task", row.name, {"exp_start_date": add_days(today, first),
                                               "exp_end_date": add_days(today, last)}, update_modified=False)


def _diaries(project, works, today, engineer, commander) -> None:
    """A diary each working day up to the day before yesterday (none yesterday) with the quantities of the day."""
    done = {row.name: 0.0 for row in works}
    days = [add_days(today, offset) for offset in range(WINDOWS[0][0], -1)]
    days = [d for d in days if getdate(d).weekday() != 6]  # no work on Sundays
    offsets = [(getdate(d) - today).days for d in days]
    worked = {index: [o for o in offsets if first <= o <= last] for index, (first, last) in enumerate(WINDOWS)}
    for number, day in enumerate(days):
        rows = []
        offset = offsets[number]
        for index, row in enumerate(works[:len(WINDOWS)]):
            if offset not in worked[index]:
                continue
            target = row.pmc_planned_qty * SLOW.get(index, 1.0)
            step = round(min(row.pmc_planned_qty / len(worked[index]), target - done[row.name]), 3)
            if offset == worked[index][-1] and index not in SLOW:
                step = round(row.pmc_planned_qty - done[row.name], 3)  # its last day completes it exactly
            if step > 0:
                done[row.name] += step
                rows.append({"task": row.name, "qty": step})
        frappe.set_user(engineer)
        values = {"weather": "Mưa nhỏ" if number % 5 == 2 else "Nắng", "workers": 12 + number % 6,
                  "temperature": "27–33 °C", "work_summary": "Thi công theo kế hoạch tuần.",
                  "safety": "Công nhân đủ bảo hộ; khu đào có rào chắn."}
        saved = diary.save(project, day, values, rows, str(uuid.uuid4()))
        media_keys = _photo(saved["name"]) if number == len(days) - 1 else []
        diary.submit(saved["name"], media_keys)
        if number < len(days) - 2:
            frappe.set_user(commander)
            diary.confirm(saved["name"])
    frappe.set_user("Administrator")


def _photo(name) -> list[str]:
    if not object_storage.configured():
        return []
    from PIL import Image, ImageDraw

    picture = Image.new("RGB", (1200, 900), (150, 130, 110))
    pen = ImageDraw.Draw(picture)
    for y in range(0, 900, 90):
        pen.rectangle((0, y, 1200, y + 40), fill=(120, 100, 85))  # trench lines, roughly
    raw = io.BytesIO()
    picture.save(raw, "JPEG", quality=80)
    key = str(uuid.uuid4())
    media.upload("PMC Site Diary", name, key, raw.getvalue(), "mong.jpg", nowdate() + " 16:30:00", 11.0632, 106.7598)
    return [key]


def _acceptance_form(project, work, engineer) -> str:
    frappe.set_user(engineer)
    name = forms.start(K.QTY_ACCEPTANCE_CODE, project, work.name)["name"]
    signature = forms.attach(name, core_demo.SIGNATURE, "chu-ky.png")
    forms.submit(name, {"ngay_nghiem_thu": nowdate(), K.QTY_FIELD: work.pmc_planned_qty,
                        "thanh_phan_truc_tiep_nghiem_thu": [{"ho_va_ten": "Lê Chỉ Huy", "chuc_vu": "Chỉ huy trưởng",
                                                             "don_vi": "Nhà thầu"}] * 3,
                        "chat_luong_cong_viec": [{"ket_qua": "Đạt"} for _ in range(4)],
                        "ket_luan": "Chấp nhận nghiệm thu", "dai_dien_nha_thau_ky": [signature],
                        "dai_dien_tu_van_giam_sat_ky": [signature]})
    return name


def _acceptances(project, works, engineer, commander) -> None:
    """The foundation's work items: all accepted but the last, whose record waits for the site commander."""
    for work in works:
        name = _acceptance_form(project, work, engineer)
        if work is not works[-1]:
            frappe.set_user(commander)
            forms.approve(name, "Đạt yêu cầu")
    frappe.set_user("Administrator")


def _alerts(columns) -> None:
    """Today's alerts; the overdue alert of the columns opened days ago, so it has climbed to the site commander."""
    alerts.run_daily()
    late = frappe.db.get_value("PM Alert", {"rule_type": alerts.OVERDUE, "reference_name": columns.name,
                                            "state": alerts.OPEN}, "name")
    if late:
        frappe.db.set_value("PM Alert", late, "opened_on", now_datetime() - timedelta(days=LATE_ALERT_AGE),
                            update_modified=False)
        alerts.escalate()


def down():
    frappe.set_user("Administrator")
    found = frappe.get_all("Project", filters={"pm_code": PROJECT_CODE}, pluck="name")
    for project in found or [None]:
        demo_site.remove(project)  # stock, machines, crews (and the demo's own masters)
    for project in found:
        photos = frappe.get_all("PM Media", filters={"project": project}, fields=["object_key", "thumb_key"])
        files = frappe.get_all("PM Document Version", filters={"project": project}, pluck="object_key")
        if object_storage.configured():
            object_storage.delete_many([p.object_key for p in photos], "media")
            object_storage.delete_many([p.thumb_key for p in photos], "thumbs")
            object_storage.delete_many(files, "documents")
        for submission in frappe.get_all("PM Form Submission", filters={"project": project}, pluck="name"):
            for file in frappe.get_all("File", filters={"attached_to_doctype": "PM Form Submission",
                                                        "attached_to_name": str(submission)}, pluck="name"):
                frappe.delete_doc("File", file, force=True, ignore_permissions=True)
        core_demo.drop_control(project)
        for doctype in ("PMC Diary Quantity", "PMC Site Diary", "PMC BOQ Item", "PMC BOQ", "PM Activity",
                        "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member",
                        "PM Form Submission", "PM Gate Requirement", "PM Task Dependency", "PM Baseline Task",
                        "PM Baseline Curve", "PM Baseline", "PM Media", "PM Follow", "PM Document Version",
                        "PM Document", "PM Alert"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    frappe.db.commit()
    print("Construction demo removed")
