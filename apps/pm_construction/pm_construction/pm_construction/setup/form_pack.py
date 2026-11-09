"""Acceptance records of construction (biên bản nghiệm thu), installed as forms of the core (M3) through the
`pm_form_packs` hook. The work acceptance carries the accepted quantity (services/acceptance.py reads it)."""

from pm_construction.pm_construction import constants as K

_PARTIES = {"label": "Thành phần trực tiếp nghiệm thu", "fieldtype": "Bảng", "reqd": 1,
            "options": "Họ và tên\nChức vụ\nĐơn vị", "preset_rows": "\n\n"}
_RESULT = "Kết quả | Chọn: Đạt, Không đạt, Không áp dụng"


def acceptance_forms() -> list[dict]:
    return [
        {
            "code": "NT-CONGVIEC", "title": "Biên bản nghiệm thu công việc xây dựng", "category": "Nghiệm thu",
            "description": "Nghiệm thu một công tác đã thi công xong, ghi khối lượng được nghiệm thu.",
            "rows": [
                {"label": "Ngày nghiệm thu", "fieldtype": "Ngày", "reqd": 1},
                _PARTIES,
                {"label": "Căn cứ nghiệm thu", "fieldtype": "Văn bản dài",
                 "description": "Bản vẽ thi công, chỉ dẫn kỹ thuật, kết quả thí nghiệm..."},
                {"label": "Khối lượng nghiệm thu", "fieldname": K.QTY_FIELD, "fieldtype": "Số", "reqd": 1,
                 "min_value": "0"},
                {"label": "Chất lượng công việc", "fieldtype": "Bảng", "reqd": 1, "options": f"Nội dung\n{_RESULT}",
                 "preset_rows": "Đúng kích thước, cao độ theo bản vẽ\nVật liệu đúng chủng loại, có chứng chỉ\n"
                                "Kết quả thí nghiệm đạt yêu cầu\nBề mặt, mối nối đạt yêu cầu"},
                {"label": "Kết luận", "fieldtype": "Chọn", "reqd": 1,
                 "options": "Chấp nhận nghiệm thu\nChấp nhận, sửa các tồn tại\nKhông chấp nhận"},
                {"label": "Tồn tại cần sửa", "fieldtype": "Văn bản dài"},
                {"label": "Ảnh hiện trường", "fieldtype": "Ảnh"},
                {"label": "Đại diện nhà thầu ký", "fieldtype": "Chữ ký", "reqd": 1},
                {"label": "Đại diện tư vấn giám sát ký", "fieldtype": "Chữ ký", "reqd": 1},
            ],
        },
        {
            "code": "NT-GIAIDOAN", "title": "Biên bản nghiệm thu giai đoạn, bộ phận công trình", "category": "Nghiệm thu",
            "description": "Nghiệm thu khi xong một giai đoạn (phần móng, phần thân...) trước khi làm tiếp.",
            "rows": [
                {"label": "Ngày nghiệm thu", "fieldtype": "Ngày", "reqd": 1},
                _PARTIES,
                {"label": "Giai đoạn, bộ phận được nghiệm thu", "fieldtype": "Văn bản", "reqd": 1},
                {"label": "Hồ sơ nghiệm thu công việc kèm theo", "fieldtype": "Văn bản dài"},
                {"label": "Kết luận", "fieldtype": "Chọn", "reqd": 1,
                 "options": "Đồng ý cho chuyển giai đoạn\nĐồng ý, sửa các tồn tại\nKhông đồng ý"},
                {"label": "Tồn tại cần sửa", "fieldtype": "Văn bản dài"},
                {"label": "Đại diện chủ đầu tư ký", "fieldtype": "Chữ ký", "reqd": 1},
                {"label": "Đại diện nhà thầu ký", "fieldtype": "Chữ ký", "reqd": 1},
            ],
        },
        {
            "code": "NT-ATLD", "title": "Phiếu kiểm tra an toàn lao động", "category": "An toàn",
            "description": "Kiểm tra an toàn trước khi thi công hoặc định kỳ trên công trường.",
            "rows": [
                {"label": "Ngày kiểm tra", "fieldtype": "Ngày", "reqd": 1},
                {"label": "Khu vực kiểm tra", "fieldtype": "Văn bản", "reqd": 1},
                {"label": "Nội dung kiểm tra", "fieldtype": "Bảng", "reqd": 1, "options": f"Nội dung\n{_RESULT}\nGhi chú",
                 "preset_rows": "Công nhân đủ đồ bảo hộ (mũ, giày, dây an toàn)\nGiàn giáo, lan can, lưới chắn\n"
                                "Điện thi công, tủ điện, tiếp địa\nMáy móc có kiểm định\nBiển báo, rào chắn, lối đi"},
                {"label": "Kết luận", "fieldtype": "Chọn", "reqd": 1, "options": "Đạt\nĐạt, cần khắc phục\nDừng thi công"},
                {"label": "Việc cần khắc phục", "fieldtype": "Văn bản dài"},
                {"label": "Ảnh", "fieldtype": "Ảnh"},
                {"label": "Cán bộ an toàn ký", "fieldtype": "Chữ ký", "reqd": 1},
            ],
        },
        {
            "code": "NT-BANGIAO", "title": "Biên bản bàn giao mặt bằng thi công", "category": "Bàn giao",
            "description": "Chủ đầu tư bàn giao mặt bằng, mốc giới, điểm đấu nối cho nhà thầu.",
            "rows": [
                {"label": "Ngày bàn giao", "fieldtype": "Ngày", "reqd": 1},
                _PARTIES,
                {"label": "Phạm vi mặt bằng", "fieldtype": "Văn bản dài", "reqd": 1},
                {"label": "Mốc giới, cao độ chuẩn", "fieldtype": "Bảng", "options": "Mốc\nTọa độ, cao độ\nGhi chú"},
                {"label": "Điểm đấu nối điện, nước", "fieldtype": "Văn bản dài"},
                {"label": "Hiện trạng", "fieldtype": "Văn bản dài"},
                {"label": "Ảnh hiện trạng", "fieldtype": "Ảnh"},
                {"label": "Bên giao ký", "fieldtype": "Chữ ký", "reqd": 1},
                {"label": "Bên nhận ký", "fieldtype": "Chữ ký", "reqd": 1},
            ],
        },
    ]
