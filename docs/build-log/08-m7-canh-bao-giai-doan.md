# M7 — Cảnh báo, chuyển giai đoạn, sức khỏe

## 1. Mục tiêu

Theo kế hoạch (prompt 4.3, 4.6 v1):

- quy tắc cảnh báo (loại, người nhận, leo thang, giờ yên lặng);
- dự báo trễ, sức khỏe Xanh / Vàng / Đỏ;
- tóm tắt ngày và tuần, email khi có SMTP;
- chuyển giai đoạn theo điều kiện; danh mục nhiều dự án v1;
- kịch bản demo và hướng dẫn thí điểm.

Tiêu chí hoàn thành: dữ liệu mẫu công trình cho thấy cảnh báo trễ, leo thang sau X ngày, giai đoạn tự chuyển khi nghiệm thu được duyệt.

Sau M7 là thí điểm: [HUONG_DAN_THI_DIEM.md](../HUONG_DAN_THI_DIEM.md).

## 2. Sức khỏe (`services/risk.py`)

Tính ngay sau dự báo của M4 (`schedule.refresh`), nên sức khỏe luôn mới như dự báo: sau mỗi lần báo tiến độ, sau đổi lịch, và mỗi đêm.

**Công việc lá đang mở:**
- **độ trễ** là số ngày làm việc giữa ngày xong kế hoạch và ngày xong dự báo;
- **Đỏ** khi:
  - trễ quá max(3 ngày, 10% thời lượng); hoặc
  - SPI dưới 0,8 (chỉ xét khi đã qua một phần tư thời gian); hoặc
  - việc trên đường găng trễ dù một ngày;
- **Vàng** khi trễ chút ít, SPI dưới 0,95, hoặc **đình trệ** (đã bắt đầu, 5 ngày không báo tiến độ);
- việc xong hoặc hủy là Xanh.

**Nhóm và dự án:**
- xét độ trễ của chính nó (dự án so với baseline chính, không có thì so với ngày hợp đồng) và SPI;
- không bao giờ tốt hơn việc găng xấu nhất bên dưới.

**Ổn định:**
- xấu đi thì đổi ngay;
- tốt lên phải giữ nguyên 3 ngày liền mới đổi (lưu mức đang chờ và ngày bắt đầu thấy).

Ngưỡng nằm trong Thiết lập hệ thống. Dự án đổi sức khỏe thì ghi vào lịch sử; xấu đi thì mở cảnh báo "Sức khỏe dự án xấu đi".

## 3. Cảnh báo (`services/alerts.py`)

| DocType | Nội dung |
|---|---|
| PM Alert Rule (+PM Alert Escalation) | Tên, loại, số ngày, chỉ việc găng, chỉ cho loại nút; báo cho ai: người chịu trách nhiệm chính, người thực hiện, người duyệt, người theo dõi, quản lý dự án, một vai trò trong dự án, cấp trên trực tiếp (theo hồ sơ nhân viên); gửi email; các bậc leo thang (sau N ngày → quản lý, vai trò, cấp trên) |
| PM Alert | Một cảnh báo: quy tắc, tài liệu, **đợt**; Đang mở → Đã xác nhận / Đã hết; bậc leo thang; đã báo cho ai; email đang chờ. Duy nhất theo (quy tắc, tài liệu, đợt); chỉ dịch vụ ghi |
| PM Notification Preference | Lựa chọn của từng người: nhận email, giờ yên lặng, tóm tắt ngày và tuần, loại cảnh báo không nhận |

**Loại quy tắc** (9 loại của lõi, 1 loại của lớp thi công):

| Loại | Thấy khi | Đợt |
|---|---|---|
| Sắp đến hạn | Hạn trong N ngày tới | Ngày hạn |
| Quá hạn | Qua hạn mà chưa xong | Ngày hạn |
| Nguy cơ trễ | Sức khỏe Đỏ, chưa tới hạn | Ngày hạn |
| Chậm trên đường găng | Việc găng có dự báo trễ | Ngày hạn |
| Đổi sức khỏe dự án | Dự án xấu đi (sự kiện, không quét) | Mức mới + ngày |
| Chưa nhận việc | Phân công chờ nhận quá N ngày | Phân công |
| Không cập nhật | Đang làm, N ngày không báo tiến độ | Ngày báo cuối |
| Biểu mẫu chờ duyệt | Đã nộp quá N ngày | Biểu mẫu |
| Chờ duyệt chuyển giai đoạn | Giai đoạn đủ điều kiện, chờ quản lý | Giai đoạn |
| Thiếu nhật ký thi công (lớp thi công) | Dự án đang thi công, có BOQ đã duyệt, ngày làm việc gần nhất chưa có nhật ký đã nộp | Ngày thiếu |

Đổi ngày hạn là sang đợt mới: cảnh báo cũ hết, cảnh báo mới mở. Điều kiện quay lại trong cùng đợt (việc đã xong bị mở lại) thì cảnh báo cũ mở lại.

**Lịch chạy** (lịch chỉ xếp job vào hàng đợi `long`):
- 06:00: mọi quy tắc đang dùng, rồi leo thang;
- mỗi giờ: leo thang, gửi email đã chờ hết giờ yên lặng;
- 07:00: tóm tắt ngày (thay lời nhắc việc của M2);
- thứ Hai 07:00: tóm tắt tuần cho quản lý dự án;
- mỗi đêm: kiểm tra chuyển giai đoạn của mọi dự án đang chạy.

**Không gửi trùng:**
- cảnh báo duy nhất theo (quy tắc, tài liệu, đợt);
- mỗi lần báo (cảnh báo, bậc, người) giữ một khóa Redis `SET NX` một ngày;
- chỉ báo khi cảnh báo mới mở hoặc lên bậc;
- trong một lượt chạy, ai có hơn 3 cảnh báo mới thì nhận một thông báo gộp ("12 cảnh báo mới: Quá hạn 8, Sắp đến hạn 4"), email cũng gộp.

**Người nhận** phải xem được thứ được báo: tổ trưởng chỉ xem việc được giao thì không nhận cảnh báo của việc khác, người ngoài dự án đang theo dõi một việc cũng không nhận.

**Xác nhận** ("Đã biết, đang xử lý"):
- ai được báo, hoặc người có quyền lập kế hoạch hay duyệt trong dự án;
- cảnh báo thôi leo thang;
- ghi vào lịch sử công việc.

**Email:**
- chỉ gửi khi quy tắc bật "Gửi cả email", có tài khoản email gửi đi mặc định, và người nhận bật nhận email;
- trong giờ yên lặng (mặc định 21:00–07:00, mỗi người đổi được) email chờ, thông báo trong ứng dụng vẫn đến.

## 4. Chuyển giai đoạn (`services/phases.py`)

- Giai đoạn là các hạng mục cấp 1, theo thứ tự của cây. Giai đoạn hiện tại là giai đoạn đầu tiên chưa qua (`Project.pm_current_phase`).
- **Điều kiện qua giai đoạn:**
  - mọi việc bên dưới đã xong (đã gồm biểu mẫu bắt buộc của M3);
  - cộng điều kiện của lớp ngành qua hook `pm_gate_checks`. Lớp thi công đòi mọi công tác đã nghiệm thu đủ khối lượng.
- **Chế độ** (`Task.pm_gate_mode`; không đặt thì theo loại nút, rồi Thủ công):
  - **Tự động:** qua ngay; nhiều giai đoạn tự động liền nhau qua một lượt;
  - **Cần duyệt:** chờ, báo quản lý dự án; quy tắc "Chờ duyệt chuyển giai đoạn" nhắc nếu để lâu;
  - **Thủ công:** quản lý bấm chuyển khi sẵn sàng.
- Người lập kế hoạch đặt chế độ ngay ở danh sách giai đoạn trong Tổng quan. Đặt Tự động lúc giai đoạn đã đủ điều kiện thì nó qua luôn.
- **Kiểm tra lúc nào:**
  - sau mỗi lần cộng dồn có thay đổi;
  - khi một biểu mẫu được duyệt (sau khi lớp ngành cập nhật khối lượng nghiệm thu);
  - khi đổi chế độ;
  - mỗi đêm.
- Việc của giai đoạn bị mở lại khi đang chờ duyệt thì yêu cầu duyệt bị rút.
- **Qua giai đoạn thì:**
  - ghi lịch sử dự án ("Chuyển từ giai đoạn A sang B (tự động)");
  - báo quản lý và người chịu trách nhiệm của giai đoạn sau.

## 5. Màn hình

| Màn | Nội dung |
|---|---|
| `/pm/danh-muc-du-an` | Danh mục dự án: số dự án theo sức khỏe (bấm để lọc), cảnh báo đang mở; mỗi dự án: sức khỏe và lý do, tiến độ so kế hoạch, SPI, dự báo xong, giai đoạn hiện tại (chờ duyệt), cảnh báo, quá hạn. Dự án xấu nhất ở trên |
| `/pm/canh-bao` | Cảnh báo của tôi, nhóm theo dự án: loại, bậc leo thang, nội dung, mở tài liệu, "Đã biết, đang xử lý" có ghi chú; tab Đã hết |
| Tổng quan dự án | Ô sức khỏe, giai đoạn (điều kiện còn thiếu, nút chuyển hoặc duyệt), cảnh báo đang mở; giai đoạn có nhãn đã chuyển hoặc chờ duyệt, ô chọn chế độ chuyển |
| Danh sách dự án, đầu trang dự án, chi tiết công việc | Nhãn sức khỏe; công việc thêm lý do, dự báo xong, nhãn đường găng |
| Menu tài khoản → Tùy chọn thông báo | Email, giờ yên lặng, tóm tắt, loại không nhận |
| Quản trị → Quy tắc cảnh báo | Màn danh mục chung (MasterPage) với bảng bậc leo thang; quy tắc có sẵn sửa và tắt được, không xóa được |
| Menu | Tổng quan → Danh mục dự án; Công việc → Cảnh báo (có số cảnh báo đang mở) |

## 6. Lớp thi công

Ba hook mới của lõi (tài liệu trong `extensions.py`):
- `pm_alert_types`: loại cảnh báo "Thiếu nhật ký thi công";
- `pm_alert_rules`: quy tắc mặc định của loại đó, báo quản lý dự án và chỉ huy trưởng;
- `pm_gate_checks`: giai đoạn chỉ qua khi mọi công tác bên dưới đã nghiệm thu đủ khối lượng thiết kế.

Lựa chọn "Loại" của quy tắc gồm cả loại của lớp ngành, qua Property Setter. Site chỉ có lõi thì không có Property Setter nào.

**Dữ liệu mẫu nhà xưởng** dựng lại theo kịch bản thí điểm, ngày tính lùi từ hôm nay:
- PHẦN MÓNG (Tự động) đã làm xong, 4/5 công tác đã nghiệm thu, biên bản cuối chờ duyệt;
- PHẦN THÂN (Cần duyệt): cột trễ 3 ngày, có cảnh báo quá hạn mở từ 3 ngày trước nên đã leo thang lên chỉ huy trưởng;
- hôm qua chưa có nhật ký;
- công tác đã giao cho kỹ sư (chịu trách nhiệm chính) và tổ trưởng (thực hiện), cả hai đã nhận việc.

## 7. File chính

| File | Nội dung |
|---|---|
| `services/risk.py` | Phân loại, ổn định, sức khỏe việc, nhóm, dự án |
| `services/alerts.py` | Bộ đánh giá, người nhận, giao thông báo, mở / đóng / leo thang theo lô, xác nhận, tùy chọn |
| `services/phases.py` | Giai đoạn hiện tại, điều kiện, chuyển |
| `services/digest.py` | Tóm tắt ngày và tuần |
| `services/portfolio.py` | Danh mục dự án |
| `api/alerts.py` | Lớp API mỏng |
| `doctype/pm_alert*`, `pm_notification_preference` | 4 DocType mới |
| `setup/install.py` | Trường sức khỏe, giai đoạn trên Project và Task; quy tắc mặc định (`constants.DEFAULT_ALERT_RULES`) |
| `frontend/src/pages/AlertsPage.vue`, `PortfolioPage.vue`, `components/HealthBadge.vue`, `NotificationPrefsDialog.vue`, `lib/health.js` | Màn hình |
| `pm_construction/services/alerts.py`, `acceptance.gate_check`, `setup/demo.py` | Lớp thi công |
| `scripts/e2e/ui/pilot_flow.mjs` | Kịch bản trình duyệt của tiêu chí hoàn thành |
| `scripts/perf/alerts_check.py` | Đo trên 50 dự án |

## 8. Quyết định kỹ thuật

- **Một cảnh báo cho mỗi đợt**, không cho mỗi lần quét. Đợt thường là ngày hạn, nên dời hạn là chuyện mới, còn ngày nào cũng còn quá hạn thì không báo lại. Leo thang đi theo thời gian mở của cảnh báo, không theo số lần quét.
- **Quét theo lô:**
  - một quy tắc đọc các cảnh báo đang mở của nó bằng một lệnh;
  - chèn cảnh báo mới cùng lúc;
  - đọc người phụ trách của mọi việc liên quan trong vài lệnh;
  - nhớ tạm quản lý, vai trò, tùy chọn trong lượt chạy;
  - ghi người nhận và bậc leo thang bằng một lệnh cho 500 cảnh báo.
  Trên 50 dự án, 4.400 cảnh báo mới: từ 43 s xuống 1,8 s; lượt không có gì mới: từ 6,7 s xuống 0,23 s (mục 9).
- **Gộp thông báo:** ngày đầu một dự án trễ không dội hàng chục thông báo lên cùng một người. Mỗi cảnh báo vẫn ghi đủ ai đã được báo.
- **Lịch chạy xếp job vào hàng đợi `long`**, vì job theo lịch của Frappe chạy ở hàng đợi `default`, giới hạn 5 phút.
- **Quy tắc có sẵn tạo một lần theo tên,** sau đó do quản trị quản lý. Vì nếu xóa thì lần cập nhật sau nó lại hiện ra, nên không cho xóa, chỉ cho tắt.
- **Tóm tắt hằng ngày thay lời nhắc việc của M2.** Mỗi người một thông báo mỗi ngày, gồm cả cảnh báo đang mở; nội dung đổi trong ngày cũng không gửi thêm.
- **Cấp trên trực tiếp** lấy từ hồ sơ nhân viên của ERPNext (`Employee.reports_to`), không cần HRMS.
- **Cảnh báo không sửa được qua API:** quyền chỉ đọc theo phạm vi dự án và công việc (như trao đổi). Controller chặn lưu ngoài dịch vụ.

## 9. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **277 + 17** (trước M7: 238 + 17; thêm `test_alerts`, 39 bài: phân loại, ổn định, sức khỏe việc và dự án, snapshot; cảnh báo theo đợt, mở lại, gộp, leo thang, xác nhận, khóa Redis, người nhận phải xem được, cấp trên, chưa nhận việc, giờ yên lặng, email chờ, tắt loại, quyền, quy tắc; giai đoạn tự động / cần duyệt / thủ công / bị rút / điều kiện lớp ngành / giai đoạn cuối, đặt chế độ; tóm tắt; danh mục, tổng quan) |
| `run-tests --app pm_construction` | **27/27** (trước M7: 22; thêm 5: giai đoạn móng tự qua khi biên bản cuối được duyệt, nghiệm thu một phần chưa đủ, thiếu nhật ký mở và đóng cảnh báo, dự án tạm dừng thì thôi, hook đã đăng ký) |
| vitest (15 tệp) | **194/194** (thêm `alerts.test.js`: hàm sức khỏe, nhãn, trang cảnh báo, danh mục, tùy chọn thông báo, ô giai đoạn ở Tổng quan) |
| ruff (CI), `compileall`, `scripts/ci/check_repo.py` | Không lỗi |
| `scripts/e2e/smoke_http.py` | 0 lỗi (thêm cảnh báo của tôi, danh mục, tùy chọn) |
| `scripts/e2e/ui/pilot_flow.mjs` | **23/23** trên Edge thật (mục 10) |
| `forms_flow.mjs`, `schedule_flow.mjs`, `discussion_flow.mjs`, `construction_flow.mjs` | 19/19, 28/28, 27/27, 20/20 |
| Hiệu năng | 50 dự án, 10.200 việc: quét hằng ngày 0,23 s, lần đầu 1,8 s; leo thang 3.600 cảnh báo 0,3 s; danh mục 0,2 s. Xem [HIEU_NANG.md](../HIEU_NANG.md#m7--cảnh-báo-sức-khỏe-danh-mục-trên-50-dự-án-2026-11-11) |

Lỗi tìm ra khi chạy test, kịch bản và đo, đã sửa:
- `frappe.get_list` của v16 không nhận `order_by` có hàm `field(...)`: trang cảnh báo lỗi;
- leo thang hai bậc trong một lượt ghi đè người nhận của bậc trước;
- tóm tắt hằng ngày đếm việc của mọi người một lần cho mỗi người (nay một lần cho cả lượt), và kiểm "đã gửi hôm nay" theo ngày truyền vào thay vì ngày thật;
- dữ liệu mẫu:
  - công tác có ngày cuối rơi vào Chủ nhật không được làm xong;
  - công tác chưa giao người chịu trách nhiệm, nên cảnh báo không có người nhận;
- ô sức khỏe ở Tổng quan bị bóp hẹp trên điện thoại;
- quét chậm (mục 8).

## 10. Tiêu chí hoàn thành trên dữ liệu mẫu

`pilot_flow.mjs` trên dữ liệu mẫu nhà xưởng (ảnh trong `scripts/e2e/ui/out/pilot/`):
1. **Danh mục dự án:** nhà xưởng ở mức Đỏ, giai đoạn hiện tại PHẦN MÓNG, có cảnh báo đang mở.
2. **Tổng quan:**
   - sức khỏe Đỏ kèm lý do;
   - "còn 1 công tác chưa nghiệm thu đủ khối lượng";
   - cảnh báo quá hạn **leo thang bậc 1** (mở 3 ngày, quy tắc: sau 2 ngày báo chỉ huy trưởng);
   - cảnh báo thiếu nhật ký.
3. **Quản trị:** danh sách quy tắc; quy tắc "Quá hạn" có 2 bậc (2 ngày → chỉ huy trưởng, 5 ngày → quản lý).
4. **Điện thoại, chỉ huy trưởng (vào vai, không cần mật khẩu):**
   - trang Cảnh báo có cảnh báo bậc 1 và thiếu nhật ký, không cuộn ngang;
   - xác nhận một cảnh báo;
   - đổi giờ yên lặng và tắt một loại, lưu đúng.
5. **Duyệt biên bản nghiệm thu cuối của móng:**
   - **PHẦN MÓNG tự chuyển sang PHẦN THÂN**, Tổng quan ghi "Giai đoạn 2/3", chế độ Cần duyệt;
   - lịch sử ghi "Chuyển từ giai đoạn PHẦN MÓNG sang PHẦN THÂN";
   - không có lỗi JavaScript.

**Clone sạch** (xuất các tệp của repo, kể cả tệp mới chưa commit, bằng `git ls-files -co --exclude-standard` sang thư mục mới; cổng 8891, stack `pmclone` chạy song song với stack dev):
- `bootstrap.ps1` thoát mã 0 cả ba lần; smoke 0 lỗi;
- dữ liệu mẫu của lõi và lớp thi công dựng được; nhà xưởng ở mức Đỏ, có 4 cảnh báo, cảnh báo quá hạn ở bậc 1;
- site mới có đủ index của PM Alert, 10 quy tắc, lựa chọn "Loại" gồm cả loại của lớp thi công; job theo lịch của M7 đã đăng ký;
- kịch bản trình duyệt: thí điểm 23/23, biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20;
- test: `project_manager` 277 + 17, `pm_construction` 27/27;
- bootstrap lần nữa trên dữ liệu đã có: thoát mã 0, smoke 0 lỗi, cảnh báo và quy tắc còn nguyên;
- một site thứ hai chỉ có ERPNext và lõi: `project_manager` 277 + 17, có 9 quy tắc của lõi, không có Property Setter nào;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 11. Điểm cần chú ý khi duyệt

- **Ngưỡng sức khỏe, số ngày của các quy tắc, bậc leo thang** là giá trị ban đầu hợp lý, chưa qua thực tế: thí điểm sẽ cho biết cần chỉnh gì (Thiết lập hệ thống, Quy tắc cảnh báo).
- **Cảnh báo đánh giá mỗi sáng:**
  - việc vừa quá hạn trong ngày được báo sáng hôm sau;
  - riêng đổi sức khỏe dự án và giai đoạn chờ duyệt báo ngay lúc xảy ra.
- **Chưa có cảnh báo vượt định mức vật tư** (M8, cùng phần vật tư).
- **Kênh:** thông báo trong ứng dụng và email; Zalo, SMS để sau như kế hoạch.
- **Email** chưa thử với máy chủ SMTP thật: test giả lập việc gửi; cần một tài khoản email để thử khi thí điểm.
- **Danh mục dự án v1:**
  - đếm cảnh báo của cả dự án, kể cả trên việc người xem không được giao;
  - hiệu suất, nguồn lực để M9.
- **Khóa "đã báo" trong Redis** không lùi theo transaction: chạy test trên site dev có thể đánh dấu đã báo cho cảnh báo thật của site dev (site mới cài không bị).

## 12. Việc tiếp theo

**Thí điểm** theo [HUONG_DAN_THI_DIEM.md](../HUONG_DAN_THI_DIEM.md). Song song là **M8 — Vật tư, máy, nhân công:** kho công trường, đề xuất vật tư theo công tác, cấp phát, định mức so với thực tế (kèm cảnh báo vượt định mức), máy, tổ đội, chấm công.
