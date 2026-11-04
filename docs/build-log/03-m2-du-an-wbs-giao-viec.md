# M2 — Dự án, WBS, giao việc rõ trách nhiệm, rollup

## 1. Mục tiêu

Theo kế hoạch (prompt 4.1, 4.3 phần rollup, 4.10 phần nhập Excel):

- tạo dự án trống hoặc từ dự án mẫu (chép cây công việc, dời ngày);
- cây WBS: thêm, sửa, di chuyển, đổi thứ tự, hủy, xóa; nhập từ Excel có chạy thử;
- giao việc theo RACI: đúng một người chịu trách nhiệm chính, nhận hoặc từ chối kèm lý do, thu hồi, lịch sử không xóa;
- cập nhật tiến độ trên việc lá; việc trễ bắt buộc ghi lý do chậm và khâu gây chậm; duyệt việc đã xong;
- tiến độ, ngày và trạng thái của nhóm và dự án tự cộng dồn (rollup tăng dần, đối soát hằng đêm), ảnh chụp hằng ngày cho đường cong S;
- màn hình: Dự án, Tổng quan dự án, Công việc (cây), Kanban, Ai làm gì, Thành viên, Việc của tôi, chi tiết công việc;
- nhắc việc sắp đến hạn và quá hạn lúc 7 giờ sáng.

## 2. DocType và trường mới

| DocType | Mục đích | Ghi chú |
|---|---|---|
| PM Team (+PM Team Member) | Đội, tổ, phòng, nhà thầu phụ: nhận việc như một khối | Trưởng nhóm tự thành thành viên; không xóa được khi đã nhận việc; index `(user, parenttype)` trên thành viên |
| PM Task Assignment | Ai giữ vai trò gì trên việc nào | `raci`, `user` hoặc `team`, `state` (Chờ nhận / Đã nhận / Từ chối / Thu hồi / Hoàn thành), `is_active`, người giao, lý do từ chối, lý do kết thúc. Không xóa được; chỉ `services/assignments.py` ghi |
| PM Progress Entry | Mỗi lần báo tiến độ | trước/sau, công, ghi chú, lý do và khâu chậm, `client_uuid` (unique, cho hàng đợi gửi lại) |
| PM Snapshot | Tiến độ hằng ngày của dự án và các giai đoạn cấp 1 | thực tế, kế hoạch tuyến tính, số việc, số việc trễ |
| PM Delay Reason, PM Delay Source | Danh mục lý do chậm (9) và khâu gây chậm (6) | Seed sẵn; mục có sẵn hoặc đang dùng không xóa được |

Custom field mới:
- **Project:** `pm_rollup_method` (Theo thời lượng / Theo trọng số / Bằng nhau), `pm_is_template`.
- **Task:** `pm_accountable`, `pm_reviewer` (bản sao của phân công còn hiệu lực, để lọc nhanh), `pm_is_overdue`, `pm_delay_days`, `pm_delay_reason`, `pm_delay_source`, `pm_delay_note`, `pm_rollup_weight`, `pm_last_progress_on`. Index `(pm_accountable, status)`, `(project, status)`.
- **PM Settings:** cách tính tiến độ mặc định, bật nhắc việc, số ngày coi là "sắp đến hạn".

## 3. File chính

| File | Nội dung |
|---|---|
| `services/assignments.py` | `assign`, `respond`, `revoke`, `complete_for`, `of_task` |
| `services/progress.py` | `report` (việc lá, lý do chậm, idempotent theo `client_uuid`), `review`, `move` (Kanban), `history`, `record_activity` (doc_event ghi lịch sử đổi hạn, tiến độ, trạng thái, vị trí) |
| `services/rollup.py` | Đánh dấu và xử lý tăng dần, `reconcile`, `sweep`, cờ trễ hạn, ảnh chụp hằng ngày, `planned_progress` |
| `services/tree.py` | Cây WBS: đọc từng cấp, thêm, sửa, di chuyển, `renumber`, hủy, xóa, `bulk_insert` + `reserve_names` |
| `services/projects.py` | Danh sách, tổng quan, tạo (từ mẫu), sửa, thành viên |
| `services/wbs_import.py` | Đọc Excel, chạy thử, nhập; tệp mẫu |
| `services/work.py` | Việc của tôi, Kanban, Ai làm gì, chi tiết công việc |
| `services/reminders.py` | Nhắc việc 7 giờ sáng, mỗi người một thông báo mỗi ngày |
| `api/projects.py`, `api/wbs.py`, `api/tasks.py` | Lớp API mỏng; mọi luật nằm trong `services/` |
| `overrides/task.py` | `update_project` → đánh dấu rollup; `validate` tính trọng số việc lá và cờ trễ |
| `setup/demo.py` | Dữ liệu mẫu (`up` / `down`): dự án mẫu, một dự án đang chạy, 5 người, phân công, tiến độ, 40 ngày lịch sử |
| `frontend/src/pages/ProjectsPage.vue`, `ProjectPage.vue` + `pages/project/*` | Dự án và các tab Tổng quan, Công việc, Kanban, Ai làm gì, Thành viên; hộp thoại nhập Excel |
| `frontend/src/pages/MyTasksPage.vue`, `TaskPage.vue`; `components/TaskDetail.vue`, `TaskDrawer.vue`, `SCurve.vue`, `ProgressBar.vue`; `lib/work.js` | Việc của tôi, chi tiết công việc, đường cong S |
| `scripts/perf/rollup_check.py` | Đo rollup trên dự án 2 000 việc tạm (tự dọn) |

## 4. Quyết định kỹ thuật

- **Rollup tăng dần qua queue `pm`.**
  - Lưu một Task chỉ đánh dấu việc cha vào tập Redis `pm_rollup:<dự án>` và đưa job `pm-rollup:<dự án>` vào hàng đợi sau commit; job được gộp (`deduplicate`), nên nhiều lần lưu liên tiếp chỉ chạy một job.
  - Job tính từ dưới lên, mỗi cấp một câu `GROUP BY parent_task`; chỉ ghi dòng có giá trị đổi, bằng `UPDATE` thẳng (không lưu document, không chạy hook). Ngày của nhóm = ngày sớm nhất / muộn nhất của con; trạng thái nhóm suy ra từ con.
  - Job lỗi thì trả các mục cần tính lại vào tập Redis; cron 5 phút (`sweep`) chạy lại. Đối soát hằng đêm (`reconcile_all`, queue long) tính lại toàn bộ và ghi log nếu phải sửa giá trị nào (bình thường là 0).
- **Trọng số:** việc lá tính theo cách tính của dự án (số ngày, `task_weight`, hoặc 1); loại nút không tính (Mốc) và việc đã hủy có trọng số 0. Trọng số nhóm = tổng của con, nên % dự án không phụ thuộc độ sâu của cây.
- **Trễ hạn là cờ, không phải trạng thái.** `pm_is_overdue` / `pm_delay_days` được tính khi lưu và mỗi ngày bằng hai câu `UPDATE` trên cả bảng. Trạng thái ERPNext không bao giờ thành "Overdue" (job của ERPNext đã dừng từ M1).
- **Một người chịu trách nhiệm chính:** giao vai trò này cho người mới thì người cũ bị thu hồi với lý do "Chuyển giao cho …". Hai người giao cùng lúc được xếp hàng nhờ khóa dòng Task (`SELECT … FOR UPDATE`).
- **Ai được giao việc:** người đọc được dự án (thành viên, hoặc được cấp phạm vi). Người chỉ thấy việc được giao (tổ trưởng, khách) thấy việc ngay khi được giao.
  - Lỗi phát hiện bằng test: bản đầu kiểm "người đó thấy được công việc", nên không bao giờ giao được cho tổ trưởng. Đã sửa.
- **Đổi ngày cần lý do** khi việc đã có người nhận; lần đổi được ghi vào lịch sử ("Đổi hạn") kèm người đổi và lý do. Ngày của nhóm có con thì không sửa tay được.
- **Xóa và hủy:** việc đã có lịch sử (phân công, báo cáo, trao đổi) chỉ hủy được; việc bị hủy có trọng số 0 và các phân công còn hiệu lực bị thu hồi.
- **Chèn hàng loạt** (mẫu, Excel): giữ trước một khối tên Task bằng một lần cập nhật naming series, tính sẵn đường dẫn cây, ghi 500 dòng mỗi câu, rồi `reconcile`. Dự án 2 045 việc chèn trong khoảng 1 s.
- **Ngày của Task trong ERPNext v16 là Datetime**, không phải Date. Mã so sánh bằng `getdate`; SPA cắt 10 ký tự đầu khi đưa vào ô `type="date"`.
- **Đường cong S:** hai chuỗi trên một trục 0–100 % (thực tế: đường liền, xanh; kế hoạch: nét đứt, cam), có chú giải, nhãn ở điểm cuối, tooltip theo ngày và bảng số liệu. Bảng màu đã chạy qua bộ kiểm (độ sáng, độ bão hòa, phân biệt khi mù màu, độ tương phản) trên nền sáng và tối.

## 5. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **108/108** (62 của M1 + 46 mới) |
| `test_assignments` (11) | Một người chịu trách nhiệm chính, chuyển giao, nhận / từ chối có lý do, thu hồi, không xóa được, đội nhận việc, tổ trưởng chỉ thấy việc của đội |
| `test_rollup` (11) | Ba cách tính, nhiều cấp, trạng thái nhóm, đánh dấu sau commit, job lỗi giữ lại việc cần tính, di chuyển, đối soát, cờ trễ hạn, ảnh chụp hằng ngày |
| `test_progress` (10) | Báo tiến độ, duyệt / trả lại, việc trễ phải có lý do, nhóm không báo được, người ngoài không báo được, gửi trùng `client_uuid`, Kanban, đổi hạn cần lý do |
| `test_tree` (7) | Thêm dưới việc lá, di chuyển và sắp xếp lại, hủy / xóa, tạo từ mẫu, nhập Excel (chạy thử báo đủ lỗi; nhập thật giao người phụ trách) |
| `test_work` (7) | Việc của tôi, Kanban theo phạm vi, Ai làm gì, chi tiết công việc, nhắc việc một lần mỗi ngày, tổng quan, thành viên |
| vitest (7 tệp) | **81/81** (thêm `work.test.js`: 15) |
| `vite build` | Qua (JS 339 KB, gzip 105 KB) |
| ruff (CI), `compileall`, `scripts/ci/check_repo.py` | Không lỗi |
| `scripts/e2e/smoke_http.py` | **18/18** (thêm 8 kiểm tra API của M2, chỉ đọc) |
| Hiệu năng rollup | Xem [HIEU_NANG.md](../HIEU_NANG.md#m2--rollup-trên-dự-án-2-000-việc-2026-11-04) |

**Clone sạch:**
- Cách làm như M1: xuất các file đã stage (`git checkout-index`) sang thư mục mới; `.env` từ `.env.example`, chỉ đổi tên compose, tiền tố volume và port (`pmclone`, 8891); để trống secret; chạy `bootstrap.ps1`.
- Kết quả:
  - bootstrap tự sinh secret, build image, tạo site, setup wizard xong;
  - smoke HTTP 18/18 (sau khi nạp dữ liệu mẫu bằng `setup.demo.up`);
  - báo tiến độ → % dự án đổi qua worker: trung vị 1.048 ms, tối đa 3.755 ms;
  - test `project_manager` 108/108, `pm_construction` 2/2;
  - chạy bootstrap lần hai: không lỗi, smoke vẫn xanh.
- Sau đó gỡ stack clone kèm volume và xóa thư mục.

## 6. Điểm cần chú ý khi duyệt

- **Kiểm tra trên trình duyệt** (người duyệt đăng nhập sẵn, vì công cụ an toàn không cho Claude đọc mật khẩu admin):
  - đã xem Dự án, Tổng quan (đường cong S, giai đoạn, chậm ở đâu), Công việc, Kanban, Ai làm gì, Thành viên, Việc của tôi, chi tiết công việc, hộp tạo dự án;
  - đã thử: đổi thứ tự trong cây rồi đưa về; báo tiến độ 70 → 80% (nhóm "Phần móng" lên 87,62% đúng như tính tay); kéo một việc trễ chưa có lý do sang "Xong" (bị từ chối, bảng chi tiết mở sẵn ô lý do chậm);
  - ở cỡ 375 px không trang nào cuộn ngang; console không có lỗi ngoài mã 417 cố ý của lần kéo bị từ chối.
  - Lỗi tìm được và đã sửa (kèm test):
    - "Hoạt động gần đây" không nói việc nào → thêm mã và tên công việc;
    - menu thao tác trên cây không đóng sau khi bấm, và đi theo dòng vừa di chuyển;
    - trên điện thoại cây công việc không hiện % tiến độ;
    - cột "Báo cáo gần nhất" trong Ai làm gì lấy lần cập nhật của việc (do bất kỳ ai), nay là lần báo của chính người đó;
    - chi tiết công việc không hiện phần giải thích chậm.
- **Dữ liệu mẫu** đang có trên site dev: dự án "Nhà phố anh Minh – Quận 7" (DEMO-NP01) và mẫu "Nhà phố 3 tầng" (DEMO-MAU). Gỡ: `bench --site pm.localhost execute project_manager.project_manager.setup.demo.down`.
- `docker-compose.yml`: mọi service chạy lâu đổi `restart: on-failure` → `unless-stopped`. Lý do: sau khi Docker khởi động lại, redis, queue-long và scheduler thoát với mã 0 và không tự bật lại, nên job nền và lịch chạy đứng im.
- Báo tiến độ trên nhóm bị từ chối: tiến độ của nhóm luôn là số cộng dồn.
- Thêm việc con dưới một việc lá biến việc lá thành nhóm. Việc lá đã có báo cáo tiến độ thì không chia nhỏ được, để số liệu đã báo không bị mất.

## 7. Việc tiếp theo

**M3 — Biểu mẫu động:** mẫu biểu mẫu có phiên bản, nộp và duyệt, in PDF, điều kiện "phải có biểu mẫu đã duyệt mới đóng việc".
