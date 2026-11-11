# M9 — Hiệu suất, khối lượng công việc, nhiều dự án v2

## 1. Mục tiêu

Theo kế hoạch (prompt 4.4, 4.6):
- PM Performance Snapshot: tỷ lệ đúng hạn, khối lượng, năng suất = khối lượng / công;
- khối lượng công việc (workload) và năng lực theo tuần; cảnh báo quá tải;
- xung đột người và máy giữa các dự án;
- danh mục dự án v2;
- giới hạn ai xem hiệu suất của ai.

Kiểm thử theo kế hoạch: ai xem được hiệu suất của ai, khối lượng công việc, dashboard 50 dự án dưới 2 s.

## 2. Khối lượng công việc (lõi, `services/workload.py`)

**Năng lực** của một người là 1 ngày công cho mỗi ngày làm việc theo lịch nghỉ mặc định của công ty, trừ các kỳ trong **PM Resource Capacity** (DocType mới):
- mỗi kỳ có người, từ ngày, đến ngày, phần trăm còn làm được và lý do (Nghỉ phép, Bán thời gian, Điều động việc khác, Khác);
- nghỉ phép là 0 %; kỳ chồng nhau thì lấy mức thấp nhất.

**Nhu cầu** tính từ các lượt giao còn hiệu lực (Chờ nhận, Đã nhận) cho một người, trên việc lá chưa xong của dự án Chuẩn bị hoặc Đang thực hiện, có ngày kế hoạch:
- mỗi ngày làm việc trong khoảng kế hoạch, việc chiếm **mức chiếm thời gian** của nó, là trường mới `Task.pm_load_pct`. Để trống hoặc 0 là 100 %; việc giám sát có thể là 25 %;
- phần đó chia đều cho những người **Thực hiện**. Việc không có ai thực hiện thì người **Chịu trách nhiệm chính** gánh;
- việc **đã trễ** (hết hạn mà chưa xong) dồn phần còn lại, ⌈(1 − tiến độ) × số ngày làm việc của việc⌉ ngày, vào các ngày làm việc từ hôm nay.

**Mức tải** = nhu cầu / năng lực của từng tuần:
- trên 120 %: **Quá tải**;
- trên 80 %: **Bận**;
- trên 0: **Vừa sức**;
- 0: **Rảnh**.

**Xung đột giữa các dự án:**
- một người quá tải trong tuần vì việc của từ hai dự án trở lên;
- cùng với những gì lớp ngành báo qua hook `pm_conflicts` (mục 4).

**Cảnh báo "Quá tải công việc"** là loại quy tắc mới trong lõi, có quy tắc mặc định:
- xét tuần này và tuần sau; mỗi người, mỗi tuần quá tải là một đợt;
- báo cho chính người đó và quản lý của các dự án gây ra phần việc đó;
- liên kết của cảnh báo mở trang khối lượng công việc.

## 3. Hiệu suất (lõi, `services/performance.py`)

Tính trên các việc lá mà một người **chịu trách nhiệm chính** hoặc **thực hiện**, theo từng cặp (người, dự án), trong một khoảng: tuần trước, 4 tuần hoặc 13 tuần.
- **xong**, **đúng hạn** (ngày xong thực tế ≤ ngày kết thúc kế hoạch), **xong trễ**, **trễ trung bình** (ngày);
- **đang trễ:** việc chưa xong mà ngày kết thúc kế hoạch đã qua;
- **số lần báo tiến độ** và số công đã khai trong các lần báo đó;
- **tỷ lệ đúng hạn** = đúng hạn / xong.

**Năng suất tổ đội** đến từ lớp ngành qua hook `pm_productivity`. Lớp thi công làm như sau:
- lấy khối lượng của nhật ký (đã nộp hoặc đã xác nhận) trên từng công tác;
- chia cho các tổ theo số công đã xác nhận của từng tổ trên công tác đó;
- năng suất = khối lượng / công, theo từng đơn vị (m3, tấn, 100m2…).

**PM Performance Snapshot** (DocType mới) giữ lại số liệu từng tuần:
- mỗi sáng thứ Hai lúc 01:30, job ghi tuần trước, theo ba loại: người × dự án, dự án, tổ đội × dự án;
- khóa duy nhất là (tuần, loại, đối tượng, dự án), nên chạy lại chỉ cập nhật các dòng đó;
- dùng cho xu hướng các tuần trước, vì số "đang trễ" vào cuối một tuần không tính lại được về sau.

## 4. Ai xem được của ai

`workload.scope` áp dụng cho cả khối lượng công việc và hiệu suất:

| Người xem | Thấy |
|---|---|
| Mọi người | Chính mình |
| Trưởng một đội (PM Team) | Các thành viên của đội, trong những dự án mình xem được |
| Có `perf.view_project` trong một dự án (Quản lý dự án, Chỉ huy trưởng) | Mọi người làm ở dự án đó |
| Có `perf.view_all` (Giám đốc), quản trị | Tất cả |

Phần việc ở dự án mà người xem không được thấy vẫn được tính vào mức tải, nhưng chỉ hiện là **"Dự án khác"**, không có tên hay chi tiết. Ví dụ, quản lý dự án A thấy một kỹ sư bận 140 %: 80 % ở dự án A và 60 % ở "Dự án khác".

Xung đột do lớp ngành báo chỉ hiện khi người xem đọc được ít nhất một dự án trong đó; các dự án còn lại cũng hiện là "Dự án khác".

Chỉ quản trị (`users.manage`) và người có `perf.view_all` mới ghi được kỳ nghỉ, bán thời gian. Quản trị cũng có danh sách mọi kỳ ở màn quản trị "Nghỉ phép, năng lực".

## 5. Danh mục dự án v2 (`services/portfolio.py`)

Mỗi dự án thêm các cột:
- tỷ lệ việc xong đúng hạn trong 4 tuần;
- số thành viên quá tải tuần này, bấm vào thì mở trang khối lượng công việc lọc theo dự án;
- xu hướng tiến độ 8 tuần, một đường nhỏ vẽ từ PM Snapshot hằng ngày;
- các cột của lớp ngành qua hook `pm_portfolio_columns`. Lớp thi công thêm hai cột:
  - **chi phí / giá trị làm được:** chi phí thực tế / (khối lượng đã làm × đơn giá). Cột này chỉ hiện với người có `finance.view` trong dự án; trên 105 % là đỏ;
  - **công tác vượt định mức:** số công tác có cảnh báo "Vượt định mức vật tư" đang mở hoặc đã xác nhận.

## 6. Lớp thi công: đặt máy

**PMC Machine Booking** (DocType mới, theo phạm vi dự án): máy, dự án, công tác, từ ngày, đến ngày, trạng thái (Đã đặt / Đã hủy), người đặt, ghi chú.

Tab **Máy** có thêm "Lịch đặt máy":
- người có `plan.edit` hoặc `project.edit` đặt hoặc hủy;
- máy hỏng hoặc đã trả thì không đặt được;
- dự án khác đã đặt cùng máy trùng ngày thì vẫn đặt được, nhưng hiện "Trùng lịch". Dự án không được xem hiện là "Dự án khác".

Hai dự án đặt cùng một máy có ngày trùng nhau là một **xung đột máy**: lớp thi công báo qua `pm_conflicts`.

## 7. Giao diện

| Màn hình | Nội dung |
|---|---|
| `/pm/khoi-luong-cong-viec` (mới) | Bảng người × tuần, ô tô màu theo mức tải, hiện % và "cần/có" ngày công. Có thể lọc tuần, số tuần (4–12), tổ đội, dự án, và "chỉ người bận, quá tải". Bên dưới là danh sách xung đột (10 dòng đầu, "Xem tất cả"). Bấm một ô thì mở ngăn bên: việc trong tuần (mỗi việc bao nhiêu ngày công), phần "Dự án khác", các kỳ nghỉ; người được phép ghi hoặc xóa kỳ nghỉ ngay tại đó |
| `/pm/hieu-suat` (mới) | Chọn tuần trước / 4 tuần / 13 tuần, lọc tổ đội, dự án. Bốn ô tổng; bảng theo người, theo dự án, năng suất tổ đội. Câu đầu trang nói người dùng đang xem được phạm vi nào. Bấm tên thì mở ngăn bên: theo dự án, các tuần trước (biểu đồ cột xong / trễ), danh sách việc xong và việc trễ |
| Danh mục dự án | Các cột v2 (mục 5) |
| Chi tiết công việc | Nút "Chiếm …% thời gian người làm" cho người lập kế hoạch |
| Tab Máy (lớp thi công) | Lịch đặt máy (mục 6) |
| Quản trị → "Nghỉ phép, năng lực" | Danh sách mọi kỳ (màn quản trị chung) |

Hai mục mới "Khối lượng công việc" và "Hiệu suất" nằm trong nhóm Công việc của thanh bên, hiện cho mọi nhân viên: mỗi người ít nhất thấy chính mình.

## 8. Hook mới của lõi

Ba hook mới, mô tả trong `extensions.py`:
- `pm_productivity`: hàm (first, last) trả về danh sách {team, team_name, project, task, uom, qty, man_days};
- `pm_conflicts`: hàm (first, last) trả về danh sách {kind, subject, week, projects: {dự án: phần}, message};
- `pm_portfolio_columns`: hàm (projects) trả về {dự án: {khóa: {label, value, format, tone}}}. Hàm tự kiểm người xem được thấy gì.

Lõi không import lớp ngành: khi không cài lớp nào, các phần trên rỗng (CI `core-alone`).

## 9. File chính

| File | Nội dung |
|---|---|
| Lõi `doctype/pm_resource_capacity/`, `doctype/pm_performance_snapshot/` | Hai DocType mới (chỉ quản trị đọc, ghi; ảnh chụp chỉ đọc), có index |
| Lõi `services/workload.py`, `services/performance.py`, `api/people.py` | Nghiệp vụ và API |
| Lõi `services/portfolio.py`, `services/alerts.py`, `constants.py`, `setup/install.py` (`Task.pm_load_pct`), `hooks.py` (job thứ Hai), `api/boot.py` (thanh bên), `permissions.py` (phạm vi ảnh chụp) | Danh mục v2, loại cảnh báo, quy tắc mặc định, trường, lịch chạy |
| Lõi `frontend/src/pages/WorkloadPage.vue`, `PerformancePage.vue`, `lib/people.js`; `PortfolioPage.vue`, `TaskDetail.vue` | Giao diện |
| Lớp `doctype/pmc_machine_booking/`, `services/people.py`, `services/machines.py` (`book`, `cancel_booking`), `api/site.py`, `frontend/src/MachinesTab.vue` | Đặt máy, ba hook của lớp thi công |
| Dữ liệu mẫu: lõi `setup/demo.py`, lớp `setup/demo.py`, `setup/demo_site.py` | Kỳ nghỉ, ảnh chụp các tuần trước, đặt máy trùng |
| `scripts/e2e/ui/people_flow.mjs`, `scripts/perf/people_check.py` | Kịch bản trình duyệt, đo hiệu năng |

Không có mã nào sao chép từ `document_manager` trong M9, nên `NGUON_GOC.md` không đổi.

## 10. Quyết định kỹ thuật

- **Tính khối lượng công việc trong bộ nhớ, không lưu.** Mỗi lần mở trang tính lại từ các lượt giao còn hiệu lực. Với 10.200 việc, 25.000 lượt giao, 123 người, 6 tuần, mất dưới 0,5 s (mục 12). Nhờ vậy không có bảng phải giữ khớp khi giao việc, đổi ngày hay báo tiến độ.
- **Một việc được chia cho mọi người đang giữ nó, kể cả người mà người xem không thấy**, rồi mới lọc dòng (mục 11, lỗi thứ nhất).
- **Lịch là lịch nghỉ mặc định của công ty.** Lịch riêng của từng dự án (`pm_holiday_list`) dùng cho tiến độ; còn sức của một người thì không phụ thuộc dự án.
- **Ảnh chụp tuần thay vì tính lại lịch sử.** "Đang trễ cuối tuần" không suy ra được về sau, vì việc có thể đã xong. Xu hướng của một người chỉ gồm các dự án người xem được thấy.
- **Năng suất chỉ tính khi có cả khối lượng (nhật ký) lẫn công đã xác nhận trên cùng công tác.** Công tác có khối lượng mà không có chấm công thì không chia được cho tổ nào, nên không tính.
- **Đặt máy trùng ngày là cảnh báo, không bị chặn.** Ở công trường, lịch máy thường được dàn xếp qua điện thoại; hệ thống chỉ làm cho việc trùng lịch hiện ra.

## 11. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **292 + 17** (trước M9: 282 + 17; thêm `test_people`, 10 bài: nhu cầu so với năng lực, nghỉ phép làm giảm năng lực và chỉ quản trị ghi được, ai gánh việc (người thực hiện chia đều, không có thì người chịu trách nhiệm; người tự xem vẫn chỉ thấy phần của mình), việc trễ dồn về các ngày tới, xung đột và cảnh báo quá tải, ai xem khối lượng của ai, số liệu hiệu suất của một người, ai xem hiệu suất của ai, ảnh chụp tuần ghi và ghi lại, các cột v2 của danh mục; `test_hook_coverage` nay gồm cả PM Performance Snapshot) |
| `run-tests --app pm_construction` | **54/54** (trước M9: 51; thêm `test_people_layer`, 3 bài: khối lượng chia theo công của từng tổ và chỉ tính chấm công đã xác nhận, tổ trưởng chỉ thấy tổ mình; máy hai dự án đặt trùng, ai đặt được, xung đột hiện "Dự án khác", hủy thì hết; cột chi phí chỉ cho người có `finance.view`, cột vượt định mức) |
| vitest | **210/210** (17 tệp; thêm `people.test.js`: các hàm định dạng, tuần, phần chia, cột của lớp ngành, đường xu hướng; trang khối lượng công việc (ô, xung đột, chỉ người bận, ngăn bên, ghi kỳ nghỉ, giới hạn 10 xung đột); trang hiệu suất (phạm vi, đổi khoảng, ngăn bên); danh mục v2. `site.layer.test.js` thêm lịch đặt máy) |
| `scripts/e2e/ui/people_flow.mjs` | **40/40** trên Edge thật (mục 14) |
| Hiệu năng | Danh mục v2 50 dự án 0,54–0,62 s; khối lượng công việc 6 tuần, 123 người 0,45–0,49 s; hiệu suất 4 tuần 0,17–0,30 s. Xem [HIEU_NANG.md](../HIEU_NANG.md#m9--khối-lượng-công-việc-hiệu-suất-danh-mục-v2-trên-50-dự-án-2026-11-11) |

Lỗi tìm ra khi chạy test và kịch bản, đã sửa:
- **Người tự xem bị dồn cả phần việc của người khác.** Khi kỹ sư mở trang của mình, chỉ các lượt giao của kỹ sư được đọc. Hệ thống không biết việc đã có tổ trưởng thực hiện, nên coi kỹ sư (người chịu trách nhiệm chính) là người gánh. Kết quả là kỹ sư thấy mình 217 %, trong khi quản lý xem cùng tuần đó thấy 0 %. Ảnh chụp điện thoại của kịch bản lộ ra lỗi này. Nay hệ thống đọc mọi người giữ các việc đó rồi mới chia; test và kịch bản kiểm hai cách xem cho cùng một số;
- **Mức chiếm thời gian bỏ trống bị hiểu là 0 %.** Trường phần trăm của Frappe lưu 0 khi để trống, nên mọi việc không ghi mức đều không được tính. Nay 0 hoặc trống là 100 %;
- **Ảnh chụp hiệu suất chưa theo phạm vi dự án.** `test_hook_coverage` bắt được: DocType mới có cột dự án mà chưa có hook phân quyền;
- **Tổ trưởng không thấy năng suất tổ mình khi xem được mọi dự án:** phạm vi đọc "tất cả" bị so như một tập rỗng (tìm ra khi đọc lại mã);
- script đo tạo 120 người bị Frappe chặn (giới hạn tạo người dùng mỗi giờ); chèn hàng loạt thành viên, lượt giao cần lấy mã từ sequence của DocType.

## 12. Hiệu năng

Xem bảng ở [HIEU_NANG.md](../HIEU_NANG.md#m9--khối-lượng-công-việc-hiệu-suất-danh-mục-v2-trên-50-dự-án-2026-11-11). Ngưỡng "dashboard 50 dự án < 2 s" đạt: 0,54–0,62 s.

## 13. Dữ liệu mẫu (bổ sung)

- **Nhà phố:** Phạm Giám Sát nghỉ phép ba ngày tuần sau. Bốn tuần trước được ghi ảnh chụp như thể job thứ Hai đã chạy.
- **Nhà xưởng:**
  - tổ trưởng Võ Tổ Trưởng thực hiện phần thân ở nhà phố và phần kết cấu ở nhà xưởng. Ông quá tải nhiều tuần, cao nhất khoảng 300 % tuần này, vì việc trễ của cả hai nơi dồn về; mỗi tuần như vậy là một xung đột người;
  - cần trục được nhà xưởng đặt cho cột (ngày +2 đến +8) và được nhà phố đặt cho mái (ngày +6 đến +10): ba ngày trùng là một xung đột máy;
  - năng suất của tổ nề (m3, 100m2) và tổ sắt (tấn) có từ nhật ký và chấm công sẵn có;
  - hai tuần trước được ghi ảnh chụp.

## 14. Tiêu chí hoàn thành

`people_flow.mjs` trên hai dữ liệu mẫu (ảnh trong `scripts/e2e/ui/out/people/`):
1. **Quản lý của cả hai dự án, máy tính**, trang Khối lượng công việc:
   - mở dưới 3 giây;
   - tổ trưởng quá tải, và tuần quá tải có việc của cả hai dự án;
   - xung đột người (tổ trưởng) và xung đột máy (cần trục, cả hai dự án);
   - ngăn bên của tuần đó liệt kê việc ở cả nhà phố và nhà xưởng;
   - quản lý không có ô ghi kỳ nghỉ.
2. **Quản trị** ghi nghỉ phép thứ Hai cho tổ trưởng: năng lực của tuần giảm đúng một ngày. Xóa kỳ nghỉ thì năng lực trở lại.
3. **Kỹ sư, điện thoại:**
   - trang khối lượng chỉ có chính mình, với đúng số mà quản lý thấy;
   - trang hiệu suất chỉ có chính mình; gọi xem hiệu suất của người khác bị từ chối (403);
   - không cuộn ngang.
4. **Tổ trưởng, điện thoại:** năng suất chỉ của tổ nề; năng suất = khối lượng / công; không cuộn ngang.
5. **Danh mục dự án** (quản lý):
   - mở dưới 2 giây;
   - nhà xưởng có người quá tải và cột chi phí / giá trị làm được;
   - có xu hướng tiến độ.
6. **Tab Máy:** lượt đặt cần trục hiện "Trùng lịch".

Không có lỗi JavaScript.

**Clone sạch** (xuất các tệp của repo, kể cả tệp chưa commit, bằng `git ls-files -co --exclude-standard`; cổng 8891, stack `pmclone` chạy song song với stack dev):
- bootstrap lần đầu: thoát mã 0;
- dữ liệu mẫu của lõi và lớp thi công dựng được:
  - kỳ nghỉ của Phạm Giám Sát;
  - 26 dòng ảnh chụp tuần;
  - 2 lượt đặt cần trục;
  - quản lý thấy Võ Tổ Trưởng quá tải, xung đột người và xung đột máy;
- site mới có:
  - index của PM Resource Capacity, PM Performance Snapshot, PMC Machine Booking;
  - trường `Task.pm_load_pct`;
  - 13 quy tắc cảnh báo, kể cả "Quá tải công việc";
  - ba hook mới của lớp thi công;
  - job thứ Hai `snapshot_week`;
- kịch bản trình duyệt: thí điểm 23/23, vật tư-máy-nhân công 33/33, M9 40/40, biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20;
- smoke 0 lỗi;
- test: `project_manager` 292 + 17, `pm_construction` 54/54;
- bootstrap lần nữa trên dữ liệu đã có: thoát mã 0, smoke 0 lỗi, cảnh báo và quy tắc còn nguyên;
- site thứ hai chỉ có ERPNext và lõi: `project_manager` 292 + 17, 10 quy tắc cảnh báo của lõi;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 15. Điểm cần chú ý khi duyệt

- **Mô hình "một người thực hiện = cả ngày".** Khi một tổ trưởng được giao "Thực hiện" thay cho cả tổ, hệ thống coi đó là việc của riêng ông. Trong dữ liệu mẫu vì vậy tổ trưởng quá tải đến 300 %. Muốn tính đúng thì giao việc cho cả đội (lượt giao cho đội không vào khối lượng của người nào), hoặc ghi mức chiếm thời gian nhỏ hơn.
- **Việc trễ dồn hết phần còn lại vào những ngày tới**, nên người có nhiều việc trễ sẽ quá tải rất cao ở tuần này. Đó là cảnh báo đúng (việc cần làm ngay), nhưng con số có thể làm người xem giật mình.
- **Chưa có lịch nghỉ riêng của từng người** ngoài các kỳ nghỉ phép, bán thời gian; ca làm, thứ Bảy làm nửa ngày cũng chưa có.
- **Cảnh báo quá tải gửi cho cả quản lý của các dự án liên quan.** Khi một người làm ở nhiều dự án, mỗi quản lý đều nhận; quản lý thấy phần của dự án khác dưới dạng "Dự án khác".
- **Ảnh chụp tuần chạy trực tiếp trong job theo lịch** (không qua hàng đợi `long` như lượt cảnh báo của M7): 50 dự án mất khoảng 3 s. Khi số dự án lớn hơn nhiều, nên chuyển sang hàng đợi `long`.
- **Năng suất tổ đội mới có ở lớp thi công.** Lõi chỉ có tỷ lệ đúng hạn, việc trễ, số lần báo tiến độ.

## 16. Việc tiếp theo

**M10 — Báo cáo, nhập/xuất, ngân sách, rủi ro, phát sinh:**
- báo cáo tiến độ, hiệu suất, vật tư, chi phí (CSV/XLSX/PDF, gửi theo lịch);
- nhập, xuất MS Project XML;
- ngân sách, EVM;
- sổ rủi ro và vấn đề; change request có duyệt;
- điểm mở rộng `project_close_handlers`.
