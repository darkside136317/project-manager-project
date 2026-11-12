# M10 — Báo cáo, nhập/xuất, ngân sách, rủi ro, phát sinh

## 1. Mục tiêu

Theo kế hoạch (prompt 4.9, 4.10):
- báo cáo tiến độ, hiệu suất, vật tư, chi phí: CSV, XLSX, PDF, gửi theo lịch;
- nhập, xuất MS Project XML;
- ngân sách và EVM; sổ rủi ro và vấn đề; change request có duyệt;
- điểm mở rộng cho cầu nối lưu trữ: sự kiện `project_close_handlers` và API xuất gói hồ sơ dự án (ZIP + manifest).

## 2. Ngân sách và giá trị thu được (`services/budget.py`, tab "Ngân sách")

**PM Budget** (+PM Budget Line) có phiên bản như baseline:
- mỗi dòng có khoản mục (Vật tư, Nhân công, Máy thi công, Thầu phụ, Chi phí chung, Dự phòng, Phát sinh, Khác), một hạng mục hoặc công việc (không bắt buộc), diễn giải và số tiền;
- mỗi lúc một bản nháp. "Điều chỉnh" chép ngân sách đang dùng thành bản nháp. Duyệt bản nháp thì nó thành bản đang dùng (BAC), bản trước chuyển sang "Thay thế";
- phát sinh được duyệt thêm một dòng "Phát sinh" vào ngân sách đang dùng (mục 4).

**Chi phí thực tế (AC)** gồm:
- chi phí nhân công trên Timesheet của ERPNext (theo công việc);
- những gì lớp ngành báo qua hook mới `pm_actual_costs`. Lớp thi công báo chi phí vật tư, máy, nhân công của từng công tác (M8).

**EVM hôm nay:**
- PV = BAC × tiến độ kế hoạch (đường cong của baseline chính, không có thì theo kế hoạch);
- EV = BAC × tiến độ;
- CPI = EV / AC, SPI = EV / PV;
- EAC = AC + (BAC − EV) / CPI; ETC = EAC − AC; VAC = BAC − EAC; TCPI = (BAC − EV) / (BAC − AC).

Tab "Ngân sách" có:
- tám ô chỉ số, tô màu: dưới 0,9 đỏ, dưới 1 vàng;
- ngân sách so với thực tế theo khoản mục (thanh "đã dùng") và theo hạng mục cấp 1;
- danh sách các bản, các dòng của bản đang dùng, trình sửa bản nháp.

Ai: xem cần `finance.view` (hoặc `budget.manage`); lập và duyệt cần `budget.manage` (quyền mới, có ở Quản lý dự án và Kế toán dự án).

## 3. Rủi ro và vấn đề (`services/control.py`, tab "Rủi ro, vấn đề")

**PM Risk:**
- khả năng và ảnh hưởng từ 1 đến 5; điểm là tích của hai số. Mức: dưới 5 là Thấp, dưới 12 là Trung bình, từ 12 trở lên là Cao;
- có nhóm, người phụ trách (được báo), cách ứng phó (Giảm thiểu, Tránh, Chuyển giao, Chấp nhận), kế hoạch ứng phó, hạn, công việc liên quan;
- trạng thái: Mở, Đang xử lý, Đã xảy ra, Đã đóng. "Đã xảy ra" đóng rủi ro và mở một vấn đề từ nó.

**PM Issue:**
- có mức ưu tiên (Khẩn, Cao, Trung bình, Thấp), người xử lý (được báo), hạn;
- chuyển sang "Đã giải quyết" phải ghi cách giải quyết;
- loại cảnh báo mới **"Vấn đề quá hạn xử lý"** (quy tắc mặc định, leo thang lên Chỉ huy trưởng sau 3 ngày) báo cho người xử lý và quản lý dự án.

Tab có ma trận 5 × 5 của các rủi ro đang mở, sổ rủi ro và danh sách vấn đề.

Ai: xem là những người thấy toàn bộ dự án. Vai trò chỉ thấy việc được giao (Tổ trưởng, Khách) không xem được. Ghi cần `risk.manage` (quyền mới: Quản lý dự án, Chỉ huy trưởng, Kỹ sư).

## 4. Phát sinh (`services/control.py`, tab "Phát sinh")

**PM Change Request** (+PM Change Task) gồm:
- nội dung, nguyên nhân, mô tả, chi phí phát sinh, số ngày ảnh hưởng;
- các công việc dời ngày, kèm ngày kết thúc hiện tại (ghi lại khi lập) và ngày kết thúc mới.

Luồng: **Nháp → Chờ duyệt → Đã duyệt / Từ chối**, hoặc **Đã hủy**.
- Gửi duyệt thì báo cho những người có `change.approve` trong dự án.
- Người lập không tự duyệt được (quản trị thì được). Từ chối phải ghi lý do.
- **Duyệt** thì chi phí cộng vào ngân sách đang dùng. Các công việc dời đến ngày kết thúc mới, kéo theo việc phụ thuộc (`schedule.apply`, lý do là mã phát sinh). Người lập được báo.

Ai: lập cần `change.request` (Quản lý dự án, Chỉ huy trưởng, Kỹ sư); duyệt cần `change.approve` (Quản lý dự án).

Patch `m10_control_capabilities` thêm bốn quyền mới vào các vai trò dựng sẵn của site đã cài trước M10.

## 5. Báo cáo (`services/reports/`, `/pm/bao-cao`)

**Khung báo cáo** sao chép từ `document_manager` (mục 10): registry, bộ lọc, chạy, xuất CSV/XLSX, trang in, PDF. Phạm vi là dự án; lớp ngành thêm báo cáo qua hook mới `pm_reports`.

| Nhóm | Báo cáo | Phạm vi |
|---|---|---|
| Tiến độ | Tiến độ các dự án; Công việc trễ | Dự án xem được; việc thấy được (vai trò chỉ thấy việc được giao vẫn theo đúng như vậy) |
| Nhân sự | Hiệu suất nhân sự; Năng suất tổ đội (khi có lớp ngành) | Ai xem hiệu suất của ai (M9) |
| Tài chính | Ngân sách và giá trị thu được (EVM) | Chỉ dự án có `finance.view` |
| Kiểm soát dự án | Sổ rủi ro; Vấn đề; Phát sinh | Dự án thấy toàn bộ |
| Thi công (lớp) | Vật tư so với định mức; Chi phí thực tế so với dự toán | Một dự án (bắt buộc chọn); chi phí cần `finance.view` |

Mỗi báo cáo có bộ lọc (giữ trên địa chỉ để chia sẻ), dòng tổng, phân trang, và bốn đường ra: Excel, CSV, trang in, PDF. Trang in và PDF có đầu trang là công ty mặc định của ERPNext.

**Gửi theo lịch** (PM Report Subscription, `services/reports/schedule.py`):
- một báo cáo với bộ lọc của nó, PDF hoặc Excel, hằng ngày, hằng tuần (một thứ) hoặc hằng tháng (ngày 1–28), vào một giờ;
- người nhận chọn trong những người cùng dự án với người tạo;
- mỗi giờ, vào phút thứ 5, một job ở hàng đợi `long` gửi những lịch đến hạn;
- **mỗi người nhận nhận báo cáo chạy dưới tên chính họ.** Không ai nhận được dòng mình không được xem. Người không chạy được báo cáo thì không nhận, và được ghi ở "lỗi lần cuối";
- tệp đi qua email khi site có tài khoản gửi email (như cảnh báo M7); thông báo trong ứng dụng kèm liên kết luôn có;
- có nút "Gửi thử ngay".

## 6. MS Project XML (`services/msproject.py`, tab "Công việc")

**Xuất (MSPDI):**
- cây công việc theo thứ tự (cấp, mã WBS);
- ngày kế hoạch (08:00–17:00); thời lượng tính theo ngày làm việc của lịch dự án, 8 giờ một ngày;
- lịch tuần của dự án; mốc, nhóm, phần trăm hoàn thành, ngày thực tế, ghi chú;
- phụ thuộc FS, SS, FF, SF kèm độ trễ;
- người chịu trách nhiệm, thực hiện là tài nguyên kèm phân công.

Chỉ xuất những việc người dùng thấy được.

**Nhập** (xem trước rồi mới ghi, như nhập Excel):
- công việc của tệp vào cuối dự án, gồm cây theo cấp (báo lỗi khi nhảy cấp), ngày kế hoạch (của nhóm thì tính lại từ việc con), mốc (loại "Mốc"), ghi chú;
- phụ thuộc giữa các việc trong tệp. Phụ thuộc phạm luật bị bỏ và báo lại: vòng tròn, nhóm với việc trong nhóm, nhóm theo SS/SF;
- người chịu trách nhiệm khi tài nguyên của việc là thành viên dự án (theo email hoặc họ tên).

Tiến độ trong tệp **không** được nhập (có cảnh báo khi xem trước). Tệp có DOCTYPE hoặc ENTITY bị từ chối, vì image không có `defusedxml`. Giới hạn 10 MB, 5.000 công việc.

## 7. Đóng dự án và gói hồ sơ (`services/closing.py`)

Tab Tổng quan có phần "Kết thúc dự án", cho người có `project.edit`:
- liệt kê những gì còn mở: việc chưa xong, rủi ro, vấn đề, phát sinh chưa quyết, biểu mẫu chờ duyệt, ngân sách nháp, cảnh báo;
- **Đóng dự án** (phải ghi kết luận):
  - `pm_state` chuyển "Đóng", trạng thái ERPNext chuyển Completed, các cảnh báo đang mở kết thúc;
  - mọi hàm của hook mới `project_close_handlers` được gọi với dự án. Một cầu nối lưu trữ sẽ cắm vào đây;
- **Mở lại** (phải ghi lý do);
- **Xuất hồ sơ dự án (ZIP)**: lập ở hàng đợi `long`, **dưới tên người yêu cầu** (chỉ những gì họ xem được). Gói lưu thành tệp riêng tư của dự án; xong thì người yêu cầu được báo kèm liên kết tải.

Nội dung gói:
- `manifest.json`: dự án, người lập, lúc lập, và mọi mục kèm kích thước, SHA-256, nguồn;
- `du-an.json`, `cong-viec.csv`, `thanh-vien.csv`;
- `rui-ro.csv`, `van-de.csv`, `phat-sinh.csv`; `ngan-sach.csv` khi có `finance.view`;
- `tai-lieu/<nhóm>/`: bản hiện hành của mỗi tài liệu;
- `bieu-mau/<mẫu>/`: các biểu mẫu đã duyệt, dạng PDF;
- phần của lớp ngành qua hook mới `pm_dossier_parts`. Lớp thi công thêm `thi-cong/nhat-ky-thi-cong.csv`, `khoi-luong-theo-ngay.csv` và BOQ đã duyệt.

Giới hạn 1 GB tệp mỗi gói.

## 8. Hook mới của lõi

| Hook | Hàm nhận | Trả về |
|---|---|---|
| `pm_reports` | — | Các `Report` của lớp ngành |
| `pm_actual_costs` | (project) | [{"task", "category", "amount"}] |
| `pm_dossier_parts` | (project) | [{"path", "content", "source"}] |
| `project_close_handlers` | (project) | — (gọi khi đóng dự án) |

## 9. File chính

| File | Nội dung |
|---|---|
| Lõi `doctype/pm_budget*`, `pm_risk`, `pm_issue`, `pm_change_request`, `pm_change_task`, `pm_report_subscription`, `pm_report_recipient` | 8 DocType mới, có index; bốn DocType theo dự án có hook phân quyền |
| Lõi `services/budget.py`, `control.py`, `closing.py`, `msproject.py`, `reports/` (`base.py`, `__init__.py`, `output.py`, `core.py`, `schedule.py`) | Nghiệp vụ |
| Lõi `api/control.py`, `api/reports.py`, `api/wbs.py` (MS Project) | API |
| Lõi `constants.py` (bốn quyền mới, quy tắc cảnh báo), `permissions.py`, `hooks.py` (job gửi báo cáo), `patches/m10_control_capabilities.py`, `services/alerts.py`, `services/schedule.py` (`check_many`), `templates/pm_report_print.html` | Nối vào phần đã có |
| Lõi `frontend/src/pages/ReportsHub.vue`, `ReportPage.vue`, `project/BudgetTab.vue`, `ControlTab.vue`, `ChangesTab.vue`, `ImportDialog.vue`, `OverviewTab.vue`; `lib/control.js`, `lib/reports.js`, `components/FilterForm.vue` | Giao diện |
| Lớp `services/reporting.py`, `hooks.py` | Chi phí thực tế, hai báo cáo, phần hồ sơ thi công |
| Dữ liệu mẫu: lõi `setup/demo.py` (`_control`, `drop_control`), lớp `setup/demo.py` | Ngân sách, rủi ro, vấn đề, phát sinh, lịch gửi |
| `scripts/e2e/ui/control_flow.mjs`, `scripts/perf/control_check.py` | Kịch bản trình duyệt, đo hiệu năng |

## 10. Mã sao chép

Khung báo cáo, trang danh mục báo cáo, trang một báo cáo, bộ lọc và mẫu in được sao chép từ `document_manager` rồi sửa: phạm vi theo dự án, đầu trang công ty của ERPNext, cột tiền, gửi theo lịch, bỏ phần kiểm kê. Chi tiết ở [NGUON_GOC.md](../NGUON_GOC.md#m10).

## 11. Quyết định kỹ thuật

- **Báo cáo gửi theo lịch chạy dưới tên từng người nhận**, không dưới tên người tạo. Như vậy một lịch không làm lộ dữ liệu. Đổi lại, mỗi người nhận một bản khác nhau và tốn một lần chạy mỗi người.
- **EVM tính mỗi lần xem, không lưu.** BAC lấy từ ngân sách đang dùng, AC từ các nguồn (timesheet, lớp ngành), PV và EV từ tiến độ. Chưa có đường cong EV/AC theo thời gian (để sau).
- **Phát sinh được duyệt sửa ngân sách đang dùng** (thêm dòng), không tạo phiên bản ngân sách mới, để lịch sử ngân sách gọn. Dòng ghi mã phát sinh.
- **Rủi ro, vấn đề, phát sinh chỉ cho người thấy toàn bộ dự án:** nội dung của chúng thường nhạy cảm với tổ đội, nhà thầu phụ, khách.
- **Nhập MS Project chèn phụ thuộc hàng loạt, kiểm vòng tròn một lần** (mục 13).
- **Gói hồ sơ là tệp riêng tư của Frappe,** không ở MinIO. Tải về theo quyền đọc dự án của Frappe.

## 12. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **306 + 17** (trước M10: 292 + 17; thêm `test_control`, 14 bài: nháp, duyệt và thay thế ngân sách; ai xem, ai lập; các số EVM; rủi ro, đã xảy ra thành vấn đề, giải quyết phải ghi cách; ai xem sổ rủi ro; cảnh báo vấn đề quá hạn; phát sinh từ đề nghị tới ngân sách và kế hoạch; từ chối, hủy; mọi báo cáo chạy trong phạm vi; tệp CSV, Excel, trang in; lịch gửi: đến hạn, mỗi người nhận theo quyền của mình, email khi có tài khoản; MS Project đi rồi về; tệp bị từ chối, nhảy cấp, vòng tròn; đóng, mở lại, hồ sơ, hook khi đóng; `test_hook_coverage` nay gồm bốn DocType mới) |
| `run-tests --app pm_construction` | **57/57** (trước M10: 54; thêm `test_reporting`, 3 bài: chi phí công tác vào EVM; hai báo cáo của lớp và phạm vi của chúng; phần hồ sơ thi công) |
| vitest | **221/221** (18 tệp; thêm `control.test.js`, 11 bài: tiền, chỉ số, ma trận, dòng ngân sách, ô báo cáo, lịch gửi; tab Ngân sách (chỉ số, duyệt, lập, không có quyền); tab Rủi ro (ghi rủi ro); tab Phát sinh (duyệt, lập và gửi); trang báo cáo (bộ lọc bắt buộc, chạy từ địa chỉ chia sẻ, xuất, lịch gửi)) |
| `scripts/e2e/ui/control_flow.mjs` | **37/37** trên Edge thật (mục 15) |
| Hiệu năng | Báo cáo EVM 55 dự án 0,38–0,49 s; xuất MS Project 2.004 việc 0,24–0,33 s, nhập 1,6 s. Xem [HIEU_NANG.md](../HIEU_NANG.md#m10--báo-cáo-evm-ms-project-hồ-sơ-dự-án-2026-11-12) |

Lỗi tìm ra khi chạy test, kịch bản và đo, đã sửa:
- **nhập MS Project 2.000 việc mất 42 s:** mỗi phụ thuộc kiểm vòng tròn trên cả mạng việc, rồi chèn từng dòng. Nay còn 1,6 s (mục 13);
- **gửi email khi site không có tài khoản gửi email làm hỏng cả lượt gửi** (Frappe từ chối ngay khi xếp hàng email có tệp kèm). Nay email chỉ đi khi có tài khoản, như cảnh báo M7;
- **dữ liệu mẫu dời ngày bàn giao sớm lên thay vì lùi lại:** phát sinh mẫu lấy ngày kết thúc đọc trước khi kế hoạch bị dời. Ảnh chụp của kịch bản lộ ra lỗi này;
- người phụ trách rủi ro, vấn đề nhận thông báo mỗi lần mục đó được sửa; nay chỉ khi người phụ trách đổi;
- tiến độ kế hoạch của EVM bỏ qua ngày truyền vào (luôn tính theo hôm nay).

## 13. Hiệu năng

Xem [HIEU_NANG.md](../HIEU_NANG.md#m10--báo-cáo-evm-ms-project-hồ-sơ-dự-án-2026-11-12).

## 14. Dữ liệu mẫu (bổ sung)

**Nhà phố:**
- ngân sách thi công đã duyệt, theo bốn giai đoạn và dự phòng (số minh họa, khoảng 1,9 tỷ);
- bốn rủi ro: ba đang mở (mưa kéo dài, mức cao; giá thép tăng; thiếu thợ hoàn thiện), một đã đóng;
- hai vấn đề: bản vẽ điện chưa duyệt (quá hạn, nên có cảnh báo) và một vấn đề đã giải quyết;
- hai phát sinh:
  - mái che sân thượng: 45 triệu, đã duyệt, cộng vào ngân sách, lùi ngày bàn giao 3 ngày;
  - đổi gạch ốp: kỹ sư gửi, chờ duyệt;
- lịch gửi "Tiến độ các dự án" sáng thứ Hai cho quản lý và chỉ huy trưởng.

**Nhà xưởng:**
- ngân sách chi phí bằng 92% giá trị dự toán, chia minh họa vật tư 60%, nhân công 25%, máy 15% theo hạng mục. CPI có nghĩa vì đã có chi phí thực tế;
- rủi ro "Thép cột về chậm" (mức cao);
- vấn đề "Cần trục trùng lịch với dự án nhà phố";
- phát sinh "Tăng mác bê tông cột" chờ duyệt.

## 15. Tiêu chí hoàn thành

`control_flow.mjs` trên dữ liệu mẫu (ảnh trong `scripts/e2e/ui/out/control/`):
1. **Kỹ sư, điện thoại:**
   - lập và gửi duyệt phát sinh; không có nút duyệt phát sinh của mình;
   - không cuộn ngang;
   - không xem được ngân sách.
2. **Quản lý dự án:**
   - tab Ngân sách: tám chỉ số EVM, khoản mục;
   - tab Rủi ro: sổ rủi ro mẫu, vấn đề quá hạn tô đỏ; ghi rủi ro mới (điểm 16, mức cao tính ngay); đánh dấu đã xảy ra thì thành vấn đề;
   - tab Phát sinh: duyệt phát sinh của kỹ sư, ngân sách đang dùng tăng đúng 3,5 triệu.
3. **Báo cáo:**
   - danh mục báo cáo có lịch gửi của quản lý;
   - báo cáo EVM mở dưới 3 giây, có hai dự án mẫu;
   - Excel là tệp XLSX, PDF là tệp PDF;
   - "Gửi thử ngay" gửi cho hai người nhận.
4. **MS Project và hồ sơ:**
   - xuất kế hoạch nhà phố ra XML có phụ thuộc;
   - nhập tệp đó vào một dự án tạm: xem trước không lỗi, sau khi nhập có công việc và phụ thuộc;
   - xuất hồ sơ ZIP của dự án tạm (lập ở hàng đợi, tải về được);
   - đóng, mở lại, rồi đóng hẳn dự án tạm.

Không có lỗi JavaScript.

**Clone sạch** (xuất các tệp của repo, kể cả tệp chưa commit, bằng `git ls-files -co --exclude-standard`; cổng 8891, stack `pmclone` chạy song song với stack dev):
- bootstrap lần đầu: thoát mã 0;
- dữ liệu mẫu của lõi và lớp thi công dựng được:
  - nhà phố: BAC 1,945 tỷ (gồm 45 triệu phát sinh đã duyệt), 3 rủi ro đang mở (1 mức cao), 1 vấn đề quá hạn, 1 phát sinh chờ duyệt;
  - nhà xưởng: BAC 698 triệu, AC 172 triệu, CPI 1,32;
  - một lịch gửi báo cáo;
- site mới có:
  - index của 8 DocType mới;
  - 14 quy tắc cảnh báo, kể cả "Vấn đề quá hạn xử lý";
  - bốn quyền mới ở vai trò Quản lý dự án;
  - ba hook mới của lớp thi công;
  - job gửi báo cáo `5 * * * *`;
  - 10 báo cáo cho quản lý dự án;
- kịch bản trình duyệt: thí điểm 23/23, vật tư-máy-nhân công 33/33, khối lượng-hiệu suất 40/40, kiểm soát dự án 37/37, biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20;
- smoke 0 lỗi;
- test: `project_manager` 306 + 17, `pm_construction` 57/57;
- bootstrap lần nữa trên dữ liệu đã có: thoát mã 0, smoke 0 lỗi, cảnh báo và quy tắc còn nguyên;
- site thứ hai chỉ có ERPNext và lõi: `project_manager` 306 + 17, 11 quy tắc cảnh báo của lõi;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 16. Điểm cần chú ý khi duyệt

- **AC của dự án chỉ dùng lõi chỉ có timesheet.** Mua hàng, hóa đơn của ERPNext chưa được tính, vì dễ tính trùng với vật tư đã cấp phát của lớp thi công. Nhà phố mẫu có AC bằng 0.
- **Mức rủi ro là ngưỡng cố định trên ma trận 5 × 5** (5 và 12); chưa cho chỉnh.
- **Phát sinh được duyệt không tạo baseline mới.** Kế hoạch đổi, baseline giữ nguyên, nên chênh lệch so với baseline thể hiện phát sinh.
- **Báo cáo gửi theo lịch:** người nhận chỉ chọn được trong số người cùng dự án; email cần tài khoản gửi email của Frappe.
- **Gói hồ sơ không có báo cáo PDF tổng hợp**, chỉ có dữ liệu (CSV, JSON) và tệp gốc (tài liệu, biểu mẫu). Một bản tóm tắt PDF có thể thêm sau.
- **Kịch bản e2e để lại một dự án tạm đã đóng** mỗi lần chạy ("E2E MS Project …").

## 17. Việc tiếp theo

**M11 — Hardening và triển khai:**
- volume check đầy đủ; load test 200 người cập nhật tiến độ đồng thời;
- rà soát bảo mật (endpoint theo role, XSS, upload);
- triển khai prod, diễn tập sao lưu và khôi phục;
- README, DEPLOYMENT, hướng dẫn sử dụng.
