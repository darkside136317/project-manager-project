"""Import a WBS from an Excel sheet into a project (prompt 4.10): check first (dry run), then write in one go.

The sheet (first worksheet, first row = headers, matched without accents or case):

    Mã WBS | Tên công việc | Loại | Bắt đầu | Kết thúc | Trọng số | Người phụ trách | Ghi chú

* "Mã WBS" gives the tree: 1, 1.1, 1.1.2 ... A row's parent is the row whose code is its code without the last part,
  and must come earlier in the sheet. Rows that have children become groups. Order = order of the sheet.
* "Tên công việc" is required. "Loại" is a PM Node Type (optional). Dates are Excel dates or dd/mm/yyyy.
* "Người phụ trách" (an e-mail, or the full name of a project member) becomes the accountable person of the task.

`preview` never writes; `run` re-checks the same file and refuses it while it has errors. The tasks go under `parent`
(or the project's roots), after the existing ones.
"""

import io
import re
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import flt, getdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import assert_project_capability, get_access, project_in
from project_manager.project_manager.services import assignments, tree
from project_manager.project_manager.services.text import plain as _plain

MAX_ROWS = 5000
COLUMNS = {
    "code": ("ma wbs", "wbs", "ma"),
    "subject": ("ten cong viec", "ten", "cong viec", "noi dung"),
    "node_type": ("loai", "loai nut"),
    "start": ("bat dau", "ngay bat dau"),
    "end": ("ket thuc", "ngay ket thuc", "han"),
    "weight": ("trong so",),
    "owner": ("nguoi phu trach", "phu trach", "chiu trach nhiem"),
    "note": ("ghi chu", "mo ta"),
}
HEADERS = ("Mã WBS", "Tên công việc", "Loại", "Bắt đầu", "Kết thúc", "Trọng số", "Người phụ trách", "Ghi chú")
CODE = re.compile(r"^\d+(\.\d+)*$")


def _read(content: bytes) -> list[list]:
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        frappe.throw(_("Không đọc được tệp Excel (.xlsx)"))
    sheet = book.worksheets[0]
    rows = []
    for row in sheet.iter_rows(values_only=True):
        if len(rows) > MAX_ROWS + 1:
            frappe.throw(_("Tệp có quá {0} dòng").format(MAX_ROWS))
        rows.append(list(row))
    book.close()
    return rows


def _columns(header: list) -> dict:
    found = {}
    for index, cell in enumerate(header):
        name = _plain(cell)
        for key, names in COLUMNS.items():
            if key not in found and name in names:
                found[key] = index
    for key in ("code", "subject"):
        if key not in found:
            frappe.throw(_("Thiếu cột {0}").format(HEADERS[0] if key == "code" else HEADERS[1]))
    return found


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(text)


def _code(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value or "").strip().rstrip(".")


def _people(project: str) -> dict:
    """{e-mail or plain full name: user} of the project's current members."""
    rows = frappe.db.sql(
        """select m.user, u.full_name from `tabPM Project Member` m join `tabUser` u on u.name = m.user
           where m.project = %s and m.is_active = 1 and u.enabled = 1""", project, as_dict=True)
    out = {}
    for row in rows:
        out[row.user.lower()] = row.user
        if row.full_name:
            out.setdefault(_plain(row.full_name), row.user)
    return out


def parse(project: str, content: bytes) -> dict:
    """Rows with their errors and warnings; nothing is written."""
    rows = _read(content)
    if not rows:
        frappe.throw(_("Tệp trống"))
    columns = _columns(rows[0])
    node_types = {_plain(n.name): n for n in frappe.get_all("PM Node Type", fields=["name", "is_group"])}
    people = _people(project)
    items, seen, errors = [], {}, 0

    def cell(raw, key):
        index = columns.get(key)
        return raw[index] if index is not None and index < len(raw) else None

    for line, raw in enumerate(rows[1:], start=2):
        if not any(v not in (None, "") for v in raw):
            continue
        item = {"line": line, "errors": [], "warnings": []}
        code, subject = _code(cell(raw, "code")), str(cell(raw, "subject") or "").strip()
        item.update(code=code, subject=subject)
        if not CODE.match(code):
            item["errors"].append(_("Mã WBS \"{0}\" không hợp lệ (ví dụ 1, 1.2, 1.2.3)").format(code))
        elif code in seen:
            item["errors"].append(_("Mã WBS {0} trùng với dòng {1}").format(code, seen[code]["line"]))
        if not subject:
            item["errors"].append(_("Thiếu tên công việc"))
        parent_code = code.rsplit(".", 1)[0] if "." in code else None
        if parent_code and parent_code not in seen:
            item["errors"].append(_("Chưa có dòng của mục cha {0} ở phía trên").format(parent_code))
        item["parent_code"] = parent_code
        kind = cell(raw, "node_type")
        if kind not in (None, ""):
            match = node_types.get(_plain(kind))
            if match:
                item["node_type"] = match.name
            else:
                item["warnings"].append(_("Không có loại \"{0}\": bỏ qua").format(kind))
        for key in ("start", "end"):
            try:
                item[key] = _date(cell(raw, key))
            except ValueError as e:
                item["errors"].append(_("Ngày không hợp lệ: {0}").format(e))
                item[key] = None
        if item.get("start") and item.get("end") and item["end"] < item["start"]:
            item["errors"].append(_("Ngày kết thúc trước ngày bắt đầu"))
        weight = cell(raw, "weight")
        item["weight"] = flt(weight) if weight not in (None, "") else 0
        owner = str(cell(raw, "owner") or "").strip()
        if owner:
            user = people.get(owner.lower()) or people.get(_plain(owner))
            if user:
                item["owner"] = user
            else:
                item["warnings"].append(_("\"{0}\" không phải thành viên dự án: chưa giao").format(owner))
        item["note"] = str(cell(raw, "note") or "").strip() or None
        errors += bool(item["errors"])
        items.append(item)
        if CODE.match(code) and code not in seen:
            seen[code] = item
    parents = {i["parent_code"] for i in items if i.get("parent_code")}
    for item in items:
        item["is_group"] = 1 if item["code"] in parents or (
            item.get("node_type") and node_types[_plain(item["node_type"])].is_group) else 0
        if item["is_group"] and item.get("owner"):
            item["warnings"].append(_("Nhóm công việc: người phụ trách vẫn được giao cho cả nhóm"))
    return {"rows": items, "errors": errors, "total": len(items),
            "groups": sum(i["is_group"] for i in items), "assigned": sum(1 for i in items if i.get("owner"))}


def preview(project: str, content: bytes) -> dict:
    assert_project_capability(project, "plan.edit")
    return parse(project, content)


def run(project: str, content: bytes, parent: str | None = None) -> dict:
    assert_project_capability(project, "plan.edit")
    if parent and frappe.db.get_value("Task", parent, "project") != project:
        frappe.throw(_("Việc cha thuộc dự án khác"))
    result = parse(project, content)
    if result["errors"]:
        frappe.throw(_("Tệp còn {0} dòng lỗi: hãy sửa rồi nhập lại").format(result["errors"]))
    if not result["rows"]:
        frappe.throw(_("Tệp không có dòng công việc nào"))
    nodes = [{"key": i["code"], "parent_key": i["parent_code"], "subject": i["subject"], "is_group": i["is_group"],
              "pm_node_type": i.get("node_type"), "exp_start_date": i.get("start"), "exp_end_date": i.get("end"),
              "task_weight": i["weight"], "description": i.get("note")} for i in result["rows"]]
    names = tree.bulk_insert(project, nodes, parent)
    assigned = 0
    for item, name in zip(result["rows"], names):
        if item.get("owner") and project_in(get_access(item["owner"]).read, project):
            assignments.assign(name, C.ACCOUNTABLE, user=item["owner"], note=_("Nhập từ Excel"))
            assigned += 1
    from project_manager.project_manager.services import activity

    activity.record("Project", project, "Thay đổi", _("Nhập {0} công việc từ Excel").format(len(names)),
                    data={"tasks": len(names), "assigned": assigned, "parent": parent})
    return {"tasks": len(names), "assigned": assigned}


def template_file() -> bytes:
    """An empty sheet with the headers and two example rows."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = "WBS"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    today = getdate()
    sheet.append(["1", "Phần móng", "", None, None, None, "", ""])
    sheet.append(["1.1", "Đào đất hố móng", "", today, today, 1, "", "Ví dụ: xóa dòng này"])
    for column, width in zip("ABCDEFGH", (10, 40, 14, 12, 12, 10, 28, 30)):
        sheet.column_dimensions[column].width = width
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()

