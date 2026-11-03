# Spike M1: chọn cách làm Gantt (quyết định D11)

**Mục tiêu:** chọn cách vẽ Gantt cho M4. Gantt phải hiển thị 2.000–5.000 công việc có phụ thuộc FS/SS/FF/SF, kéo-thả trên máy tính, chỉ xem trên điện thoại. Đường găng (CPM) luôn tính ở server, không phụ thuộc thư viện (D10).

**Mã spike:** `spikes/gantt/` (không thuộc app, không vào image).
- `npm ci && npm run build && npm run preview` để chạy trang thử.
- `cd tools && npm ci && node measure.mjs http://localhost:4173 2000,5000` để đo.

## Cách đo

- Cùng một kế hoạch cho mọi phương án: giai đoạn → hạng mục → 10 công tác. Liên kết FS giữa các công tác liên tiếp, thêm vài liên kết SS/FF.
  - Bộ 2.000 task có 1.982 công việc; bộ 5.000 task có 4.955 công việc và 4.140 liên kết.
- Đo bằng Edge headless qua Playwright, với hai cấu hình:
  - **máy tính** 1366×768;
  - **điện thoại** 390×844, CPU chậm 4 lần (giả lập máy Android tầm trung).
- **Vẽ lần đầu:** từ lúc gắn component tới khi trình duyệt vẽ xong hai khung hình.
- **Cuộn:** thời gian trung bình mỗi khung khi cuộn xuống 120 bước. 16,7 ms tương ứng 60 khung/giây; trên 33 ms là thấy giật.

## Kết quả (2026-11-03)

| Cấu hình | Phương án | Công việc | Vẽ lần đầu | Cuộn TB / p95 (ms/khung) | Nút DOM |
|---|---|---|---|---|---|
| máy tính | Tự vẽ canvas | 4.955 | **35 ms** | **6,9 / 7,0** | 34 |
| máy tính | SVAR Vue Gantt 2.8.1 (MIT) | 4.955 | 153 ms | 8,5 / 11,6 | 376 |
| máy tính | DHTMLX Gantt 10.0.3 Standard (MIT) | 4.955 | 197 ms | 6,9 / 7,1 | 1.114 |
| máy tính | frappe-gantt 1.2.2 (MIT) | 4.955 | **4.036 ms** | 17,3 / 7,2 | 59.565 |
| điện thoại | Tự vẽ canvas | 4.955 | **108 ms** | **7,8 / 10,9** | 36 |
| điện thoại | SVAR | 4.955 | 602 ms | **56,7 / 86,2** (giật) | 272 |
| điện thoại | DHTMLX Standard | 4.955 | 791 ms | 13,8 / 20,7 | 505 |
| điện thoại | frappe-gantt | 4.955 | **24.750 ms** | 8,0 / 15,6 | 59.565 |

Bộ 2.000 task cho cùng thứ tự xếp hạng; chi tiết xem lại bằng `measure.mjs`.

**Dung lượng tải** (riêng phần Gantt, chưa nén, chưa tính CSS):

| Phương án | JS | CSS |
|---|---|---|
| Canvas | ~3 KB | 0,6 KB |
| frappe-gantt | 49 KB | 7 KB |
| SVAR | 270 KB | 158 KB |
| DHTMLX | 628 KB | 143 KB |

## Những tính năng M4 cần mà bản miễn phí không có

Đã kiểm trong mã thư viện và README:

| Tính năng M4 cần | SVAR (MIT) | DHTMLX Standard (MIT) | Tự vẽ canvas |
|---|---|---|---|
| Hiển thị cả 4 loại liên kết, cây WBS, kéo-thả | Có | Có | Phải viết (kéo-thả, nối liên kết) |
| Chỉ vẽ phần đang hiển thị (cho phép 5.000+ task) | Có | Có | Có |
| Tô màu task trên đường găng (dữ liệu từ server) | Qua class/template | Qua `templates.task_class` | Có |
| **Vẽ baseline** cạnh thanh thực tế | Chỉ bản PRO | **Không**: bản Standard xóa `addTaskLayer` | Có |
| Lịch ngày làm việc (bỏ ngày nghỉ, lễ) | Chỉ bản PRO | Chỉ bản PRO ("Pro feature… not available in this edition") | Có (dùng Holiday List) |
| Đường cong S, mã WBS, xuất PDF/MS Project | Chỉ bản PRO | Chỉ bản PRO | Tự làm (đường cong S và xuất đã có trong kế hoạch M4/M10) |
| Giấy phép | MIT; PRO trả phí theo lập trình viên | MIT; PRO trả phí theo lập trình viên | Của mình |

**frappe-gantt bị loại:** nó tạo nút DOM cho mọi task, nên mất 4 giây trên máy tính và 25 giây trên điện thoại với 5.000 task. Nó cũng không có cây WBS và chỉ vẽ được liên kết FS.

## Ba lựa chọn để bạn quyết định

1. **Tự vẽ trên canvas (đề xuất).**
   - Ưu điểm:
     - nhanh nhất ở mọi cấu hình, kể cả điện thoại chậm;
     - nhẹ nhất;
     - không phụ thuộc giấy phép;
     - baseline, đường găng, ngày nghỉ và mã WBS vẽ được ngay từ dữ liệu server đã có kế hoạch (D10, D14).
   - Chi phí: phải tự viết tương tác (kéo, kéo giãn, nối liên kết, phóng to/thu nhỏ, sửa trong lưới). M4 dài thêm khoảng 2–3 tuần (từ L lên khoảng L+).
2. **DHTMLX Standard (MIT) cho tương tác, thêm phần tự vẽ.**
   - Ưu điểm: mượt trên điện thoại; có sẵn kéo-thả và cây.
   - Hạn chế:
     - baseline và ngày nghỉ không vẽ được trong bản miễn phí, phải hiển thị kiểu khác (ví dụ bảng so sánh bên cạnh);
     - bundle khoảng 770 KB, chỉ tải khi mở trang Gantt.
3. **Mua bản PRO** (DHTMLX PRO hoặc SVAR PRO).
   - Ưu điểm: đủ tính năng ngay.
   - Hạn chế:
     - tốn phí bản quyền theo số lập trình viên;
     - SVAR vẫn giật trên điện thoại;
     - phải kiểm tra điều khoản phân phối nếu bán phần mềm cho nhiều khách hàng.

**Đề xuất:** phương án 1. Lý do:
- Phần đắt nhất của một Gantt "xịn" (đường găng, lịch làm việc, baseline) theo kế hoạch đã nằm ở server.
- Thư viện miễn phí chỉ tiết kiệm được phần tương tác, nhưng lại chặn đúng các tính năng cần hiển thị.
- Bản canvas trong spike đã đạt khoảng 7–8 ms/khung trên điện thoại chậm.

## Quyết định

2026-11-03: người dùng chọn **phương án 1 — tự vẽ trên canvas**. M4 tăng từ L lên L+ (thêm khoảng 2–3 tuần cho tương tác). Mã khởi đầu: `spikes/gantt/src/CanvasView.vue`.
