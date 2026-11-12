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

## M6 — BOQ 3.000 dòng (2026-11-09)

`scripts/perf/boq_check.py` tạo dự án tạm, BOQ 100 hạng mục × 29 công tác, rồi bản 2 đổi khối lượng 1/10 số dòng. Đo ở máy chủ, Docker Desktop trên Windows 11.

| Thao tác | Thời gian |
|---|---|
| Đọc tệp Excel (94 KB) | 243–339 ms |
| Nhập một phiên bản (3.000 dòng, chèn hàng loạt) | 1.234 ms |
| Duyệt bản đầu: sinh cây WBS 3.000 việc, cộng dồn lại | 3.421 ms (trước khi tối ưu: 8.593 ms) |
| Duyệt bản sau: nhận ra 3.000 dòng, cập nhật 300 việc | 704 ms (trước khi tối ưu: 10.590 ms) |

Trước khi tối ưu, mỗi dòng ghi riêng 2–3 lệnh, và lần duyệt sau nạp lại mọi công tác để tính tiến độ dù không đổi. Nay ghi theo lô (một lệnh UPDATE cho vài trăm dòng), và chỉ tính lại tiến độ của công tác đổi khối lượng thiết kế.

## M7 — Cảnh báo, sức khỏe, danh mục trên 50 dự án (2026-11-11)

`scripts/perf/alerts_check.py` tạo 50 dự án tạm, mỗi dự án 4 giai đoạn, 200 công việc rải trong hai tháng quanh hôm nay (tổng 10.200 việc). Một phần ba số việc đáng lẽ đã bắt đầu thì đang trễ và chậm, một số không cập nhật đã một tuần. Một người quản lý tất cả. Đo ở máy chủ, Docker Desktop trên Windows 11. Script tự dọn dữ liệu khi xong.

| Thao tác | Thời gian |
|---|---|
| Dự báo và sức khỏe một dự án 200 việc: lần đầu / không đổi | 173 ms / 28 ms |
| Dự báo và sức khỏe 49 dự án còn lại | 2.454 ms |
| Kiểm tra chuyển giai đoạn, 50 dự án | 310 ms |
| Quy tắc hằng ngày, lần đầu: mở 4.400 cảnh báo, báo người nhận | 1.837 ms (trước khi tối ưu: 42.889 ms) |
| Quy tắc hằng ngày, các lần sau (không có gì mới) | 226 ms (trước: 6.727 ms) |
| Leo thang 3.600 cảnh báo mở 3 ngày | 314 ms (trước: 15.091 ms) |
| Danh mục dự án, 50 dự án (quản trị / người quản lý) | 236 ms / 224 ms |
| Cảnh báo của tôi | 12 ms |
| Tóm tắt hằng ngày / tuần | 64 ms / 153 ms |

Trước khi tối ưu, mỗi kết quả của quy tắc tra cảnh báo bằng một lệnh riêng. Người nhận của từng việc cũng được đọc riêng, và mỗi người nhận được ghi bằng một lệnh. Nay một lượt chạy làm theo lô:
- đọc cảnh báo đang mở của quy tắc bằng một lệnh;
- chèn cảnh báo mới cùng lúc;
- đọc người phụ trách của mọi việc liên quan trong vài lệnh;
- nhớ tạm người quản lý, vai trò, tùy chọn của từng người trong lượt chạy;
- ghi người nhận và bậc leo thang bằng một lệnh UPDATE cho 500 cảnh báo.

Một người có hơn 3 cảnh báo mới trong cùng một lượt nhận một thông báo gộp ("12 cảnh báo mới: Quá hạn 8, Sắp đến hạn 4") thay vì 12 thông báo lẻ.

Lịch chạy chỉ xếp lượt chạy vào hàng đợi `long` (giới hạn 1 giờ), vì nhiều dự án có thể làm lượt chạy dài hơn thời gian cho phép của một job theo lịch.

## M8 — Vật tư trên BOQ 3.000 công tác (2026-11-11)

`scripts/perf/materials_check.py` tạo dự án tạm với BOQ 100 hạng mục × 30 công tác. Mỗi mã hiệu có một định mức 3 vật tư, nên có 9.000 dòng kế hoạch vật tư. Script nhập kho, cấp phát cho 1.000 công tác (3.000 dòng, 31 phiếu), rồi đo các màn hình. Đo ở máy chủ, Docker Desktop trên Windows 11; script tự dọn dữ liệu.

| Thao tác | Thời gian |
|---|---|
| Duyệt BOQ 3.000 công tác, gồm cả lập 9.000 dòng kế hoạch vật tư | 5,7–9,6 s |
| Tính lại kế hoạch vật tư (9.000 dòng, chèn hàng loạt) | 2,4–3,9 s |
| Một phiếu cấp phát 99 dòng | 3,9–4,0 s |
| Tổng quan vật tư: định mức so với thực tế, 9.000 dòng | 0,55–0,88 s |
| Tính lại chi phí cả dự án | 61–70 ms |
| Bảng chi phí | 115–124 ms |
| Quét cảnh báo vượt định mức (mọi dự án) | 0,51–0,62 s |

Số đầu là lần chạy thứ nhất, số sau là lần thứ hai, khi máy đang bận hơn.

Một phiếu cấp phát 99 dòng tốn gần hết thời gian ở ERPNext: lập và submit Stock Entry, ghi sổ kho, tính giá, ghi bút toán. Phần của hệ thống (kiểm từng dòng, tính lại chi phí) khoảng 0,3 s (đo bằng cProfile). Phiếu thực tế thường vài dòng, nên mất dưới 1 giây.

Bảng định mức so với thực tế trả về mọi dòng của dự án. Với 9.000 dòng, trang tải chậm trên điện thoại. Cần lọc theo hạng mục hoặc chỉ hiện công tác đang làm (để sau).

## M9 — Khối lượng công việc, hiệu suất, danh mục v2 trên 50 dự án (2026-11-11)

`scripts/perf/people_check.py` tạo 50 dự án tạm × 204 việc (10.200 việc) trong ba tháng quanh hôm nay, 120 người, 25.012 lượt giao (mỗi việc một người chịu trách nhiệm chính, một hoặc hai người thực hiện; mỗi dự án 12 người lấy từ nhóm chung, nên mỗi người làm ở nhiều dự án). Một nửa số việc đã qua là xong (một phần ba trong đó trễ), còn lại đang làm. 10 người nghỉ phép hai ngày tuần này. Một quản lý tạm quản lý cả 50 dự án. Đo ở máy chủ, Docker Desktop trên Windows 11; script tự dọn dữ liệu.

| Thao tác | Thời gian |
|---|---|
| Danh mục dự án v2, 50 dự án (quản trị / quản lý cả 50 dự án) | 0,58–0,62 s / 0,54–0,56 s |
| Khối lượng công việc 6 tuần, mọi người (123 người, 712 xung đột) | 0,45–0,49 s |
| Khối lượng công việc 12 tuần, mọi người | 0,32–0,42 s |
| Khối lượng công việc 6 tuần, quản lý cả 50 dự án | 0,44–0,49 s |
| Khối lượng công việc 6 tuần, một người tự xem | 28–33 ms |
| Một ô (người × tuần) | 14–16 ms |
| Cảnh báo quá tải: đánh giá tuần này và tuần sau, mọi người | 0,43–0,49 s |
| Hiệu suất 4 tuần / 13 tuần (quản trị) | 0,22–0,30 s / 0,20–0,21 s |
| Hiệu suất 4 tuần (quản lý cả 50 dự án) | 0,17–0,19 s |
| Hiệu suất một người | 11–14 ms |
| Ảnh chụp tuần trước (650 dòng; lần hai cập nhật các dòng đó) | 2,8–2,9 s; 1,3–1,4 s |

Hai số là hai lần chạy. Ngưỡng "dashboard 50 dự án < 2 s" của kế hoạch đạt với dư nhiều. Trên trình duyệt, `people_flow.mjs` kiểm trên dữ liệu mẫu rằng trang khối lượng công việc mở dưới 3 giây và danh mục dự án dưới 2 giây.

Dữ liệu đo dày hơn thực tế (mỗi người khoảng 200 lượt giao trong ba tháng), nên gần như ai cũng quá tải và có 712 xung đột. Trang khối lượng công việc chỉ hiện 10 xung đột đầu, bấm "Xem tất cả" để xem hết.

Khối lượng công việc được tính trong bộ nhớ từ một truy vấn các lượt giao còn hiệu lực: mỗi việc chia cho mọi người đang giữ nó (kể cả người mà người xem không thấy), rồi chỉ giữ dòng của những người người xem được thấy. Ảnh chụp tuần chạy mỗi sáng thứ Hai lúc 01:30.

## M10 — Báo cáo, EVM, MS Project, hồ sơ dự án (2026-11-12)

`scripts/perf/control_check.py` tạo 50 dự án tạm × 204 việc, mỗi dự án có ngân sách đã duyệt 8 dòng, 6 rủi ro, 4 vấn đề, 3 phát sinh; một phần ba việc đã trễ. Thêm một dự án 2.004 việc với 1.500 phụ thuộc để đo MS Project. Đo ở máy chủ, Docker Desktop trên Windows 11, trên site dev (có cả dữ liệu mẫu); script tự dọn dữ liệu.

| Thao tác | Thời gian |
|---|---|
| Báo cáo "Tiến độ các dự án" (55 dự án) | 0,34–0,37 s |
| Báo cáo "Ngân sách và giá trị thu được" (55 dự án, EVM từng dự án) | 0,38–0,49 s |
| Báo cáo "Công việc trễ", trang đầu (1.927 việc trễ) | 30 ms |
| Sổ rủi ro, vấn đề, phát sinh (mọi dự án), trang đầu | 4–7 ms |
| Báo cáo của lớp thi công, một dự án | 22–26 ms |
| EVM 55 dự án ra Excel / PDF | 0,13–0,16 s / 0,59–0,61 s |
| Xuất MS Project XML, 2.004 việc (1,2 MB) | 0,24–0,33 s |
| Đọc lại tệp đó (xem trước) | 0,17–0,21 s |
| Nhập tệp đó vào dự án khác (2.004 việc, 1.500 phụ thuộc) | 1,6 s |
| Lập hồ sơ dự án 2.004 việc (không có tài liệu, biểu mẫu) | 0,09–0,13 s |

Lần đo đầu, nhập MS Project mất **42 s**: mỗi phụ thuộc được kiểm vòng tròn trên cả mạng việc (1.500 lần × 2.000 việc), rồi chèn từng dòng. Nay các quy tắc của từng phụ thuộc được kiểm riêng, vòng tròn được kiểm một lần cho tất cả (chỉ khi tệp có vòng tròn mới thử từng cái để bỏ cái gây vòng), và các phụ thuộc được chèn hàng loạt.

Gói hồ sơ chạy ở hàng đợi `long`. Thời gian chủ yếu nằm ở việc tải các tệp tài liệu từ MinIO và lập PDF của biểu mẫu đã duyệt chưa có bản lưu; giới hạn 1 GB tệp mỗi gói.

