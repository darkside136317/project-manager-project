# M4 — Lịch trình và tiến độ trực quan

## 1. Mục tiêu

Theo kế hoạch (prompt 4.2):

- phụ thuộc FS/SS/FF/SF có độ trễ, phát hiện vòng tròn;
- đường găng tính ở server; xem trước khi dời lịch;
- Gantt tự vẽ bằng canvas (quyết định D11): kéo-thả, đường găng, so với baseline;
- lịch thi công; baseline nhiều phiên bản; đường cong S; dự báo ngày hoàn thành.

Tiêu chí hoàn thành: chụp baseline → dời một việc găng → Gantt hiện chênh lệch, ngày hoàn thành dự báo thay đổi.

## 2. DocType và trường mới

| DocType | Mục đích | Ghi chú |
|---|---|---|
| PM Task Dependency | Phụ thuộc giữa hai việc | `predecessor`, `successor`, `dep_type`, `lag_days`; unique `(predecessor, successor)` |
| PM Baseline | Đầu mục một lần chụp, tên `{dự án}-BL01` | `is_primary`, `start_date`, `end_date`, `task_count`, `total_weight`. Không sửa được; không xóa được bản chính |
| PM Baseline Task | Ngày và trọng số của từng việc lúc chụp | Chèn hàng loạt; unique `(baseline, task)` |
| PM Baseline Curve | Đường cong S kế hoạch, mỗi tuần một điểm | Chèn hàng loạt; unique `(baseline, point_date)` |

Trường mới:
- **Task:** `pm_is_critical`, `pm_total_float`, `pm_conflict_days`, `pm_forecast_end`, `pm_spi`.
- **Project:** `pm_holiday_list`, `pm_primary_baseline`, `pm_plan_end`, `pm_forecast_end`, `pm_spi`.
- **PM Node Type:** `is_milestone` (loại "Mốc" không tốn thời gian). **PM Snapshot:** `spi`, `forecast_end`.

## 3. File chính

| File | Nội dung |
|---|---|
| `services/cpm.py` | Thuật toán đường găng thuần, không dính cơ sở dữ liệu: sắp xếp tô-pô, lượt xuôi, lượt ngược |
| `services/workdays.py` | Lịch làm việc từ Holiday List: đổi ngày thành số thứ tự ngày làm việc và ngược lại |
| `services/schedule.py` | Mạng công việc, phụ thuộc, tính kế hoạch, dự báo, xem trước và áp dụng dời lịch, job nền, dữ liệu cho Gantt và lịch |
| `services/baseline.py` | Chụp, chọn bản chính, xóa, so sánh, đường cong S kế hoạch |
| `services/activity.py`, `services/queries.py` | `record_many`, `reserve_ids`: ghi hàng loạt (bảng autoincrement của Frappe lấy số từ sequence riêng) |
| `api/schedule.py` | Lớp API mỏng |
| `frontend/src/components/gantt/GanttChart.vue` | Gantt canvas: danh sách bên trái, vẽ đúng phần trên màn hình, kéo-thả |
| `frontend/src/lib/gantt.js` | Phần không vẽ của Gantt và lịch: ngày, dòng hiển thị, thước, mũi tên, vị trí kéo. Có test riêng |
| `frontend/src/components/gantt/MovePreview.vue`, `TaskLinks.vue` | Xem trước dời lịch; phụ thuộc trong bảng công việc |
| `frontend/src/pages/project/GanttTab.vue`, `CalendarTab.vue`, `BaselineTab.vue` | Ba tab mới của dự án |
| `scripts/e2e/ui/schedule_flow.mjs`, `gantt_perf.mjs`; `scripts/perf/gantt_seed.py` | Kịch bản trình duyệt; đo Gantt 2.000 việc |

## 4. Quyết định kỹ thuật

- **Thời gian tính bằng ngày làm việc,** theo Holiday List của dự án (mặc định của công ty). Ngoài khoảng danh sách vẫn giữ các ngày nghỉ hằng tuần.
- **Ngày kế hoạch là "không bắt đầu sớm hơn".** Kế hoạch tôn trọng phụ thuộc thì đường găng tính được ngay trên chính kế hoạch đó. Việc bắt đầu sớm hơn phụ thuộc cho phép được đánh dấu (`pm_conflict_days`), không tự đổi ngày; Gantt có nút "Sửa N xung đột", có xem trước.
- **Nhóm là hai điểm không tốn thời gian,** điểm đầu và điểm cuối, con nằm giữa. Nhờ vậy "giai đoạn 2 sau giai đoạn 1" không cần xử lý riêng. Nhóm chỉ được làm việc trước theo FS hoặc FF.
- **Mốc nằm ở cuối ngày của nó,** nên mốc cùng ngày việc trước kết thúc không bị coi là xung đột.
- **Dời lịch:**
  - chỉ đẩy các việc phía sau đủ để không vi phạm phụ thuộc, không tự kéo việc sớm lên;
  - việc đã xong không bao giờ dời;
  - ngày sớm hơn phụ thuộc cho phép được sửa về ngày sớm nhất, kèm thông báo;
  - kéo cả thanh giữ nguyên số ngày làm việc; kéo đầu thanh mới đổi thời lượng;
  - việc đã giao cho người thực hiện thì bắt buộc có lý do, người phụ trách nhận thông báo, mỗi việc bị dời có dòng "Đổi hạn" trong lịch sử.
- **Xem trước do server tính, sau khi thả chuột.** Kế hoạch dự kiến có bộ test dùng chung cho thuật toán ở server và client; do client không có thuật toán thứ hai nên không cần bộ này, và không thể có hai bản kết quả khác nhau.
- **Tính lại ngay với thao tác trên kế hoạch** (phụ thuộc, dời lịch, baseline), để màn hình đúng tức thì. Các thay đổi khác (báo tiến độ...) đánh dấu dự án và chạy job gộp trên queue `pm`; cron 5 phút gom phần sót; mỗi đêm tính lại toàn bộ vì "hôm nay" đã đổi.
- **Dự báo:**
  - việc đã xong giữ ngày thực tế; việc chưa bắt đầu không thể bắt đầu trước hôm nay và vẫn chờ việc trước;
  - việc đang làm chạy theo tốc độ đã thể hiện: `0,6 × tiến độ 14 ngày qua + 0,4 × tiến độ từ khi bắt đầu`, tính trên mỗi ngày làm việc;
  - phần còn lại của việc quá chậm bị chặn ở 5 lần thời lượng, để một việc đình trệ không đẩy dự báo đi nhiều năm (việc đình trệ sẽ là cảnh báo ở M7).
- **SPI** so với baseline chính nếu có, không thì so với kế hoạch hiện tại. Sức khỏe Xanh/Vàng/Đỏ để M7.
- **Đường cong S kế hoạch** tính sẵn khi chụp: mỗi việc rải trọng số đều trên các ngày làm việc của nó. Biểu đồ dùng trục thời gian thật; đường thực tế dừng ở hôm nay, đường kế hoạch chạy tới cuối dự án.
- **Gantt:** danh sách bên trái là HTML thật nên đọc và bấm được bằng bàn phím; canvas chỉ vẽ phần trên màn hình. Trên điện thoại chỉ để xem, ban đầu hiện 3 cấp. Phiên bản bằng chữ của cùng dữ liệu là tab Công việc và bảng Baseline.

## 5. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **208 + 17** (152 trước đó, 56 `test_schedule`, 17 `test_cpm` chạy riêng vì không cần cơ sở dữ liệu) |
| `test_cpm` | Các ví dụ tính tay: mọi kiểu phụ thuộc xuôi và ngược, độ trễ âm, việc đã xong, việc đang làm, mốc, vòng tròn 40 bước, 20.000 việc dưới 2 s; lịch làm việc |
| `test_schedule` | Đường găng trên ngày thật (Chủ nhật, ngày lễ), nhóm, từ chối phụ thuộc sai, dời lịch, dời cả giai đoạn, sửa xung đột, dự báo, job nền, phạm vi quyền, baseline, kịch bản hoàn thành |
| vitest (9 tệp) | **144/144** (thêm `gantt.test.js`: 39) |
| ruff (CI), `compileall`, `scripts/ci/check_repo.py` | Không lỗi |
| `scripts/e2e/ui/schedule_flow.mjs` | **28/28** trên Edge thật: kéo thanh, xem trước, hủy, nối phụ thuộc bằng kéo chuột, bấm mở việc; cỡ điện thoại chỉ xem, không cuộn ngang |
| Hiệu năng | Xem [HIEU_NANG.md](../HIEU_NANG.md#m4--gantt-và-đường-găng-trên-dự-án-2000-việc-2026-11-06) |

Lỗi kiểm thử giao diện tự động không bắt được, tìm ra khi xem ảnh chụp của kịch bản, đã sửa:
- kéo cả thanh qua Chủ nhật làm việc 3 ngày co còn 2 ngày;
- chú giải của đường cong S gần như mất màu: lớp CSS `.grid` của biểu đồ trùng tên với `grid` của Tailwind ở khung ngoài.

Lỗi tìm được khi chạy test: chèn hàng loạt vào bảng autoincrement báo `Field 'name' doesn't have a default value`, vì Frappe lấy số từ sequence riêng chứ bảng không tự tăng. Đã sửa bằng `reserve_ids`.

**Clone sạch** (xuất bằng `git checkout-index` sang thư mục mới, cổng 8891, stack `pmclone` chạy song song với stack dev):
- `bootstrap.ps1` thoát với mã 0; smoke 0 lỗi, cả trước và sau khi có dữ liệu mẫu;
- `setup.demo.up` tạo được dự án mẫu kèm baseline;
- kịch bản trình duyệt: `forms_flow.mjs` 19/19, `schedule_flow.mjs` 28/28;
- test: `project_manager` 208 + 17, `pm_construction` 2/2;
- bootstrap lần hai thoát với mã 0, smoke vẫn 0 lỗi, dữ liệu mẫu còn nguyên;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 6. Điểm cần chú ý khi duyệt

- **Chưa có cột phụ thuộc khi nhập WBS từ Excel:** phụ thuộc thêm trên Gantt hoặc trong bảng công việc. Nhập từ MS Project để M10 như kế hoạch.
- **Kéo-thả chỉ thử bằng chuột trên máy tính.** Trên điện thoại Gantt chỉ để xem, đúng kế hoạch; cỡ điện thoại mới chạy giả lập trên Edge, chưa thử trên máy thật.
- **Xóa việc:** việc đứng sau trong một phụ thuộc đã có dòng lịch sử, việc nằm trong baseline cũng vậy, nên chỉ hủy được chứ không xóa được. Việc đứng trước chưa có lịch sử thì xóa được; phụ thuộc của nó bị gỡ theo và lịch được tính lại trong nền.
- **Sửa ngày qua `tree.update` không đẩy các việc sau,** chỉ đánh dấu xung đột. Màn hình đã dùng xem trước và áp dụng (Gantt, bảng công việc); đường này chỉ còn cho ai gọi API trực tiếp.
- **Dữ liệu mẫu** có sẵn phụ thuộc, baseline "Kế hoạch được duyệt" và việc 3.1.2 bị dời sau baseline, làm ngày hoàn thành dự báo chậm hơn baseline (lúc viết: 9 ngày). Dựng lại bằng `setup.demo.down` rồi `setup.demo.up`.
- **Kịch bản trình duyệt chưa chạy trong CI,** chạy thủ công khi kiểm từng phase.

## 7. Việc tiếp theo

**M5 — Trao đổi theo đầu việc, tài liệu, offline nền:** dòng thời gian có bình luận và @mention, ảnh qua MinIO, tài liệu có phiên bản, PWA với hàng đợi gửi lại.
