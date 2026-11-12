"""Closing a project, and its dossier (gói hồ sơ dự án): the extension point for an archive.

* check: what is still open (work, risks, issues, change requests, forms, a draft budget, alerts), so the manager
  knows before closing.
* close: the project goes to "Đóng" (ERPNext status Completed), its open alerts end, every function of the hook
  `project_close_handlers` is called with the project (an archive bridge can take the dossier from there), and the
  activity records who closed it and why. reopen brings it back to "Đang thực hiện".
* dossier: a ZIP built on the long queue and kept as a private file of the project:
  - manifest.json: the project, who built it and when, and every entry with its size, SHA-256 and where it came from;
  - du-an.json, cong-viec.csv, thanh-vien.csv, rui-ro.csv, van-de.csv, phat-sinh.csv, ngan-sach.csv (finance.view);
  - tai-lieu/<category>/: the current version of each document; bieu-mau/<template>/: the approved forms as PDF;
  - what the layers add (hook `pm_dossier_parts`: functions (project) returning [{"path", "content", "source"}]).
  The person who asked is told when it is ready. Built as that person: only what they may read goes in.
Who: project.edit closes, reopens and builds the dossier.
"""

import csv
import hashlib
import io
import json
import re
import zipfile

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.policy import (
    assert_project_capability,
    get_access,
    has_project_capability,
    project_in,
)
from project_manager.project_manager.services import activity, notify

CLOSED, RUNNING = "Đóng", "Đang thực hiện"
MAX_BYTES = 1024 * 1024 * 1024  # 1 GB of files in one dossier


def check(project: str) -> dict:
    """What is still open in the project."""
    if not project_in(get_access().read, project):
        frappe.throw(_("Bạn không xem được dự án này"), frappe.PermissionError)
    count = frappe.db.count
    return {
        "tasks_open": count("Task", {"project": project, "is_group": 0, "status": ["not in", [C.COMPLETED, C.CANCELLED]]}),
        "risks_open": count("PM Risk", {"project": project, "status": ["in", ["Mở", "Đang xử lý"]]}),
        "issues_open": count("PM Issue", {"project": project, "status": ["in", ["Mở", "Đang xử lý"]]}),
        "changes_waiting": count("PM Change Request", {"project": project, "status": ["in", ["Nháp", "Chờ duyệt"]]}),
        "forms_waiting": count("PM Form Submission", {"project": project, "state": C.SUB_SUBMITTED}),
        "budget_draft": count("PM Budget", {"project": project, "status": "Nháp"}),
        "alerts_open": count("PM Alert", {"project": project, "state": ["in", ["Đang mở", "Đã xác nhận"]]}),
        "state": frappe.db.get_value("Project", project, "pm_state"),
        "dossiers": dossiers(project),
    }


def close(project: str, note: str = "") -> dict:
    assert_project_capability(project, "project.edit")
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Ghi lý do, kết luận khi đóng dự án"))
    state = frappe.db.get_value("Project", project, "pm_state")
    if state == CLOSED:
        frappe.throw(_("Dự án đã đóng"))
    if state == "Hủy":
        frappe.throw(_("Dự án đã hủy"))
    left = check(project)
    frappe.db.set_value("Project", project, {"pm_state": CLOSED, "status": "Completed"})
    frappe.db.sql("""update `tabPM Alert` set state = 'Đã hết', closed_on = %s
                     where project = %s and state in ('Đang mở', 'Đã xác nhận')""", (now_datetime(), project))
    activity.record("Project", project, "Trạng thái", _("Đóng dự án: {0}").format(note),
                    data={"state": CLOSED, "left": {k: v for k, v in left.items() if k != "dossiers"}})
    handled = []
    for path in frappe.get_hooks("project_close_handlers") or []:
        frappe.get_attr(path)(project)
        handled.append(path)
    return {"state": CLOSED, "left": left, "handlers": handled}


def reopen(project: str, note: str = "") -> dict:
    assert_project_capability(project, "project.edit")
    if frappe.db.get_value("Project", project, "pm_state") != CLOSED:
        frappe.throw(_("Chỉ mở lại được dự án đã đóng"))
    note = (note or "").strip()
    if not note:
        frappe.throw(_("Ghi lý do mở lại dự án"))
    frappe.db.set_value("Project", project, {"pm_state": RUNNING, "status": "Open"})
    activity.record("Project", project, "Trạng thái", _("Mở lại dự án: {0}").format(note), data={"state": RUNNING})
    return {"state": RUNNING}


# --- the dossier ----------------------------------------------------------------------------------------------------------

def dossiers(project: str) -> list[dict]:
    return frappe.get_all("File", filters={"attached_to_doctype": "Project", "attached_to_name": project,
                                           "file_name": ["like", "ho-so-%.zip"]},
                          fields=["name", "file_name", "file_url", "file_size", "creation", "owner"],
                          order_by="creation desc", limit_page_length=10)


def request_dossier(project: str) -> dict:
    assert_project_capability(project, "project.edit")
    frappe.enqueue("project_manager.project_manager.services.closing.build_dossier", queue="long", timeout=3600,
                   project=project, user=frappe.session.user, enqueue_after_commit=True,
                   job_id=f"pm-dossier:{project}", deduplicate=True)
    return {"queued": True}


def _safe(text: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", str(text or "")).strip(" .-")
    return text[:120] or "khong-ten"


def _csv(rows: list, columns: list[tuple[str, str]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label for _key, label in columns])
    for row in rows:
        writer.writerow(["" if row.get(key) is None else row.get(key) for key, _label in columns])
    return ("﻿" + out.getvalue()).encode("utf-8")


class _Zip:
    def __init__(self):
        self.buffer = io.BytesIO()
        self.archive = zipfile.ZipFile(self.buffer, "w", compression=zipfile.ZIP_DEFLATED)
        self.entries, self.size, self.paths = [], 0, set()

    def add(self, path: str, content: bytes, source: str) -> None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        base, number = path, 1
        while path in self.paths:  # two documents with the same title
            number += 1
            stem, dot, ext = base.rpartition(".")
            path = f"{stem} ({number}).{ext}" if dot else f"{base} ({number})"
        self.size += len(content)
        if self.size > MAX_BYTES:
            frappe.throw(_("Hồ sơ vượt quá 1 GB"))
        self.paths.add(path)
        self.archive.writestr(path, content)
        self.entries.append({"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                             "source": source})

    def close(self, manifest: dict) -> bytes:
        self.archive.writestr("manifest.json", json.dumps({**manifest, "entries": self.entries}, ensure_ascii=False,
                                                          indent=2, default=str))
        self.archive.close()
        return self.buffer.getvalue()


def _project_parts(box: _Zip, project: str) -> None:
    from project_manager.project_manager.services import object_storage

    info = frappe.get_doc("Project", project)
    fields = ("name", "project_name", "pm_code", "pm_state", "company", "expected_start_date", "expected_end_date",
              "percent_complete", "pm_manager", "pm_health", "pm_spi", "pm_forecast_end")
    box.add("du-an.json", json.dumps({f: info.get(f) for f in fields}, ensure_ascii=False, indent=2, default=str),
            f"Project {project}")
    tasks = frappe.get_list("Task", filters={"project": project},
                            fields=["name", "pm_wbs_code", "subject", "pm_node_type", "is_group", "status", "progress",
                                    "exp_start_date", "exp_end_date", "act_start_date", "act_end_date", "pm_accountable"],
                            order_by="pm_path asc", limit_page_length=0)
    box.add("cong-viec.csv", _csv(tasks, [("pm_wbs_code", "Mã WBS"), ("subject", "Công việc"), ("pm_node_type", "Loại"),
                                          ("status", "Trạng thái"), ("progress", "Tiến độ (%)"),
                                          ("exp_start_date", "Bắt đầu kế hoạch"), ("exp_end_date", "Kết thúc kế hoạch"),
                                          ("act_start_date", "Bắt đầu thực tế"), ("act_end_date", "Kết thúc thực tế"),
                                          ("pm_accountable", "Chịu trách nhiệm"), ("name", "Mã hệ thống")]), "Task")
    members = frappe.get_all("PM Project Member", filters={"project": project},
                             fields=["user", "project_role", "is_active", "valid_from", "valid_to"], limit_page_length=0)
    box.add("thanh-vien.csv", _csv(members, [("user", "Người"), ("project_role", "Vai trò"), ("is_active", "Đang hiệu lực"),
                                             ("valid_from", "Từ ngày"), ("valid_to", "Đến ngày")]), "PM Project Member")
    if project_in(get_access().read_tasks, project):
        for doctype, path, columns in (
                ("PM Risk", "rui-ro.csv", [("name", "Mã"), ("title", "Rủi ro"), ("level", "Mức"), ("status", "Trạng thái"),
                                           ("owner_user", "Phụ trách"), ("plan", "Kế hoạch ứng phó")]),
                ("PM Issue", "van-de.csv", [("name", "Mã"), ("title", "Vấn đề"), ("priority", "Ưu tiên"),
                                            ("status", "Trạng thái"), ("resolution", "Cách giải quyết")]),
                ("PM Change Request", "phat-sinh.csv", [("name", "Mã"), ("title", "Nội dung"), ("status", "Trạng thái"),
                                                        ("cost_impact", "Chi phí"), ("days_impact", "Ngày")])):
            rows = frappe.get_all(doctype, filters={"project": project}, fields=[k for k, _l in columns], limit_page_length=0)
            box.add(path, _csv(rows, columns), doctype)
    if has_project_capability(project, "finance.view", "budget.manage"):
        from project_manager.project_manager.services import budget

        name = budget.current(project)
        if name:
            lines = frappe.get_all("PM Budget Line", filters={"parent": name, "parenttype": "PM Budget"},
                                   fields=["category", "task", "description", "amount"], order_by="idx asc")
            box.add("ngan-sach.csv", _csv(lines, [("category", "Khoản mục"), ("task", "Công việc"),
                                                 ("description", "Diễn giải"), ("amount", "Số tiền")]), f"PM Budget {name}")
    versions = frappe.db.sql("""select d.name, d.title, d.category, v.version_no, v.file_name, v.object_key
                                from `tabPM Document` d join `tabPM Document Version` v
                                  on v.document = d.name and v.version_no = d.current_version
                                where d.project = %s order by d.category, d.title""", project, as_dict=True)
    readable = set(frappe.get_list("PM Document", filters={"project": project}, pluck="name", limit_page_length=0))
    for row in versions:
        if row.name not in readable or not object_storage.configured():
            continue
        content = object_storage.get(row.object_key, "documents")
        box.add(f"tai-lieu/{_safe(row.category)}/{_safe(row.title)} - v{row.version_no} - {_safe(row.file_name)}", content,
                f"PM Document {row.name} v{row.version_no}")
    from project_manager.project_manager.services import form_output

    for name, code in frappe.get_list("PM Form Submission", filters={"project": project, "state": C.SUB_APPROVED},
                                      fields=["name", "template_code"], as_list=True, limit_page_length=0):
        file_name, content = form_output.pdf_of(name)
        box.add(f"bieu-mau/{_safe(code)}/{file_name}", content, f"PM Form Submission {name}")
    for path in frappe.get_hooks("pm_dossier_parts") or []:
        for part in frappe.get_attr(path)(project) or []:
            box.add(part["path"], part["content"], part.get("source") or path)


def build_dossier(project: str, user: str) -> str:
    """Build the ZIP as `user`, keep it as a private file of the project, tell them. Returns the file's URL."""
    caller = frappe.session.user
    frappe.set_user(user)
    policy.clear_cache()
    try:
        assert_project_capability(project, "project.edit")
        box = _Zip()
        _project_parts(box, project)
        info = frappe.db.get_value("Project", project, ["project_name", "pm_code", "pm_state"], as_dict=True)
        content = box.close({"format": "pm-dossier/1", "project": project, "project_name": info.project_name,
                             "code": info.pm_code, "state": info.pm_state, "built_on": now_datetime(), "built_by": user})
        stamp = now_datetime().strftime("%Y%m%d-%H%M")
        file = frappe.get_doc({"doctype": "File", "file_name": f"ho-so-{_safe(info.pm_code or project)}-{stamp}.zip",
                               "content": content, "is_private": 1, "attached_to_doctype": "Project",
                               "attached_to_name": project})
        file.insert(ignore_permissions=True)
        activity.record("Project", project, "Thay đổi", _("Xuất hồ sơ dự án: {0} mục, {1} MB").format(
            len(box.entries), flt(len(content) / 1048576, 1)), data={"file": file.name, "entries": len(box.entries)})
        notify.notify_user(user, _("Hồ sơ dự án {0} đã sẵn sàng").format(info.project_name), file.file_url, "Project", project)
        return file.file_url
    finally:
        frappe.set_user(caller)
        policy.clear_cache()


def manifest_of(url: str) -> dict:
    file = frappe.get_doc("File", {"file_url": url})
    with zipfile.ZipFile(io.BytesIO(file.get_content())) as archive:
        return json.loads(archive.read("manifest.json"))

