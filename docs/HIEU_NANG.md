# Hiệu năng

Đo bằng `scripts/perf/volume_check.py` trên một site riêng (`perfpm.localhost`, tên phải bắt đầu bằng `perf`); site được xóa sau khi đo. Cách chạy nằm ở đầu file script.

## M1 — 1 triệu công việc (2026-11-03)

**Dữ liệu sinh:**
- 500 dự án: 50 đang chạy, mỗi dự án 6.000 công việc; 450 đã đóng, mỗi dự án khoảng 1.556.
- Tổng **999.750 công việc**, cây 4 cấp. Số nút theo cấp:

| Cấp | Số nút |
|---|---|
| Giai đoạn | 2.500 |
| Hạng mục | 77.250 |
| Công tác | 766.000 |
| Việc con | 154.000 |

- Ngày bắt đầu, kết thúc và `modified` rải đều trong 3 năm.
- Thời gian sinh: khoảng 6 phút (SQL theo lô 2.000 dòng).

**Kết quả** (lấy lần nhanh nhất trong 3 lần; mọi thay đổi được rollback; Docker Desktop trên Windows 11):

| Thao tác | Thời gian | Ghi chú |
|---|---|---|
| Thêm công việc vào một hạng mục của dự án **cũ nhất** | **8,9 ms** (lần đầu 189 ms do cache trống) | Mục tiêu < 300 ms |
| Thêm công việc gốc vào dự án cũ nhất | 16,1 ms | Khóa dòng Project để không trùng thứ tự |
| Chuyển một hạng mục (kèm công việc con) sang giai đoạn khác | 7,9 ms | Một câu UPDATE giới hạn trong dự án |
| Cập nhật **mọi dòng** Task một lần (`rgt + 0`) | **1.239–1.440 ms** | Đây là việc nested set của Frappe làm khi thêm công việc vào dự án cũ, và nó khóa dòng của mọi dự án. Kết quả này là lý do cho quyết định D4 |
| Kỹ sư (3 dự án): danh sách công việc trang 1, mới nhất trước | 39,9 ms | Có lọc phạm vi dự án |
| Kỹ sư: WBS một dự án theo thứ tự cây (2.000 dòng đầu) | 12,1 ms | Index `(project, pm_path)` |
| Giám đốc (mọi dự án): danh sách công việc trang 1, mới nhất trước | 319 ms | Không có điều kiện dự án |
| Giám đốc: danh sách dự án trang 1 | 5,9 ms | |
| Kỹ sư: đếm công việc của mình | 168,8 ms | Khoảng 18.000 dòng của 3 dự án |

**Nhận xét:**
- Thêm, sửa, di chuyển công việc không phụ thuộc kích thước bảng: chỉ chạm vào dữ liệu của một dự án.
- Danh sách "mọi dự án" mới nhất trước (319 ms) và phép đếm (169 ms) đạt ngưỡng < 1 s, nhưng là hai chỗ cần theo dõi khi làm màn hình danh sách ở M2. Hướng xử lý: phân trang keyset, `capped_count`, index `(project, modified)` nếu cần.
