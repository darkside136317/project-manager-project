"""Mẫu biểu mẫu: users design their own forms, each change of a form in use being a new version.

* A template is one row per version: code + version (TN-AT-v01, v02...). Only a draft (Nháp) can be edited.
* Putting a version in use (Đang dùng) retires the previous one of the same code: new forms use the new version, forms
  already filled in keep the version they were filled in with, so a change can never damage them.
* `fieldname` is kept from version to version even when the label changes, so answers across versions line up (Excel).
* Who designs: `forms.manage`. Everybody may read templates in use, in order to fill them in.

Options are plain text so that they can be typed and read: "Chọn" has one choice per line, "Bảng" one column per line
("Nhãn", "Nhãn | Số", "Kết quả | Chọn: Đạt, Không đạt"). `spec()` gives the parsed form the screens and services use.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import assert_capability, has_capability
from project_manager.project_manager.services.text import plain, slug

CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,29}$")
TEMPLATE_FIELDS = ("title", "category", "description", "print_note")
ROW_FIELDS = ("label", "fieldname", "fieldtype", "reqd", "description", "options", "preset_rows", "unit", "min_value",
              "max_value")
MAX_FIELDS = 200
MAX_COLUMNS = 12
MAX_PRESET_ROWS = 200
COLUMN_TYPES = {plain(t): t for t in C.TABLE_COLUMN_TYPES}
DATA_LESS = (C.F_SECTION,)


# --- parsing options ---------------------------------------------------------------------------------------------------

def parse_choices(text) -> list[str]:
    seen, out = set(), []
    for line in str(text or "").splitlines():
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def parse_columns(text) -> list[dict]:
    """Columns of a table field. Raises ValueError with the problem to show."""
    columns, keys = [], set()
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        label, _sep, kind = line.partition("|")
        label, kind = label.strip(), kind.strip()
        choices = []
        if ":" in kind:
            kind, _sep, options = kind.partition(":")
            choices = [c.strip() for c in options.split(",") if c.strip()]
        column_type = COLUMN_TYPES.get(plain(kind)) if kind else C.F_TEXT
        if not label or not column_type:
            raise ValueError(_("Cột \"{0}\": kiểu phải là một trong {1}").format(line, ", ".join(C.TABLE_COLUMN_TYPES)))
        if column_type == C.F_SELECT and not choices:
            raise ValueError(_("Cột \"{0}\": hãy ghi các lựa chọn, ví dụ Kết quả | Chọn: Đạt, Không đạt").format(label))
        key = base = slug(label, "cot")
        n = 1
        while key in keys:
            n += 1
            key = f"{base}_{n}"
        keys.add(key)
        columns.append({"key": key, "label": label, "type": column_type, "choices": choices})
    return columns


def _field_spec(row) -> dict:
    spec = {"fieldname": row.fieldname, "label": row.label, "fieldtype": row.fieldtype, "reqd": cint(row.reqd),
            "description": row.description or "", "choices": [], "columns": [], "preset_rows": [],
            "unit": row.unit or "", "min_value": row.min_value, "max_value": row.max_value}
    if row.fieldtype == C.F_SELECT:
        spec["choices"] = parse_choices(row.options)
    elif row.fieldtype == C.F_TABLE:
        spec["columns"] = parse_columns(row.options)
        spec["preset_rows"] = parse_choices(row.preset_rows)
    return spec


def bound(value) -> float | None:
    """A number's limit as the designer typed it: empty means none, 0 is a limit."""
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _memo() -> dict:
    memo = getattr(frappe.local, "pm_form_specs", None)
    if memo is None:
        memo = frappe.local.pm_form_specs = {}
    return memo


def spec(template: str) -> dict:
    """The parsed definition of one version, memoised for the request."""
    memo = _memo()
    if template not in memo:
        doc = frappe.get_doc("PM Form Template", template)
        memo[template] = frappe._dict(
            name=doc.name, code=doc.code, title=doc.title, version=cint(doc.version), status=doc.status,
            category=doc.category or "", description=doc.description or "", print_note=doc.print_note or "",
            fields=[_field_spec(row) for row in doc.form_fields])
    return memo[template]


def forget(template: str) -> None:
    _memo().pop(template, None)


# --- checking what a designer typed ---------------------------------------------------------------------------------

def _clean_rows(rows) -> list[dict]:
    if len(rows or []) > MAX_FIELDS:
        frappe.throw(_("Một biểu mẫu có tối đa {0} trường").format(MAX_FIELDS))
    used = {str(r.get("fieldname")) for r in rows or [] if r.get("fieldname")}
    out = []
    for position, raw in enumerate(rows or [], start=1):
        row = {k: raw.get(k) for k in ROW_FIELDS}
        row["label"] = (row["label"] or "").strip()
        if not row["label"]:
            frappe.throw(_("Trường thứ {0}: thiếu nhãn").format(position))
        kind = row["fieldtype"] or C.F_TEXT
        if kind not in C.FORM_FIELD_TYPES:
            frappe.throw(_("{0}: kiểu \"{1}\" không hợp lệ").format(row["label"], kind))
        row["fieldtype"] = kind
        row["reqd"] = 0 if kind in DATA_LESS else cint(row["reqd"])
        if not row["fieldname"]:
            key = base = slug(row["label"])
            n = 1
            while key in used:
                n += 1
                key = f"{base}_{n}"
            row["fieldname"] = key
            used.add(key)
        if kind == C.F_SELECT and not parse_choices(row["options"]):
            frappe.throw(_("{0}: hãy ghi các lựa chọn, mỗi dòng một lựa chọn").format(row["label"]))
        if kind == C.F_TABLE:
            try:
                columns = parse_columns(row["options"])
            except ValueError as error:
                frappe.throw(f"{row['label']}: {error}")
            if not columns or len(columns) > MAX_COLUMNS:
                frappe.throw(_("{0}: bảng cần từ 1 đến {1} cột, mỗi dòng một cột").format(row["label"], MAX_COLUMNS))
            if len(parse_choices(row["preset_rows"])) > MAX_PRESET_ROWS:
                frappe.throw(_("{0}: tối đa {1} hàng có sẵn").format(row["label"], MAX_PRESET_ROWS))
        if kind == C.F_NUMBER:
            for limit in ("min_value", "max_value"):
                if row[limit] not in (None, "") and bound(row[limit]) is None:
                    frappe.throw(_("{0}: giới hạn \"{1}\" không phải là số").format(row["label"], row[limit]))
            low, high = bound(row["min_value"]), bound(row["max_value"])
            if low is not None and high is not None and low > high:
                frappe.throw(_("{0}: giá trị nhỏ nhất lớn hơn giá trị lớn nhất").format(row["label"]))
        out.append(row)
    keys = [r["fieldname"] for r in out]
    if len(keys) != len(set(keys)):
        frappe.throw(_("Có hai trường trùng mã"))
    return out


# --- reading ----------------------------------------------------------------------------------------------------------

def overview() -> dict:
    """Every code with its versions, for the designers."""
    assert_capability("forms.manage")
    rows = frappe.get_all("PM Form Template", fields=["name", "code", "title", "version", "status", "category", "modified",
                                                      "is_builtin"], order_by="code asc, version desc",
                          limit_page_length=0)
    counts = dict(frappe.db.sql("select template, count(*) from `tabPM Form Submission` group by template"))
    grouped = {}
    for row in rows:
        row["submissions"] = cint(counts.get(row.name))
        entry = grouped.setdefault(row.code, {"code": row.code, "title": row.title, "category": row.category,
                                              "active": None, "draft": None, "versions": []})
        entry["versions"].append(row)
        if row.status == C.FORM_ACTIVE:
            entry["active"] = row.name
            entry["title"] = row.title
        elif row.status == C.FORM_DRAFT:
            entry["draft"] = row.name
    return {"rows": list(grouped.values())}


def in_use() -> list[dict]:
    """The forms that can be filled in now (what a person picks from)."""
    return frappe.get_all("PM Form Template", filters={"status": C.FORM_ACTIVE},
                          fields=["name", "code", "title", "version", "category", "description"], order_by="category asc, title asc",
                          limit_page_length=0)


def active_version(code: str) -> str | None:
    return frappe.db.get_value("PM Form Template", {"code": code, "status": C.FORM_ACTIVE}, "name")


def get(name: str) -> dict:
    """One version with its raw rows (for the designer) and its parsed definition (for the preview)."""
    doc = frappe.get_doc("PM Form Template", name)
    doc.check_permission("read")
    if doc.status == C.FORM_DRAFT and not has_capability("forms.manage"):
        frappe.throw(_("Mẫu này chưa đưa vào dùng"), frappe.PermissionError)
    forget(name)
    return {
        "name": doc.name, "code": doc.code, "title": doc.title, "version": cint(doc.version), "status": doc.status,
        "category": doc.category, "description": doc.description, "print_note": doc.print_note,
        "is_builtin": cint(doc.is_builtin),
        "rows": [{k: row.get(k) for k in ROW_FIELDS} for row in doc.form_fields],
        "spec": spec(name),
        "can_edit": doc.status == C.FORM_DRAFT and has_capability("forms.manage"),
        "can_manage": has_capability("forms.manage"),
        "field_types": list(C.FORM_FIELD_TYPES),
        "submissions": frappe.db.count("PM Form Submission", {"template": name}),
    }


# --- changing ----------------------------------------------------------------------------------------------------------

def _apply(doc, values: dict, rows) -> None:
    for field in TEMPLATE_FIELDS:
        if field in values:
            doc.set(field, (values[field] or "").strip() if isinstance(values[field], str) else values[field])
    if not (doc.title or "").strip():
        frappe.throw(_("Hãy nhập tên biểu mẫu"))
    if rows is not None:
        doc.set("form_fields", [])
        for row in _clean_rows(rows):
            doc.append("form_fields", row)


def create(code: str, values: dict, rows=None) -> dict:
    assert_capability("forms.manage")
    code = (code or "").strip().upper()
    if not CODE.match(code):
        frappe.throw(_("Mã mẫu chỉ gồm chữ không dấu, số, gạch nối, tối đa 30 ký tự (ví dụ NT-CV)"))
    if frappe.db.exists("PM Form Template", {"code": code}):
        frappe.throw(_("Đã có mẫu mã {0}: hãy tạo phiên bản mới của mẫu đó").format(code))
    doc = frappe.get_doc({"doctype": "PM Form Template", "code": code, "version": 1, "status": C.FORM_DRAFT})
    _apply(doc, values, rows or [])
    doc.insert(ignore_permissions=True)
    return get(doc.name)


def save(name: str, values: dict, rows=None) -> dict:
    assert_capability("forms.manage")
    doc = frappe.get_doc("PM Form Template", name)
    _apply(doc, values, rows)
    doc.save(ignore_permissions=True)  # the controller refuses anything but a draft
    forget(name)
    return get(name)


def activate(name: str) -> dict:
    """Put a draft in use. The version in use until now stops being offered."""
    assert_capability("forms.manage")
    doc = frappe.get_doc("PM Form Template", name)
    if doc.status != C.FORM_DRAFT:
        frappe.throw(_("Chỉ đưa vào dùng được bản nháp"))
    _clean_rows([{k: row.get(k) for k in ROW_FIELDS} for row in doc.form_fields])
    if not [row for row in doc.form_fields if row.fieldtype not in DATA_LESS]:
        frappe.throw(_("Biểu mẫu chưa có trường nào để điền"))
    frappe.db.sql("select name from `tabPM Form Template` where code = %s for update", doc.code)
    for previous in frappe.get_all("PM Form Template", filters={"code": doc.code, "status": C.FORM_ACTIVE}, pluck="name"):
        frappe.db.set_value("PM Form Template", previous, "status", C.FORM_RETIRED)
    frappe.db.set_value("PM Form Template", name, "status", C.FORM_ACTIVE)
    forget(name)
    return get(name)


def retire(name: str) -> dict:
    assert_capability("forms.manage")
    if frappe.db.get_value("PM Form Template", name, "status") != C.FORM_ACTIVE:
        frappe.throw(_("Mẫu này không đang được dùng"))
    code = frappe.db.get_value("PM Form Template", name, "code")
    required = frappe.db.count("PM Gate Requirement", {"form_code": code})
    if required:
        frappe.throw(_("{0} công việc đang bắt buộc mẫu này để đóng việc: hãy bỏ điều kiện đó hoặc đưa một phiên bản khác "
                       "vào dùng").format(required))
    frappe.db.set_value("PM Form Template", name, "status", C.FORM_RETIRED)
    forget(name)
    return get(name)


def new_version(name: str) -> dict:
    """A draft copy of `name`, numbered after the newest version of its code (the draft itself if there is one)."""
    assert_capability("forms.manage")
    source = frappe.get_doc("PM Form Template", name)
    frappe.db.sql("select name from `tabPM Form Template` where code = %s for update", source.code)
    draft = frappe.db.get_value("PM Form Template", {"code": source.code, "status": C.FORM_DRAFT}, "name")
    if draft:
        return get(draft)
    latest = frappe.db.sql("select max(version) from `tabPM Form Template` where code = %s", source.code)[0][0]
    doc = frappe.get_doc({"doctype": "PM Form Template", "code": source.code, "version": cint(latest) + 1,
                          "status": C.FORM_DRAFT, "title": source.title, "category": source.category,
                          "description": source.description, "print_note": source.print_note})
    for row in source.form_fields:
        doc.append("form_fields", {k: row.get(k) for k in ROW_FIELDS})
    doc.insert(ignore_permissions=True)
    return get(doc.name)


def remove_draft(name: str) -> dict:
    assert_capability("forms.manage")
    frappe.delete_doc("PM Form Template", name, ignore_permissions=True)  # the controller keeps everything but drafts
    forget(name)
    return {"name": name, "deleted": True}


# --- packs of ready-made forms ----------------------------------------------------------------------------------------

def install_pack(pack: list[dict]) -> int:
    """Create (and put in use) the forms of a pack whose code does not exist yet. Existing ones are left alone: an
    administrator may have changed or retired them."""
    created = 0
    for item in pack:
        if frappe.db.exists("PM Form Template", {"code": item["code"]}):
            continue
        doc = frappe.get_doc({"doctype": "PM Form Template", "code": item["code"], "version": 1, "status": C.FORM_ACTIVE,
                              "is_builtin": 1, **{k: item.get(k) for k in TEMPLATE_FIELDS}})
        for row in _clean_rows(item["rows"]):
            doc.append("form_fields", row)
        doc.insert(ignore_permissions=True)
        created += 1
    return created
