# M6 — Lớp thi công cơ bản

## 1. Mục tiêu

Theo kế hoạch (prompt 4.2, 4.8):

- app `pm_construction` có loại nút thi công riêng;
- BOQ: nhập từ Excel, có phiên bản, sinh WBS hạng mục và công tác; tiến độ theo khối lượng, cộng dồn theo giá trị dự toán;
- nhật ký thi công: làm được khi mất mạng, có ảnh, có xác nhận;
- nghiệm thu, với các gói biên bản mẫu;
- màn hình thi công gắn vào SPA của lõi qua `spa_modules`.

Tiêu chí hoàn thành: nhập BOQ mẫu → WBS có khối lượng → nhập khối lượng hằng ngày qua nhật ký → tiến độ dự án tính theo giá trị dự toán.

## 2. Lõi mở cho lớp ngành (lõi vẫn không import lớp thi công)

Các điểm mở rộng đọc từ hook của lớp ngành, gom trong `project_manager/extensions.py`:

| Hook | Lõi dùng để | Lớp thi công khai báo |
|---|---|---|
| `pm_rollup_methods` | Thêm cách tính tiến độ: lá nặng bằng giá trị một trường của Task | "Theo giá trị dự toán" → `pmc_estimate_value` |
| `pm_discussion_targets` | Tài liệu khác (ngoài công việc, dự án) có trao đổi và ảnh | Nhật ký thi công |
| `pm_form_events` | Gọi lớp ngành khi một biểu mẫu được duyệt | Cập nhật khối lượng đã nghiệm thu |
| `pm_spa_modules` | Bật màn hình của lớp ngành trong SPA | `construction` |
| `pm_form_packs` (có từ M3) | Gói biểu mẫu sẵn | 4 biên bản nghiệm thu |

Thêm ở lõi:
- **`progress.set_measured`:** tiến độ đo từ khối lượng. Không hỏi lý do chậm (người dùng ghi khi tự báo); việc còn thiếu điều kiện đóng (biểu mẫu chưa duyệt) dừng ở 99%.
- **Hàm phân quyền dùng lại được** trong `permissions.py`: `scope_condition`, `entry_condition`, `scoped`, `entry_scoped`, `read_only`.
- **SPA:**
  - `src/modules.js` tìm `frontend/pm-module.js` của các app nằm cạnh lõi lúc build và chỉ bật module mà máy chủ báo đã cài (`boot.modules`);
  - module thêm tab dự án (đặt sau tab nó chỉ định), trang, và loại mục cho hàng đợi gửi lại (`registerKind`);
  - tệp của lớp ngành import lõi qua alias `@pm`; test của nó tên `*.layer.test.js`, chạy chung vitest của lõi.

## 3. DocType và trường mới (lớp thi công)

| DocType | Mục đích | Ghi chú |
|---|---|---|
| PMC BOQ | Một phiên bản BOQ đã nhập, tên `{dự án}-BOQ01` | Nháp → Đã duyệt → Thay thế; không sửa được, sửa là nhập bản mới |
| PMC BOQ Item | Một dòng: hạng mục hoặc công tác | Chèn hàng loạt; khối lượng, đơn giá, thành tiền, mã hiệu định mức, công việc tương ứng |
| PMC Site Diary | Nhật ký của một dự án trong một ngày, tên `{dự án}-ND-{ngày}` | Biết trước tên nên viết được khi mất mạng; Nháp → Đã nộp → Đã xác nhận |
| PMC Diary Quantity | Khối lượng làm được của một công tác trong nhật ký | Khối lượng đã làm của công tác là tổng các dòng thuộc nhật ký đã nộp |

Trường mới trên Task (`pmc_*`):
- đơn vị, khối lượng thiết kế, đơn giá, giá trị dự toán;
- khối lượng đã làm, khối lượng đã nghiệm thu;
- mã hiệu định mức, dòng BOQ, khóa nhận diện dòng giữa các phiên bản.

Loại nút mới: "Hạng mục" (nhóm), "Công tác" (lá).

## 4. File chính

| File | Nội dung |
|---|---|
| `services/boq_import.py` | Đọc BOQ từ Excel, tệp mẫu có sẵn 17 dòng |
| `services/boq.py` | Xem trước, nhập phiên bản, duyệt rồi đồng bộ WBS, tổng giá trị đã làm và đã nghiệm thu |
| `services/diary.py` | Lưu, nộp, gửi một lần (từ hàng đợi), xác nhận, trả lại, danh sách, công tác để chọn |
| `services/quantities.py` | Khối lượng đã làm từ nhật ký; tiến độ theo khối lượng; chặn xóa công tác đã có khối lượng |
| `services/acceptance.py` | Khối lượng đã nghiệm thu từ biên bản đã duyệt; bảng tổng hợp nghiệm thu |
| `setup/install.py`, `setup/form_pack.py`, `setup/demo.py` | Trường thêm, loại nút; 4 biên bản; dữ liệu mẫu nhà xưởng |
| `api/construction.py` | Lớp API mỏng |
| `frontend/pm-module.js`, `frontend/src/*.vue` | Tab BOQ, Nhật ký, Nghiệm thu; gửi nhật ký qua hàng đợi |
| `scripts/e2e/ui/construction_flow.mjs` | Kịch bản trình duyệt của tiêu chí hoàn thành |

## 5. Quyết định kỹ thuật

- **Đọc BOQ:**
  - dòng tiêu đề được dò trong 25 dòng đầu, theo tên cột không dấu (STT, Mã hiệu, Nội dung công việc, Đơn vị, Khối lượng, Đơn giá, Thành tiền); chỉ bắt buộc cột nội dung và khối lượng;
  - đọc sheet có nhiều dòng nhất (sổ dự toán thường có trang bìa);
  - dòng không có khối lượng và đơn vị là hạng mục; hạng mục lồng nhau theo kiểu đánh số (A, B → I, II → 1, 2); một chữ I, V, X, C là chữ cái khi đứng ngay sau chữ cái trước đó (C sau B), là số La Mã nếu không (I dưới B);
  - số đọc được cả kiểu Việt Nam (1.234,5) lẫn kiểu quốc tế (1,234.5);
  - bỏ dòng tổng; báo thành tiền lệch, khối lượng 0, thiếu đơn vị.
- **Duyệt BOQ thì WBS đi theo:**
  - lần đầu sinh cả cây một lượt (chèn hàng loạt);
  - các lần sau nhận ra dòng cũ theo STT và nội dung dưới cùng hạng mục cha: cập nhật khối lượng, đơn giá; thêm dòng mới; dòng biến mất chỉ được báo, công việc của nó vẫn giữ (có thể đã có lịch sử);
  - phương pháp tính tiến độ của dự án chuyển sang "Theo giá trị dự toán".
- **Khối lượng đã làm không bao giờ nhập tay:**
  - là tổng khối lượng của các nhật ký đã nộp, tính lại mỗi khi một nhật ký đổi trạng thái;
  - trả lại nhật ký thì khối lượng của nó thôi được tính;
  - tiến độ công tác = đã làm / thiết kế.
- **Nghiệm thu là biểu mẫu của M3:**
  - 4 mẫu: nghiệm thu công việc, nghiệm thu giai đoạn, kiểm tra an toàn lao động, bàn giao mặt bằng; dùng lại trình thiết kế, chữ ký, duyệt, PDF và điều kiện đóng việc;
  - biên bản nghiệm thu công việc có trường "Khối lượng nghiệm thu"; khi được duyệt, khối lượng đã nghiệm thu của công tác bằng tổng các biên bản đã duyệt;
  - kế hoạch dự kiến DocType PMC Acceptance riêng; làm theo cách này ít mã hơn và không có hai luồng duyệt.
- **Nhật ký khi mất mạng:** đi qua hàng đợi gửi lại của M5 thành ba bước (lưu, gửi ảnh, nộp), bước nào gửi lại cũng không sinh bản trùng; ảnh của nhật ký đi kèm một bình luận nên hiện trên tường ảnh của dự án.
- **Ai làm gì:**
  - nhập, duyệt BOQ cần quyền lập kế hoạch;
  - ghi nhật ký cần quyền cập nhật tiến độ;
  - xác nhận, trả lại nhật ký cần quyền duyệt; lập biên bản như biểu mẫu thường.
- **Sửa ở lõi M2 (cộng dồn) và M4 (đường găng):**
  - job của một dự án đang chạy thì lệnh xếp job mới bị Frappe bỏ qua vì trùng, nên thay đổi vừa đến chờ tới lượt quét 5 phút;
  - kịch bản trình duyệt bắt được: tiến độ dự án vẫn 0 sau khi nhật ký gửi bù lên;
  - nay khi job đang chạy, `services/jobs.enqueue_once` xếp thêm đúng một job chạy ngay sau nó.
- **Toast cảnh báo:** kiểu "warning" trước đây hiện như thành công (có từ M5), nay có màu và biểu tượng riêng.

## 6. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **238 + 17** (thêm 1: job chạy tiếp khi job trước đang chạy) |
| `run-tests --app pm_construction` | **22/22** (trước M6: 2): đọc BOQ, phiên bản, WBS, nhật ký, khối lượng, nghiệm thu, phạm vi quyền, hook |
| vitest (14 tệp) | **184/184** (thêm `modules.test.js` và `construction.layer.test.js` của lớp thi công) |
| ruff (CI), `compileall`, `scripts/ci/check_repo.py` | Không lỗi |
| `scripts/e2e/ui/construction_flow.mjs` | **20/20** trên Edge thật: nhập BOQ mẫu, xem trước, duyệt, WBS có hạng mục; điện thoại mất mạng ghi nhật ký có khối lượng và ảnh, có mạng thì tự nộp, tiến độ công tác 50%; xác nhận; phần giá trị đã thi công; tiến độ dự án theo giá trị dự toán; lập biên bản nghiệm thu; không cuộn ngang |
| `forms_flow.mjs`, `schedule_flow.mjs`, `discussion_flow.mjs` | 19/19, 28/28, 27/27 |
| Hiệu năng | BOQ 3.000 dòng: duyệt lần đầu 3,4 s, lần sau 0,7 s. Xem [HIEU_NANG.md](../HIEU_NANG.md#m6--boq-3000-dòng-2026-11-09) |

Lỗi tìm ra khi chạy test và kịch bản, đã sửa:
- hàm API `boq_import` trùng tên module `boq_import` (ruff bắt được, tải mẫu BOQ sẽ hỏng);
- job trùng bị bỏ qua (mục 5);
- sau một lần migrate dở, index của bảng mới không được tạo trên site dev. Nguyên nhân: dev-watcher migrate ngay lúc controller còn rỗng. Site cài mới không bị, đã kiểm trên clone sạch.

**Clone sạch** (xuất bằng `git checkout-index` sang thư mục mới, cổng 8891, stack `pmclone` chạy song song với stack dev):
- `bootstrap.ps1` thoát với mã 0; smoke 0 lỗi;
- dữ liệu mẫu của lõi và của lớp thi công dựng được;
- bảng mới của M5, M6 có đủ index trên site mới cài;
- kịch bản trình duyệt: biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20;
- test: `project_manager` 238 + 17, `pm_construction` 22/22;
- bootstrap lần hai thoát với mã 0, smoke 0 lỗi, dữ liệu còn nguyên, ảnh vẫn đọc được từ MinIO;
- một site thứ hai chỉ có ERPNext và lõi (như job CI `core-alone`): `project_manager` 238 + 17, lõi chạy được khi không có lớp thi công;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 7. Điểm cần chú ý khi duyệt

- **Chưa thử với tệp BOQ của phần mềm dự toán thật** (G8, Eta, F1...). Bộ đọc nhận nhiều cách đặt tên cột và kiểu số; nếu có tệp mẫu thật thì nên thử trước khi thí điểm.
- **Chỉ đọc .xlsx,** chưa đọc .xls đời cũ.
- **BOQ không mang ngày:** công tác sinh ra chưa có ngày kế hoạch, người lập kế hoạch đặt ngày trên Gantt.
- **Dòng biến mất khỏi BOQ mới chỉ được báo,** không tự hủy công việc.
- **Định mức vật tư, kế hoạch vật tư, máy, nhân công** để M8 như kế hoạch; mã hiệu định mức mới được lưu lại.
- **Điều kiện chuyển giai đoạn của lớp thi công** (ví dụ mọi nghiệm thu đã duyệt) để M7.
- **Nhật ký mới có số nhân công tổng;** nhân lực theo tổ, máy theo ca để M8.
- **Dữ liệu mẫu:**
  - dựng bằng `pm_construction.pm_construction.setup.demo.up` sau dữ liệu mẫu của lõi, gỡ bằng `.down` trước khi gỡ dữ liệu mẫu của lõi;
  - có dự án nhà xưởng, BOQ được duyệt, 6 nhật ký và 1 biên bản nghiệm thu đã duyệt.

## 8. Việc tiếp theo

**M7 — Cảnh báo thông minh, chuyển giai đoạn, sức khỏe:** quy tắc cảnh báo có leo thang, sức khỏe Xanh/Vàng/Đỏ, tóm tắt ngày và tuần, chuyển giai đoạn theo điều kiện. Xong M7 thì thí điểm.
