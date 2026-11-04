"""The ready-made forms of the core: general, for any industry. A layer adds its own through the `pm_form_packs` hook
(the construction layer's acceptance forms come with M6). Installed once per code; an administrator may then change or
retire them like any other form (setup/install.ensure_form_packs)."""

_RESULT = "Kết quả | Chọn: Đạt, Không đạt, Không áp dụng"

GENERAL_FORMS = [
    {
        "code": "CL-CHUNG", "title": "Phiếu kiểm tra hoàn thành công việc", "category": "Kiểm tra",
        "description": "Danh mục kiểm tra trước khi coi một công việc là xong.",
        "rows": [
            {"label": "Ngày kiểm tra", "fieldtype": "Ngày", "reqd": 1},
            {"label": "Danh mục kiểm tra", "fieldtype": "Bảng", "reqd": 1,
             "options": f"Nội dung\n{_RESULT}\nGhi chú",
             "preset_rows": "Làm đúng phạm vi đã giao\nĐúng yêu cầu kỹ thuật, bản vẽ, tiêu chuẩn\n"
                            "Đủ tài liệu, hồ sơ đi kèm\nĐã xử lý các tồn tại lần trước\nHiện trường gọn gàng, an toàn"},
            {"label": "Kết luận", "fieldtype": "Chọn", "reqd": 1, "options": "Đạt\nĐạt, còn tồn tại nhỏ\nKhông đạt"},
            {"label": "Tồn tại cần xử lý", "fieldtype": "Văn bản dài"},
            {"label": "Ảnh hiện trường", "fieldtype": "Ảnh"},
            {"label": "Người kiểm tra ký", "fieldtype": "Chữ ký", "reqd": 1},
        ],
    },
    {
        "code": "BB-BANGIAO", "title": "Biên bản bàn giao công việc", "category": "Bàn giao",
        "description": "Bàn giao kết quả công việc giữa hai bên hoặc giữa hai đội.",
        "rows": [
            {"label": "Ngày bàn giao", "fieldtype": "Ngày", "reqd": 1},
            {"label": "Bên giao", "fieldtype": "Văn bản", "reqd": 1},
            {"label": "Bên nhận", "fieldtype": "Văn bản", "reqd": 1},
            {"label": "Nội dung bàn giao", "fieldtype": "Bảng", "reqd": 1,
             "options": "Hạng mục\nKhối lượng | Số\nĐơn vị\nTình trạng"},
            {"label": "Ghi chú", "fieldtype": "Văn bản dài"},
            {"label": "Bên giao ký", "fieldtype": "Chữ ký", "reqd": 1},
            {"label": "Bên nhận ký", "fieldtype": "Chữ ký", "reqd": 1},
        ],
    },
    {
        "code": "BC-SUCO", "title": "Báo cáo sự cố", "category": "An toàn",
        "description": "Ghi nhận sự cố hoặc vướng mắc ngay khi xảy ra.",
        "rows": [
            {"label": "Thời điểm xảy ra", "fieldtype": "Ngày", "reqd": 1},
            {"label": "Mức độ", "fieldtype": "Chọn", "reqd": 1, "options": "Nhẹ\nTrung bình\nNghiêm trọng"},
            {"label": "Mô tả sự cố", "fieldtype": "Văn bản dài", "reqd": 1},
            {"label": "Ảnh", "fieldtype": "Ảnh"},
            {"label": "Có người bị ảnh hưởng", "fieldtype": "Hộp kiểm"},
            {"label": "Hướng xử lý", "fieldtype": "Văn bản dài"},
        ],
    },
]
