"""Names and choices of the construction layer."""

ESTIMATE_METHOD = "Theo giá trị dự toán"  # roll-up: a work item weighs its estimate value (hooks.pm_rollup_methods)
NODE_SECTION, NODE_WORK = "Hạng mục", "Công tác"
NODE_TYPES = (
    {"node_type": NODE_SECTION, "is_group": 1, "counts_in_rollup": 1, "sort_order": 15},
    {"node_type": NODE_WORK, "is_group": 0, "counts_in_rollup": 1, "sort_order": 35},
)

BOQ_DRAFT, BOQ_APPROVED, BOQ_REPLACED = "Nháp", "Đã duyệt", "Thay thế"
DIARY_DRAFT, DIARY_SUBMITTED, DIARY_CONFIRMED = "Nháp", "Đã nộp", "Đã xác nhận"
DIARY_COUNTED = (DIARY_SUBMITTED, DIARY_CONFIRMED)  # quantities of these diaries count as done
WEATHER = ("Nắng", "Âm u", "Mưa nhỏ", "Mưa to", "Gió lớn")

# Acceptance records are forms (M3) of the pack setup/form_pack.py; the work acceptance carries a quantity.
ACCEPTANCE_CODES = ("NT-CONGVIEC", "NT-GIAIDOAN", "NT-ATLD", "NT-BANGIAO")
QTY_ACCEPTANCE_CODE = "NT-CONGVIEC"
QTY_FIELD = "khoi_luong_nghiem_thu"

PROJECT_SCOPED = ("PMC BOQ", "PMC BOQ Item", "PMC Site Diary", "PMC Diary Quantity")

TASK_FIELDS = [
    {"fieldname": "pmc_section", "fieldtype": "Section Break", "label": "Khối lượng (thi công)", "insert_after": "pm_spi",
     "collapsible": 1},
    {"fieldname": "pmc_uom", "fieldtype": "Data", "label": "Đơn vị", "insert_after": "pmc_section"},
    {"fieldname": "pmc_planned_qty", "fieldtype": "Float", "label": "Khối lượng thiết kế", "insert_after": "pmc_uom"},
    {"fieldname": "pmc_unit_price", "fieldtype": "Currency", "label": "Đơn giá", "insert_after": "pmc_planned_qty"},
    {"fieldname": "pmc_estimate_value", "fieldtype": "Currency", "label": "Giá trị dự toán", "read_only": 1,
     "insert_after": "pmc_unit_price", "no_copy": 1},
    {"fieldname": "pmc_column", "fieldtype": "Column Break", "insert_after": "pmc_estimate_value"},
    {"fieldname": "pmc_done_qty", "fieldtype": "Float", "label": "Khối lượng đã làm", "read_only": 1,
     "insert_after": "pmc_column", "no_copy": 1},
    {"fieldname": "pmc_accepted_qty", "fieldtype": "Float", "label": "Khối lượng đã nghiệm thu", "read_only": 1,
     "insert_after": "pmc_done_qty", "no_copy": 1},
    {"fieldname": "pmc_norm_code", "fieldtype": "Data", "label": "Mã hiệu định mức", "insert_after": "pmc_accepted_qty"},
    {"fieldname": "pmc_boq_item", "fieldtype": "Int", "label": "Dòng BOQ", "read_only": 1, "insert_after": "pmc_norm_code",
     "no_copy": 1},
    {"fieldname": "pmc_boq_key", "fieldtype": "Data", "label": "Khóa BOQ", "read_only": 1, "hidden": 1,
     "insert_after": "pmc_boq_item", "no_copy": 1},
]

# Alerts (core hooks pm_alert_types / pm_alert_rules): yesterday's site diary is missing on a project under way.
MISSING_DIARY = "Thiếu nhật ký thi công"
ALERT_RULES = (
    {"rule_name": MISSING_DIARY, "rule_type": MISSING_DIARY, "to_accountable": 0, "to_manager": 1,
     "to_role": "Chỉ huy trưởng",
     "description": "Ngày làm việc gần nhất chưa có nhật ký thi công đã nộp, ở dự án có bảng khối lượng đã duyệt."},
)

