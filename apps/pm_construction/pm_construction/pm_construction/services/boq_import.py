"""Reading a bill of quantities (BOQ, bảng khối lượng dự toán) from an Excel sheet.

Estimating software exports different layouts, so the header row is looked for in the first rows, by the usual
column names (without accents or case): STT | Mã hiệu (định mức) | Nội dung công việc | Đơn vị | Khối lượng |
Đơn giá | Thành tiền | Ghi chú. Only "Nội dung công việc" and "Khối lượng" are required.

* A row with a description but no quantity and no unit is a section (hạng mục). Sections nest by the style of their
  number: the first style met (A, B... or I, II... or 1, 2...) is the top level, the next style the level below.
* A row with a quantity (or a unit) is a work item (công tác), under the last section above it.
* Total rows ("Tổng cộng", "Cộng"...) and empty rows are skipped.
* Numbers may be Excel numbers or text in Vietnamese (1.234,5) or international (1,234.5) form.
* A line whose amount differs from quantity × unit price is reported (a warning: the quantity and price are kept).
"""

import io
import re

import frappe
from frappe import _
from frappe.utils import flt
from project_manager.project_manager.services.text import plain

MAX_ROWS = 20000
HEADER_SCAN = 25
COLUMNS = {
    "code": ("stt", "tt", "so tt", "so thu tu"),
    "norm_code": ("ma hieu", "ma hieu dinh muc", "ma dinh muc", "ma so", "ma dm", "ma hieu don gia", "ma cong viec"),
    "description": ("noi dung cong viec", "noi dung", "ten cong viec", "ten cong tac", "dien giai", "hang muc cong viec",
                    "cong viec", "ten cong viec / hang muc"),
    "uom": ("don vi", "dvt", "don vi tinh", "dv"),
    "qty": ("khoi luong", "kl", "so luong", "khoi luong thiet ke"),
    "unit_price": ("don gia", "don gia (dong)", "don gia tong hop"),
    "amount": ("thanh tien", "gia tri", "thanh tien (dong)", "gia tri du toan"),
    "note": ("ghi chu",),
}
HEADERS = ("STT", "Mã hiệu", "Nội dung công việc", "Đơn vị", "Khối lượng", "Đơn giá", "Thành tiền", "Ghi chú")
TOTAL_WORDS = ("tong cong", "tong", "cong", "cong hang muc", "tong gia tri")
ROMAN = re.compile(r"^(?=[ivxlc]+$)c{0,3}(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")


def read_rows(content: bytes) -> list[list]:
    """Rows of the sheet with the most filled rows (a workbook often has a cover sheet)."""
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        frappe.throw(_("Không đọc được tệp Excel (.xlsx)"))
    best = []
    for sheet in book.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            if len(rows) > MAX_ROWS + HEADER_SCAN:
                frappe.throw(_("Tệp có quá {0} dòng").format(MAX_ROWS))
            rows.append(list(row))
        if sum(1 for r in rows if any(c not in (None, "") for c in r)) > sum(1 for r in best if any(c not in (None, "") for c in r)):
            best = rows
    book.close()
    return best


def find_header(rows: list[list]) -> tuple[int, dict]:
    """(row index, {column key: column index}) of the header row."""
    for number, row in enumerate(rows[:HEADER_SCAN]):
        found = {}
        for index, cell in enumerate(row):
            name = plain(cell).rstrip(":").strip()
            if not name:
                continue
            for key, names in COLUMNS.items():
                if key not in found and (name in names or any(name.startswith(n + " ") for n in names if len(n) > 3)):
                    found[key] = index
                    break
        if "description" in found and "qty" in found:
            return number, found
    frappe.throw(_("Không tìm thấy dòng tiêu đề: cần có cột \"Nội dung công việc\" và \"Khối lượng\""),
                 title=_("Tệp BOQ không đúng mẫu"))


def number(value):
    """A number from an Excel cell: a number, or text such as "1.234,5", "1,234.5", "12,5" (None when empty)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(" ", "")
    if not text or text in ("-", "—"):
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")  # 1.234,5
        else:
            text = text.replace(",", "")  # 1,234.5
    elif "," in text:
        text = text.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", text) else text.replace(",", ".")
    elif "." in text and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")  # 1.234.567: Vietnamese thousands
    try:
        return float(text)
    except ValueError:
        return None


def code_style(code: str, last_letter: str = "") -> str:
    """How a section is numbered. A single I, V, X, C... is a letter when it follows the previous letter section
    (A, B, C), a Roman numeral otherwise (I under B)."""
    text = plain(code).rstrip(".").strip()
    if not text:
        return "none"
    if re.fullmatch(r"[a-z]", text):
        follows = bool(last_letter) and ord(text) == ord(last_letter) + 1
        return "roman" if ROMAN.fullmatch(text) and not follows else "letter"
    if ROMAN.fullmatch(text):
        return "roman"
    if re.fullmatch(r"\d+", text):
        return "number"
    if re.fullmatch(r"\d+(\.\d+)+", text):
        return f"number{text.count('.')}"
    if text.startswith("phan") or text.startswith("hang muc"):
        return "letter"
    return "other"


def _cell(row, found, key):
    index = found.get(key)
    return row[index] if index is not None and index < len(row) else None


def _text(value, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())[:limit]


def parse(content: bytes) -> dict:
    """The sheet as BOQ lines, with the problems found. Nothing is written."""
    rows = read_rows(content)
    header_at, found = find_header(rows)
    items, issues = [], []
    styles = []  # section number styles, outermost first
    open_sections = []  # (level, line_no) of the sections that contain what follows
    last_letter = ""
    for offset, row in enumerate(rows[header_at + 1:], start=header_at + 2):
        description = _text(_cell(row, found, "description"), 1000)
        code = _text(_cell(row, found, "code"), 40)
        uom = _text(_cell(row, found, "uom"), 40)
        qty = number(_cell(row, found, "qty"))
        price = number(_cell(row, found, "unit_price"))
        amount = number(_cell(row, found, "amount"))
        if not description:
            continue
        words = plain(description)
        if not uom and qty is None and (words in TOTAL_WORDS or words.startswith(("tong cong", "cong hang muc"))):
            continue
        line = len(items) + 1
        if qty is None and not uom:
            style = code_style(code, last_letter)
            if style == "letter" and len(plain(code).rstrip(".")) == 1:
                last_letter = plain(code).rstrip(".")
            if style not in styles:
                styles.append(style)
            level = min(styles.index(style) + 1, 4)
            while open_sections and open_sections[-1][0] >= level:
                open_sections.pop()
            items.append({"line_no": line, "row": offset, "code": code, "norm_code": "", "description": description,
                          "uom": "", "qty": 0.0, "unit_price": 0.0, "amount": 0.0, "is_group": 1, "level": level,
                          "parent_line": open_sections[-1][1] if open_sections else 0,
                          "note": _text(_cell(row, found, "note"), 500)})
            open_sections.append((level, line))
            continue
        qty = flt(qty)
        price = flt(price)
        computed = flt(qty * price, 2)
        if amount is None:
            amount = computed
        elif price and abs(computed - amount) > max(1.0, abs(amount) * 0.005):
            issues.append({"row": offset, "level": "warning",
                           "message": _("Dòng {0}: thành tiền {1} khác khối lượng × đơn giá ({2})").format(
                               offset, f"{amount:,.0f}", f"{computed:,.0f}")})
        if qty <= 0:
            issues.append({"row": offset, "level": "warning",
                           "message": _("Dòng {0}: khối lượng bằng 0, công tác \"{1}\" sẽ không tính vào tiến độ").format(
                               offset, description[:60])})
        if not uom:
            issues.append({"row": offset, "level": "warning", "message": _("Dòng {0}: thiếu đơn vị").format(offset)})
        level = (open_sections[-1][0] + 1) if open_sections else 1
        items.append({"line_no": line, "row": offset, "code": code, "norm_code": _text(_cell(row, found, "norm_code"), 60),
                      "description": description, "uom": uom, "qty": qty, "unit_price": price, "amount": flt(amount, 2),
                      "is_group": 0, "level": level, "parent_line": open_sections[-1][1] if open_sections else 0,
                      "note": _text(_cell(row, found, "note"), 500)})
        if len(items) > MAX_ROWS:
            frappe.throw(_("Tệp có quá {0} dòng").format(MAX_ROWS))
    works = [item for item in items if not item["is_group"]]
    if not works:
        frappe.throw(_("Không có công tác nào (dòng có khối lượng) trong tệp"), title=_("Tệp BOQ trống"))
    return {
        "items": items, "issues": issues, "columns": sorted(found), "sections": len(items) - len(works),
        "works": len(works), "total": flt(sum(item["amount"] for item in works), 2),
    }


SAMPLE = [
    ("A", "", "PHẦN MÓNG", "", None, None),
    ("1", "AB.11312", "Đào móng băng bằng thủ công, đất cấp II", "m3", 86.4, 285_000),
    ("2", "AF.11111", "Bê tông lót móng đá 4x6, vữa mác 100", "m3", 9.6, 1_350_000),
    ("3", "AF.61120", "Sản xuất, lắp dựng cốt thép móng, đường kính ≤ 18 mm", "tấn", 4.25, 23_800_000),
    ("4", "AF.81111", "Ván khuôn móng băng", "100m2", 1.32, 14_500_000),
    ("5", "AF.11223", "Bê tông móng đá 1x2, mác 250", "m3", 38.5, 1_950_000),
    ("B", "", "PHẦN THÂN", "", None, None),
    ("I", "", "Kết cấu", "", None, None),
    ("6", "AF.12233", "Bê tông cột đá 1x2, mác 250, tiết diện ≤ 0,1 m2", "m3", 12.8, 2_250_000),
    ("7", "AF.61432", "Sản xuất, lắp dựng cốt thép cột, đường kính ≤ 18 mm", "tấn", 2.6, 24_500_000),
    ("8", "AF.12313", "Bê tông dầm, sàn đá 1x2, mác 250", "m3", 46.2, 2_050_000),
    ("II", "", "Xây, trát", "", None, None),
    ("9", "AE.22114", "Xây tường gạch đặc 6,5x10,5x22, dày ≤ 33 cm, vữa mác 75", "m3", 58.0, 1_650_000),
    ("10", "AK.21224", "Trát tường trong, dày 1,5 cm, vữa mác 75", "m2", 820.0, 95_000),
    ("C", "", "PHẦN HOÀN THIỆN", "", None, None),
    ("11", "AK.51250", "Lát nền gạch ceramic 600x600", "m2", 310.0, 285_000),
    ("12", "AK.84114", "Sơn tường trong nhà, 1 nước lót, 2 nước phủ", "m2", 1240.0, 62_000),
]


def template_file(with_sample: bool = True) -> bytes:
    """A sheet with the expected columns, and a small sample BOQ to start from."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = "BOQ"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    total = 0.0
    for code, norm, description, uom, qty, price in (SAMPLE if with_sample else []):
        amount = round(qty * price) if qty is not None else None
        total += amount or 0
        sheet.append([code, norm, description, uom, qty, price, amount, ""])
        if qty is None:
            for cell in sheet[sheet.max_row]:
                cell.font = Font(bold=True)
    if with_sample:
        sheet.append(["", "", "TỔNG CỘNG", "", None, None, total, ""])
    for column, width in zip("ABCDEFGH", (6, 12, 60, 9, 12, 14, 16, 24)):
        sheet.column_dimensions[column].width = width
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
