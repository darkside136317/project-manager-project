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

PROJECT_SCOPED = ("PMC BOQ", "PMC BOQ Item", "PMC Site Diary", "PMC Diary Quantity", "PMC Material Plan",
                  "PMC Machine Transfer", "PMC Machine Shift", "PMC Crew Attendance", "PMC Machine Booking")

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
    {"rule_name": "Vượt định mức vật tư", "rule_type": "Vượt định mức vật tư", "to_accountable": 1, "to_manager": 1,
     "to_role": "Chỉ huy trưởng",
     "description": "Vật tư đã dùng cho một công tác vượt quá định mức của khối lượng đã làm (quá 5%)."},
    {"rule_name": "Máy đến hạn bảo dưỡng", "rule_type": "Máy đến hạn bảo dưỡng", "days": 3, "to_accountable": 0,
     "to_manager": 1, "to_role": "Chỉ huy trưởng",
     "description": "Máy đang ở dự án có ngày bảo dưỡng tiếp theo trong N ngày tới (hoặc đã qua)."},
)


# --- materials, machines, labour (M8) ---------------------------------------------------------------------------------------
OVER_NORM = "Vượt định mức vật tư"
MACHINE_MAINTENANCE = "Máy đến hạn bảo dưỡng"
NORM_TOLERANCE = 0.05  # used above the norm of the work done by more than this: over the norm
ITEM_GROUP = "Vật tư xây dựng"
SITE_STORES = "Kho công trường"  # the group of the site stores (one per project)
# Kinds of stock entry of a site store (Stock Entry.pmc_kind) and the ERPNext purpose of each.
RECEIPT, ISSUE, RETURN, WASTE, TRANSFER = "Nhập kho", "Cấp phát", "Hoàn trả", "Hao hụt", "Điều chuyển"
PURPOSES = {RECEIPT: "Material Receipt", ISSUE: "Material Issue", RETURN: "Material Receipt", WASTE: "Material Issue",
            TRANSFER: "Material Transfer"}
OWNED, RENTED = "Sở hữu", "Thuê"
MACHINE_READY, MACHINE_BUSY = "Sẵn sàng", "Đang dùng"
SHEET_DRAFT, SHEET_SUBMITTED, SHEET_CONFIRMED = "Nháp", "Đã nộp", "Đã xác nhận"
UOMS = (("m3", 0), ("m2", 0), ("tấn", 0), ("lít", 0), ("viên", 1), ("bao", 1), ("ca", 0))

STOCK_FIELDS = {
    "Material Request Item": [{"fieldname": "pmc_task", "fieldtype": "Link", "options": "Task", "label": "Công tác",
                               "insert_after": "project"}],
    "Purchase Order Item": [{"fieldname": "pmc_task", "fieldtype": "Link", "options": "Task", "label": "Công tác",
                             "insert_after": "project"}],
    "Purchase Receipt Item": [{"fieldname": "pmc_task", "fieldtype": "Link", "options": "Task", "label": "Công tác",
                               "insert_after": "project"}],
    "Purchase Invoice Item": [{"fieldname": "pmc_task", "fieldtype": "Link", "options": "Task", "label": "Công tác",
                               "insert_after": "project"}],
    "Stock Entry": [{"fieldname": "pmc_kind", "fieldtype": "Select", "label": "Loại phiếu (công trường)",
                     "options": "\nNhập kho\nCấp phát\nHoàn trả\nHao hụt\nĐiều chuyển", "insert_after": "stock_entry_type",
                     "in_standard_filter": 1},
                    {"fieldname": "pmc_client_uuid", "fieldtype": "Data", "label": "Mã gửi từ máy", "read_only": 1,
                     "hidden": 1, "unique": 1, "no_copy": 1, "insert_after": "pmc_kind"}],
    "Stock Entry Detail": [{"fieldname": "pmc_task", "fieldtype": "Link", "options": "Task", "label": "Công tác",
                            "insert_after": "project"}],
    # cost of a work item (services/costs.py): permission level 1, so the Desk shows it only to who may see costs
    "Task": [
        {"fieldname": "pmc_cost_section", "fieldtype": "Section Break", "label": "Chi phí thực tế (thi công)",
         "insert_after": "pmc_boq_key", "collapsible": 1, "permlevel": 1},
        {"fieldname": "pmc_material_cost", "fieldtype": "Currency", "label": "Vật tư", "read_only": 1, "permlevel": 1,
         "insert_after": "pmc_cost_section", "no_copy": 1},
        {"fieldname": "pmc_machine_cost", "fieldtype": "Currency", "label": "Máy", "read_only": 1, "permlevel": 1,
         "insert_after": "pmc_material_cost", "no_copy": 1},
        {"fieldname": "pmc_labour_cost", "fieldtype": "Currency", "label": "Nhân công", "read_only": 1, "permlevel": 1,
         "insert_after": "pmc_machine_cost", "no_copy": 1},
        {"fieldname": "pmc_actual_cost", "fieldtype": "Currency", "label": "Tổng chi phí thực tế", "read_only": 1,
         "permlevel": 1, "insert_after": "pmc_labour_cost", "no_copy": 1},
    ],
}

# Catalogues of the layer on the generic master screens (core hook pm_masters).
MASTERS = [
    {"doctype": "PMC Material Norm", "slug": "dinh-muc-vat-tu", "label": "Định mức vật tư", "icon": "list-checks",
     "list_fields": ["norm_code", "description", "uom", "is_active"]},
    {"doctype": "PMC Machine", "slug": "may-thi-cong", "label": "Máy thi công", "icon": "truck",
     "list_fields": ["machine_code", "machine_name", "ownership", "status", "current_project"]},
    {"doctype": "PMC Worker", "slug": "cong-nhan", "label": "Công nhân", "icon": "hard-hat",
     "list_fields": ["full_name", "team", "trade", "daily_rate", "is_active"]},
]

