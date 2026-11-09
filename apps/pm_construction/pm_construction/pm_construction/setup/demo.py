"""Demo data of the construction layer: a factory project built from the sample BOQ, a week of site diaries and an
approved work acceptance. Uses the core demo's people (demo.*@pm.localhost).

    bench --site <site> execute pm_construction.pm_construction.setup.demo.up
    bench --site <site> execute pm_construction.pm_construction.setup.demo.down   (before the core demo's down)
"""

import io
import uuid

import frappe
from frappe.utils import add_days, getdate, nowdate

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import boq, boq_import, diary
from project_manager.project_manager.services import forms, media, object_storage, projects, rollup, schedule
from project_manager.project_manager.setup import demo as core_demo

PROJECT_CODE = "DEMO-XD01"
# work item: (days it takes, share done per diary day)
PLAN = {"Đào móng băng bằng thủ công, đất cấp II": 4, "Bê tông lót móng đá 4x6, vữa mác 100": 2,
        "Sản xuất, lắp dựng cốt thép móng, đường kính ≤ 18 mm": 5, "Ván khuôn móng băng": 4,
        "Bê tông móng đá 1x2, mác 250": 3}


def up():
    if frappe.db.exists("Project", {"pm_code": PROJECT_CODE}):
        print("Construction demo already present")
        return
    frappe.set_user("Administrator")
    core_demo._people()
    manager, commander, engineer, supervisor, lead = (p[0] for p in core_demo.PEOPLE)
    start = getdate(add_days(nowdate(), -12))
    project = projects.create({"project_name": "Nhà xưởng Tân Uyên – Bình Dương", "pm_code": PROJECT_CODE,
                               "pm_state": "Đang thực hiện", "expected_start_date": start, "pm_manager": manager})["name"]
    for email, _name, role in core_demo.PEOPLE[1:]:
        projects.add_member(project, email, role)
    frappe.set_user(manager)
    version = boq.import_version(project, boq_import.template_file(), "du-toan-nha-xuong.xlsx", "Dự toán được duyệt")
    boq.approve(version.name)
    frappe.set_user("Administrator")
    tasks = {r.subject: r for r in frappe.get_all("Task", filters={"project": project, "is_group": 0},
                                                 fields=["name", "subject", "pmc_planned_qty"], order_by="pm_path asc")}
    _dates(tasks, start)
    _diaries(project, tasks, engineer, commander)
    _acceptance(project, tasks, engineer, commander)
    rollup.reconcile(project)
    schedule.refresh(project)
    frappe.db.commit()
    print(f"Construction demo created: {project}")


def _dates(tasks, start) -> None:
    """Back-to-back dates, a little overlap, so that the Gantt and the S-curve have a shape."""
    day = start
    for name, row in tasks.items():
        length = PLAN.get(name, 6)
        frappe.db.set_value("Task", row.name, {"exp_start_date": day, "exp_end_date": add_days(day, length - 1)},
                            update_modified=False)
        day = add_days(day, max(1, length - 1))


def _diaries(project, tasks, engineer, commander) -> None:
    order = [name for name in PLAN if name in tasks]
    done = {name: 0.0 for name in order}
    days = [add_days(nowdate(), -offset) for offset in range(7, 0, -1)]
    days = [d for d in days if getdate(d).weekday() != 6]  # no work on Sundays
    for number, day in enumerate(days):
        rows = []
        for index, name in enumerate(order):
            if index > number // 2:  # work items start one after the other
                break
            planned = tasks[name].pmc_planned_qty
            step = round(planned / PLAN[name], 3)
            if done[name] + step > planned:
                step = round(planned - done[name], 3)
            if step > 0:
                done[name] += step
                rows.append({"task": tasks[name].name, "qty": step})
        frappe.set_user(engineer)
        values = {"weather": "Mưa nhỏ" if number == 2 else "Nắng", "workers": 14 + number, "temperature": "27–33 °C",
                  "work_summary": "Thi công phần móng theo kế hoạch.",
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


def _acceptance(project, tasks, engineer, commander) -> None:
    dig = tasks.get("Đào móng băng bằng thủ công, đất cấp II")
    if not dig:
        return
    frappe.set_user(engineer)
    name = forms.start(K.QTY_ACCEPTANCE_CODE, project, dig.name)["name"]
    signature = forms.attach(name, core_demo.SIGNATURE, "chu-ky.png")
    forms.submit(name, {"ngay_nghiem_thu": nowdate(), K.QTY_FIELD: dig.pmc_planned_qty,
                        "thanh_phan_truc_tiep_nghiem_thu": [{"ho_va_ten": "Lê Chỉ Huy", "chuc_vu": "Chỉ huy trưởng",
                                                             "don_vi": "Nhà thầu"}] * 3,
                        "chat_luong_cong_viec": [{"ket_qua": "Đạt"} for _ in range(4)],
                        "ket_luan": "Chấp nhận nghiệm thu", "dai_dien_nha_thau_ky": [signature],
                        "dai_dien_tu_van_giam_sat_ky": [signature]})
    frappe.set_user(commander)
    forms.approve(name, "Đạt yêu cầu")
    frappe.set_user("Administrator")


def down():
    frappe.set_user("Administrator")
    for project in frappe.get_all("Project", filters={"pm_code": PROJECT_CODE}, pluck="name"):
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
        for doctype in ("PMC Diary Quantity", "PMC Site Diary", "PMC BOQ Item", "PMC BOQ", "PM Activity",
                        "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member",
                        "PM Form Submission", "PM Gate Requirement", "PM Task Dependency", "PM Baseline Task",
                        "PM Baseline Curve", "PM Baseline", "PM Media", "PM Follow", "PM Document Version",
                        "PM Document"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
    frappe.db.commit()
    print("Construction demo removed")
