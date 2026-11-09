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

## M2 — rollup trên dự án 2.000 việc (2026-11-04)

Đo bằng `scripts/perf/rollup_check.py` trên site dev: script tạo một dự án tạm 2.045 việc (5 giai đoạn × 8 nhóm × 50 việc), đo, rồi xóa. Docker Desktop trên Windows 11.

| Thao tác | Thời gian | Ghi chú |
|---|---|---|
| Chèn 2.045 việc (mẫu, Excel) kèm tính cộng dồn | 933–977 ms | Giữ trước tên Task một lần, chèn 500 dòng mỗi câu |
| Đối soát toàn dự án (từ việc lá lên) | 32–45 ms | Mỗi cấp một câu `GROUP BY` |
| **Báo tiến độ một việc lá → % dự án đổi** (đường thật: lưu → commit → Redis + job queue `pm` → worker) | **trung vị 963 ms, tối đa 3.266 ms** (5 lần) | Mục tiêu < 5 s. Phần lớn thời gian là chờ worker nhận job |
| Job tự thân: tính lại một nhánh (3 cấp + dự án) | 7,6 ms | Ghi 3 dòng |
| Job tự thân: 19 nhánh một lúc | 44,9 ms | Ghi 24 dòng |
| Cây WBS: một cấp | 3 ms | |
| Kanban (500 thẻ) | 6 ms | |
| Ai làm gì | 4 ms | |
| Tổng quan dự án | 15 ms | |
| Danh sách dự án | 6 ms | |

Các số trên đo với tài khoản Administrator (không có điều kiện phạm vi). Điều kiện phạm vi của người dùng thường đã được đo ở M1 trên 1 triệu việc.

## M4 — Gantt và đường găng trên dự án 2.000 việc (2026-11-06)

Dữ liệu: `scripts/perf/gantt_seed.py` tạo dự án tạm 2.000 việc và 2.394 phụ thuộc (mọi việc nối tiếp nhau, thêm nối chéo giữa các nhóm). Đo Gantt bằng `scripts/e2e/ui/gantt_perf.mjs` trên Edge thật, mỗi cỡ 3 lần. Docker Desktop trên Windows 11, tài khoản Administrator.

| Thao tác trên máy chủ | Thời gian |
|---|---|
| Tính đường găng và dự báo, không có gì đổi | 285 ms |
| Tính lần đầu, ghi kết quả mọi việc | 581 ms |
| Dữ liệu Gantt (API) | 147 ms, 68 KB sau nén |
| Xem trước dời một việc giữa dự án (đẩy theo 997 việc) | 134 ms |
| Áp dụng lần dời đó, kèm lịch sử 997 dòng | 1.545 ms |
| Chụp baseline | 1.918 ms |

| Gantt trên trình duyệt | Vẽ xong (từ lúc mở trang, 3 lần) | Cuộn: trung vị / p95 |
|---|---|---|
| Máy tính | 694 / 563 / 751 ms | 6,9 / 7,1 ms mỗi khung |
| Điện thoại 390 px, CPU giảm 4 lần | 1.638 / 983 / 753 ms | 25,4 / 37,1 ms mỗi khung |

Mục tiêu của kế hoạch là dưới 2 s: đạt ở cả hai cỡ. Trước khi tối ưu, cuộn trên điện thoại là 39,6 ms mỗi khung: đọc lại màu CSS mỗi khung hình và cập nhật từng dòng danh sách là hai phần tốn nhất.

Thuật toán thuần (`test_cpm`): 20.000 việc, khoảng 12.000 phụ thuộc, dưới 2 s, chạy trên máy chủ.

## M5 — Dòng thời gian 50.000 mục (2026-11-09)

Dữ liệu: `scripts/perf/timeline_check.py` tạo dự án tạm 200 việc và 50.000 mục trao đổi, lịch sử rải đều trên các việc. Mỗi phép đo chạy 5 lần, đo ở máy chủ (gồm điều kiện quyền và tên người, ảnh của từng mục). Docker Desktop trên Windows 11.

| Một trang 50 mục | Quản trị | Kỹ sư (xem mọi việc) | Tổ trưởng (chỉ việc được giao) |
|---|---|---|---|
| Một công việc | 37 ms | 53 ms | 39 ms |
| Cả dự án, trang đầu | 10 ms | 40 ms | 19 ms |
| Cả dự án, trang thứ hai | 9 ms | 44 ms | 26 ms |

Trung vị; lần chậm nhất 76 ms. Mục tiêu của kế hoạch là dưới 500 ms. Trang sau đi theo mã của mục cuối (keyset), nên trang thứ một trăm nhanh như trang đầu.

Ảnh gửi từ điện thoại được thu nhỏ còn tối đa 1.600 px trước khi vào hàng đợi (kịch bản `discussion_flow.mjs` kiểm trên ảnh 1.170 × 2.532). Bundle SPA: 537 KB, 166 KB sau nén (thêm `socket.io-client`).

