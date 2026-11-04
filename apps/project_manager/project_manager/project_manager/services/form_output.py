"""What leaves the system: the PDF of a form and the Excel of many forms.

The PDF of an approved form is made once and kept (private file + SHA-256), so what was approved stays what is printed
even if the company's name or a person's name changes later. A form not yet approved prints with a "bản nháp" mark and
nothing is kept. The page is rendered with autoescape on: answers are never HTML. Pictures go in as data URIs read from
this form's own attachments: wkhtmltopdf runs without local file access.
"""

import base64
import hashlib
import io
import json
import mimetypes

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, formatdate
from frappe.utils.pdf import get_pdf

from project_manager.project_manager import constants as C
from project_manager.project_manager.services import form_templates

TEMPLATE = "templates/pm_form_print.html"
MAX_EXPORT_ROWS = 5000


def _picture(item: dict, allowed: dict) -> str | None:
    file_name = allowed.get(item.get("file"))
    if not file_name:
        return None
    content = frappe.get_doc("File", file_name).get_content()
    if isinstance(content, str):
        content = content.encode()
    kind = mimetypes.guess_type(item["file"])[0] or "image/jpeg"
    return f"data:{kind};base64,{base64.b64encode(content).decode()}"


def _display(column_type: str, value) -> str:
    if value in (None, ""):
        return ""
    if column_type == C.F_CHECK:
        return _("Có") if value else _("Không")
    if column_type == C.F_DATE:
        return formatdate(value, "dd/MM/yyyy")
    return str(value)


def _sections(spec, data: dict, allowed: dict) -> list[dict]:
    """The answers, in template order, ready to print."""
    rows = []
    for field in spec["fields"]:
        kind, value = field["fieldtype"], data.get(field["fieldname"])
        row = {"label": field["label"], "kind": kind}
        if kind == C.F_TABLE:
            row["columns"] = [c["label"] for c in field["columns"]]
            row["rows"] = [[_display(c["type"], r.get(c["key"])) for c in field["columns"]] for r in value or []]
        elif kind in (C.F_IMAGE, C.F_SIGNATURE):
            row["pictures"] = [p for p in (_picture(i, allowed) for i in (value or [])) if p]
        else:
            text = _display(kind, value)
            row["text"] = f"{text} {field['unit']}".strip() if text and field["unit"] else text
        rows.append(row)
    return rows


def render_html(doc) -> str:
    spec = form_templates.spec(doc.template)
    files = frappe.get_all("File", filters={"attached_to_doctype": doc.doctype, "attached_to_name": str(doc.name)},
                           fields=["name", "file_url"])
    task = frappe.db.get_value("Task", doc.task, ["subject", "pm_wbs_code"], as_dict=True) if doc.task else None
    name_of = frappe.utils.get_fullname
    context = {
        "company": frappe.defaults.get_global_default("company") or "",
        "title": spec["title"], "code": f"{spec['code']} (phiên bản {spec['version']})", "number": doc.name,
        "project": frappe.db.get_value("Project", doc.project, "project_name"),
        "task": f"{task.pm_wbs_code or ''} {task.subject}".strip() if task else "",
        "state": doc.state, "approved": doc.state == C.SUB_APPROVED,
        "submitted": f"{name_of(doc.submitted_by)}, {format_datetime(doc.submitted_on, 'dd/MM/yyyy HH:mm')}" if doc.submitted_by else "",
        "reviewed": f"{name_of(doc.reviewed_by)}, {format_datetime(doc.reviewed_on, 'dd/MM/yyyy HH:mm')}" if doc.reviewed_by else "",
        "review_note": doc.review_note or "", "print_note": spec["print_note"],
        "rows": _sections(spec, json.loads(doc.data or "{}"), {f.file_url: f.name for f in files}),
    }
    return frappe.render_template(TEMPLATE, context)


def _pdf(doc) -> bytes:
    return get_pdf(render_html(doc), {"page-size": "A4", "margin-top": "15mm", "margin-bottom": "15mm",
                                      "margin-left": "15mm", "margin-right": "15mm"})


def freeze(doc) -> bytes:
    """The kept PDF of an approved form, made now if it does not exist yet."""
    if doc.pdf_file:
        name = frappe.db.get_value("File", {"file_url": doc.pdf_file, "attached_to_name": str(doc.name)}, "name")
        if name:
            content = frappe.get_doc("File", name).get_content()
            return content.encode() if isinstance(content, str) else content
    content = _pdf(doc)
    file = frappe.get_doc({"doctype": "File", "file_name": f"bieu-mau-{doc.name}.pdf", "content": content, "is_private": 1,
                           "attached_to_doctype": doc.doctype, "attached_to_name": str(doc.name)})
    file.insert(ignore_permissions=True)
    frappe.db.set_value(doc.doctype, doc.name, {"pdf_file": file.file_url, "pdf_hash": hashlib.sha256(content).hexdigest()},
                        update_modified=False)
    return content


def make_pdf_job(submission) -> None:
    """After an approval (queue default). If it fails, the first download makes the PDF instead."""
    if not frappe.db.exists("PM Form Submission", cint(submission)):
        return
    doc = frappe.get_doc("PM Form Submission", cint(submission))
    if doc.state == C.SUB_APPROVED:
        freeze(doc)
        frappe.db.commit()


def pdf_of(name) -> tuple[str, bytes]:
    """(file name, content) of a form the caller may read."""
    doc = frappe.get_doc("PM Form Submission", cint(name))
    doc.check_permission("read")
    content = freeze(doc) if doc.state == C.SUB_APPROVED else _pdf(doc)
    return f"bieu-mau-{doc.name}.pdf", content


# --- Excel --------------------------------------------------------------------------------------------------------------

def _put(sheet, row: int, column: int, value) -> None:
    cell = sheet.cell(row=row, column=column)
    if isinstance(value, (int, float)):
        cell.value = value
    else:
        cell.value = "" if value is None else str(value)
        cell.data_type = "s"  # never a formula, whatever the text starts with


def _sheet_title(book, text: str) -> str:
    title = "".join(c for c in text if c not in "[]:*?/\\")[:28] or "Bang"
    base, n = title, 1
    while title in book.sheetnames:
        n += 1
        title = f"{base} {n}"
    return title


def _header(sheet, labels: list) -> None:
    from openpyxl.styles import Font

    for column, label in enumerate(labels, start=1):
        _put(sheet, 1, column, label)
        sheet.cell(row=1, column=column).font = Font(bold=True)


def _flat(field: dict, value):
    kind = field["fieldtype"]
    if kind == C.F_CHECK:
        return _("Có") if value else _("Không")
    if kind in (C.F_IMAGE, C.F_SIGNATURE):
        return _("{0} tệp").format(len(value)) if value else ""
    return value


def export_xlsx(project: str, template_code: str, states=None) -> tuple[str, bytes]:
    """Every form of one kind in a project: one row per form; each table field gets its own sheet."""
    from openpyxl import Workbook

    frappe.get_doc("Project", project).check_permission("read")
    states = states or [C.SUB_SUBMITTED, C.SUB_APPROVED]
    rows = frappe.get_list("PM Form Submission", filters=[
        ["PM Form Submission", "project", "=", project], ["PM Form Submission", "template_code", "=", template_code],
        ["PM Form Submission", "state", "in", states]],
        fields=["name", "template", "version", "state", "task", "submitted_by", "submitted_on", "reviewed_by", "reviewed_on",
                "data"], order_by="name asc", limit_page_length=MAX_EXPORT_ROWS)
    fields, seen = [], set()
    versions = sorted({r.template for r in rows} or {form_templates.active_version(template_code)} - {None}, reverse=True)
    for version in versions:  # newest version's order first; fields only older versions had come after
        for field in form_templates.spec(version)["fields"]:
            if field["fieldtype"] != C.F_SECTION and field["fieldname"] not in seen:
                seen.add(field["fieldname"])
                fields.append(field)
    tasks = {t.name: t for t in frappe.get_all("Task", filters={"name": ["in", [r.task for r in rows if r.task]]},
                                               fields=["name", "subject", "pm_wbs_code"])} if rows else {}
    book = Workbook()
    sheet = book.active
    sheet.title = "Bieu mau"
    fixed = ["Số", "Công việc", "Trạng thái", "Phiên bản", "Người nộp", "Lúc nộp", "Người duyệt", "Lúc duyệt"]
    columns = [f for f in fields if f["fieldtype"] != C.F_TABLE]
    _header(sheet, fixed + [f["label"] for f in columns])
    tables = {}
    for field in (f for f in fields if f["fieldtype"] == C.F_TABLE):
        extra = book.create_sheet(_sheet_title(book, field["label"]))
        _header(extra, ["Số"] + [c["label"] for c in field["columns"]])
        tables[field["fieldname"]] = (extra, field, 2)
    name_of = frappe.utils.get_fullname
    for index, row in enumerate(rows, start=2):
        task = tasks.get(row.task)
        data = json.loads(row.data or "{}")
        values = [cint(row.name), f"{task.pm_wbs_code or ''} {task.subject}".strip() if task else "", row.state, row.version,
                  name_of(row.submitted_by) if row.submitted_by else "", row.submitted_on, name_of(row.reviewed_by) if row.reviewed_by else "",
                  row.reviewed_on]
        values += [_flat(f, data.get(f["fieldname"])) for f in columns]
        for column, value in enumerate(values, start=1):
            _put(sheet, index, column, value)
        for key, (extra, field, _next) in list(tables.items()):
            line = tables[key][2]
            for item in data.get(key) or []:
                _put(extra, line, 1, cint(row.name))
                for column, spec_column in enumerate(field["columns"], start=2):
                    _put(extra, line, column, item.get(spec_column["key"]))
                line += 1
            tables[key] = (extra, field, line)
    out = io.BytesIO()
    book.save(out)
    return f"bieu-mau-{template_code}.xlsx", out.getvalue()
