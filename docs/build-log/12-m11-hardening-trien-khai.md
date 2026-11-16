# M11 — Hardening và triển khai

## 1. Mục tiêu

Theo kế hoạch:
- volume check đầy đủ (mục 12); load test 200 người cập nhật tiến độ đồng thời;
- rà soát bảo mật: liệt kê endpoint theo từng role; XSS (Jinja autoescape, `inline_json`); upload;
- triển khai prod qua `prod_compose.py`; diễn tập sao lưu và khôi phục sang máy khác;
- tài liệu: README, DEPLOYMENT, HIEU_NANG, hướng dẫn sử dụng.

## 2. Quy mô đầy đủ

`scripts/perf/volume_check.py` có thêm hai bước:
- `extra`: 5 triệu trao đổi, 2 triệu ảnh (chỉ dữ liệu), 100 nghìn phiếu kho, 500 người (mỗi người là Kỹ sư của 3 dự án đang chạy), một phần mười số việc của các dự án đang chạy đã quá hạn. Chèn bằng SQL theo lô 5.000 dòng với id định trước, rồi đặt lại sequence của bảng autoincrement;
- `measure` có thêm phần M11: các ngưỡng của mục 12, cộng báo cáo, khối lượng công việc, phiếu kho của thủ kho.

Mọi ngưỡng đạt. Số liệu: [HIEU_NANG.md](../HIEU_NANG.md#m11--quy-mô-đầy-đủ-và-200-người-cùng-lúc-2026-11-16).

**Danh mục dự án** lần đo đầu mất 1,93–2,29 s cho 50 dự án, sát ngưỡng 2 s. Ba chỗ đã sửa:
- `schedule.targets` (mới) lấy ngày đích và độ trễ dự báo của mọi dự án bằng vài truy vấn. Trước đây `schedule.summary` chạy riêng cho từng dự án và đếm cả những số danh mục không dùng. Lịch nghỉ (`workdays.calendars_of`) và đường cong baseline (`baseline.curves_of`) cũng đọc một lần cho mọi dự án;
- index `(pm_is_overdue, project)` trên Task cho việc đếm việc quá hạn (từ 0,46 s xuống 69 ms);
- cột chi phí / giá trị làm được của lớp thi công: tổng của từng dự án giữ 10 phút trong Redis (`costs.totals`); `costs.refresh`, `quantities.refresh` và việc áp BOQ (đơn giá) bỏ tổng của dự án ngay khi số liệu đổi.

Sau khi sửa: 0,87 s khi cache trống, 0,12 s các lần sau.

## 3. Rà soát bảo mật (`tests/test_security.py`)

Test liệt kê mọi endpoint (`@frappe.whitelist`) của lõi và của các lớp ngành đang cài. Lớp ngành được tìm qua `required_apps`, nên lõi không nhắc tên lớp thi công. Bốn nhóm kiểm:

1. **Không endpoint nào mở cho khách** (`allow_guest`).
2. **Endpoint ghi chỉ nhận POST.** Một endpoint có tên bắt đầu bằng động từ ghi (save, create, approve, book, upload…) mà nhận GET thì một thẻ ảnh hay một liên kết cũng kích hoạt được. Ngoại lệ có ghi rõ: `wbs.import_template` (tải tệp mẫu trống).
3. **Tài khoản ngoài nhân viên bị từ chối ở mọi endpoint:** một Website User và một tài khoản chỉ có vai trò ERPNext ("Accounts User"). Mỗi endpoint được gọi với tham số giả; nó phải báo PermissionError trước khi làm gì khác. Ngoại lệ là ba endpoint chỉ đụng tới tài khoản của chính người gọi (đổi mật khẩu, đọc và đánh dấu thông báo của mình).
4. **Escape và tệp tải lên:**
   - trang in báo cáo escape những gì người dùng gõ (tiêu đề, ô, bộ lọc);
   - `inline_json` không đóng được thẻ `<script>`;
   - tài liệu từ chối html, svg, xhtml, script, tệp chạy được; tên tệp bỏ phần đường dẫn;
   - ảnh nhận theo nội dung (JPEG, PNG, WebP), không theo tên;
   - chỉ PDF và ảnh được mở ngay trong trình duyệt. Mọi loại khác là tệp tải về, kèm `nosniff`.

**Lỗ hổng tìm được:** `site.machine_book` và `site.machine_booking_cancel` của lớp thi công thiếu `assert_staff()`. Một tài khoản ngoài nhân viên tới được hàm dịch vụ; quyền theo dự án ở đó vẫn chặn, nhưng cổng nhân viên phải đứng trước. Đã thêm.

Các phần đã có từ trước và được rà lại:
- quyền theo dự án trên mọi DocType có cột `project` (`test_hook_coverage`);
- tìm kiếm lọc theo phạm vi ở server; tệp tải qua API sau khi kiểm quyền, từ MinIO;
- Jinja của Frappe v16 không tự escape: các mẫu của repo dùng `| e` hoặc `{% autoescape true %}` (DEV_WORKFLOW, mục Lưu ý).

## 4. Triển khai prod

| File | Nội dung |
|---|---|
| `docker/docker-compose.prod.yml` | Overlay prod: image `pm-custom` build trên máy chủ, hoặc image CI (`PM_IMAGE`, `PM_IMAGE_TAG`); `restart: always`; giới hạn bộ nhớ theo biến; chỉ nginx được publish, và chỉ ở `127.0.0.1` |
| `docker/docker-compose.prod.bind.yml` | Tùy chọn: dữ liệu ở thư mục của máy chủ (`DATA_ROOT`) thay cho volume của Docker |
| `docker/.env.prod.example` | Mẫu cấu hình; các mật khẩu để trống |
| `scripts/validate_prod_env.py` | Kiểm `.env.prod`: tên miền thật và `PUBLIC_URL=https://…`; cổng chỉ ở `127.0.0.1`; mật khẩu từ 24 ký tự, khác nhau, không trùng bản dev; tiền tố volume và tên stack khác bản dev; `DATA_ROOT` tuyệt đối và nằm ngoài mã nguồn; đủ thông tin công ty; chmod 600 (trên POSIX). `PM_REHEARSAL=1` cho phép tên `*.test` qua http |
| `scripts/prod_compose.py` | Mọi lệnh `docker compose` của prod: kiểm `.env.prod`, rồi thêm các overlay |
| `scripts/deploy_prod.sh` | Triển khai lần đầu và nâng cấp: sinh mật khẩu còn trống, kiểm, tạo thư mục dữ liệu, sao lưu trước nếu có `--backup`, build hoặc kéo image, khởi động hạ tầng, tạo site, setup wizard, migrate, khởi động mọi dịch vụ, chờ site trả lời |
| `scripts/backup.sh`, `scripts/restore.sh` | Mục 6 |
| `scripts/ci/test_validate_prod_env.py` | 7 test của trình kiểm, chạy ở job `static` của CI |
| `.github/workflows/ci.yml` | Job `static`: các test trên, `bash -n` cho bốn script, `docker compose config` của overlay prod và overlay bind |

Tài liệu: [DEPLOYMENT.md](../DEPLOYMENT.md) (máy chủ, chuẩn bị, triển khai, HTTPS với Caddy hoặc nginx, sau khi triển khai, vận hành, nâng cấp và quy trình nâng cấp ERPNext, diễn tập).

### Diễn tập prod trên máy này

Máy Windows 11, Docker Desktop (8 GB RAM, 12 nhân), Git Bash; stack dev tắt trong lúc diễn tập. Chưa có máy chủ Linux và tên miền thật, nên dùng chế độ diễn tập (`PM_REHEARSAL=1`, site `duan.test` qua http).

1. **Chuẩn bị.** Xuất repo sang thư mục mới (`git ls-files -co --exclude-standard`; không có `docker/.env`). Tạo `docker/.env.prod` từ mẫu: stack `pmprodtest`, cổng `127.0.0.1:8892`, site `duan.test`, công ty "Công ty Diễn tập". Mật khẩu để trống.
2. **Trình kiểm.** Không có `PM_REHEARSAL`, nó từ chối tên `.test`, `http://` và mật khẩu trống. Có `PM_REHEARSAL`, nó chỉ còn từ chối mật khẩu trống.
3. **Triển khai lần đầu:** `deploy_prod.sh` sinh 5 mật khẩu, build image, tạo site, chạy setup wizard, khởi động: **4 phút 40 giây**, thoát mã 0. Các lớp image đã có trong cache từ các lần build dev; trên máy chủ mới, lần build đầu mất khoảng 10–15 phút.
4. **Kiểm sau triển khai:**
   - chỉ nginx được publish, ở `127.0.0.1:8892`; MariaDB, Redis, Meilisearch, MinIO chỉ ở mạng nội bộ;
   - `restart: always`; giới hạn bộ nhớ backend 3 GB, db 3 GB, frontend 512 MB;
   - smoke (`PM_ENV_FILE=docker/.env.prod`): 0 lỗi.
5. **Dữ liệu mẫu** của lõi và lớp thi công: 16 giây.
6. **Đo tải** (mục 5).
7. **Nâng cấp:** chép bản sửa lỗi xếp job vào, rồi `deploy_prod.sh --backup`. Sao lưu trước (1,6 MB, 6 đối tượng MinIO), build image mới, migrate, khởi động lại: **5 phút 21 giây**, smoke 0 lỗi. Lần chạy đầu của bước này tìm ra lỗi đường dẫn của `backup.sh` trên Windows (mục 7).

## 5. Đo tải 200 người

`scripts/perf/load_progress.py`, chạy trong container backend của bản diễn tập, gửi yêu cầu qua nginx (`http://frontend:8080`):
- dự án tạm 4 giai đoạn × 5 hạng mục × 10 công tác. Mỗi hạng mục có 10 người cùng báo, nên một node cha bị cộng dồn từ nhiều yêu cầu cùng lúc;
- 200 người tạm: mỗi người là Kỹ sư của dự án và là người thực hiện một công tác (đã nhận việc). Mật khẩu ngẫu nhiên, không in ra;
- mỗi người đăng nhập thật và lấy CSRF token. Mọi người chờ ở một barrier rồi cùng gửi `tasks.report`, 3 vòng (30 %, 60 %, 90 %), mỗi lần có `client_uuid`;
- kiểm:
  - không có câu trả lời lỗi;
  - đủ 600 PM Progress Entry;
  - mọi công tác ở 90 %;
  - không có deadlock trong Error Log;
  - khi hàng đợi `pm` xong, tiến độ dự án bằng kết quả tính lại toàn cây (`rollup.reconcile` không sửa node nào).
  
  Dữ liệu tạm được dọn khi xong.

Cấu hình: gunicorn 4 tiến trình × 4 luồng (mặc định của `.env.prod`), một worker `queue-pm`.

| Lần | Thời gian (600 yêu cầu) | Trung vị / p95 / lớn nhất | Lỗi | Dữ liệu |
|---|---|---|---|---|
| 1 (trước khi sửa) | 17,5 s | 3,0 / 4,4 / 4,7 s | **1** (HTTP 500, mục 7) | 600/600, 0 deadlock, cộng dồn đúng |
| 2, 3, 4 (sau khi sửa) | 16,6–18,5 s (khoảng 35 yêu cầu/s) | 2,9–3,1 / 4,1–4,7 / 4,4–5,0 s | 0 | 600/600, mọi công tác ở 90 %, 0 deadlock, tính lại toàn cây đổi 0 node |

Ngưỡng của kế hoạch ("không deadlock, không mất dữ liệu") đạt. Thời gian chờ vài giây là do 200 yêu cầu đến cùng một lúc vào 16 luồng, nên phải xếp hàng. Một lần báo tiến độ chỉ tốn khoảng 34 ms ở server (mục 2). Thực tế 200 người hiếm khi bấm trong cùng một giây; máy chủ nhiều nhân hơn thì tăng `GUNICORN_WORKERS`.

## 6. Diễn tập sao lưu và khôi phục

**Sao lưu** (`scripts/backup.sh`) gồm:
- `bench backup --with-files`: CSDL, tệp công khai và riêng tư, cấu hình site (có khóa mã hóa);
- bucket MinIO, chép bằng `mc mirror` (chạy trong container `minio-init`);
- `MANIFEST.txt`: tên site, thời điểm, phiên bản mã, số đối tượng, SHA-256 từng tệp.

**Khôi phục** (`scripts/restore.sh`) làm lần lượt:
1. kiểm manifest: phải có, tên site phải trùng, SHA-256 phải khớp;
2. `bench restore` (mật khẩu root của CSDL đi qua biến môi trường, không lên dòng lệnh);
3. đặt lại khóa mã hóa cũ;
4. chép lại bucket;
5. migrate, dựng lại chỉ mục tìm kiếm, khởi động lại.

Cách dùng: [SAO_LUU_KHOI_PHUC.md](../SAO_LUU_KHOI_PHUC.md).

**Diễn tập** (cùng máy Windows, hai stack không dùng chung gì):

1. **Nguồn:** bản diễn tập prod `pmprodtest` (mục 4), có dữ liệu mẫu, sau các lần đo tải. Ghi thêm một giá trị mã hóa bằng khóa của site (giá trị thử, không phải mật khẩu thật) để kiểm khóa mã hóa đi theo.
2. **Ghi 28 dữ kiện của nguồn:**
   - số dòng của 19 DocType;
   - tiến độ của hai dự án mẫu;
   - SHA-256 của từng đối tượng MinIO, đọc qua ứng dụng (6 đối tượng: ảnh, ảnh nhỏ, tài liệu);
   - mã băm của khóa mã hóa; giá trị mã hóa có giải được không;
   - số mục trong chỉ mục tìm kiếm; kết quả một lần tìm.
3. **Sao lưu:** `backup.sh --prod`, **10,5 giây, 2,1 MB**.
4. **Thử đường lỗi:** dừng stack nguồn rồi sao lưu. Script thoát mã 1 và xóa thư mục dở dang.
5. **"Máy khác":** stack thứ hai `pmrestore`, xuất repo sang thư mục mới, `.env.prod` riêng (mật khẩu khác, cổng 8893, cùng tên site). `deploy_prod.sh`: 2 phút 45 giây (image đã có trong cache). Chỉ chép thư mục sao lưu sang.
6. **Thử từ chối:** manifest ghi site khác thì từ chối; thư mục không có manifest thì từ chối. Cả hai trước khi đụng vào dữ liệu.
7. **Khôi phục:** `restore.sh --prod`: **65 giây**. Cả **28 dữ kiện trùng khớp**:
   - số dòng, tiến độ;
   - 6 đối tượng MinIO giống từng byte;
   - giá trị mã hóa vẫn giải được bằng khóa cũ;
   - chỉ mục tìm kiếm dựng lại đủ 6/6 mục, lần tìm cho cùng kết quả.
8. **Đăng nhập:** dữ liệu khôi phục giữ mật khẩu Administrator của máy cũ. Smoke với mật khẩu của máy mới: 12 lỗi (đúng như tài liệu nói). Sau `set-admin-password` (mật khẩu đi qua biến môi trường): 0 lỗi.
9. **Trình duyệt trên bản khôi phục:**
   - `discussion_flow.mjs` 27/27: ảnh, tệp, tìm kiếm;
   - `pilot_flow.mjs` 13 đạt, 3 không: thiếu cảnh báo "Thiếu nhật ký thi công". Nguồn cũng không có cảnh báo này: dữ liệu mẫu được dựng hôm thứ Hai, và dữ liệu mẫu bỏ nhật ký của "hôm qua" là Chủ nhật, ngày nghỉ, nên quy tắc (xét ngày làm việc gần nhất là thứ Bảy) không báo. Đã sửa dữ liệu mẫu: bỏ nhật ký của ngày làm việc gần nhất theo lịch của dự án. Clone sạch kiểm lại (mục 11).
10. Gỡ cả hai stack (`down -v`), xóa hai thư mục.

Với dữ liệu cỡ này, thời gian khôi phục sang máy mới là 3–5 phút cài đặt (image có sẵn) cộng khoảng 1 phút khôi phục.

## 7. Lỗi tìm ra trong M11, đã sửa

**Từ đo tải:**
- **Một lần báo tiến độ đã lưu nhưng trả về lỗi 500** (1 trong 600). Sau khi commit, việc xếp job cộng dồn gọi `frappe.enqueue(deduplicate=True)`. Khi job trước vừa xong, Frappe xóa nó để xếp lại; đúng lúc worker đang dọn, RQ báo "Execution … not found in Redis". Lỗi nổ trong `after_commit`, nên người dùng thấy trang lỗi dù dữ liệu đã lưu. Nay `jobs.enqueue_once` không bao giờ báo lỗi: tự xem trạng thái job, thử lại một lần, rồi để bộ quét 5 phút làm nốt (tập "cần tính lại" vẫn còn nguyên trong Redis).
- **Mỗi lần trùng job, Frappe ghi một dòng lỗi vào `frappe.log`** ("Not queueing job … because it is in queue already"): khoảng 3.000 dòng cho một lần đo 600 lần báo. Tệp log xoay vòng liên tục, và bốn tiến trình gunicorn xoay cùng một tệp thì va nhau (`FileNotFoundError` trong `doRollover`). Nay job đang chờ thì không gọi `frappe.enqueue` nữa: còn 10–23 dòng mỗi lần đo (hai yêu cầu cùng xem trạng thái đúng một lúc, vô hại).
- **Chạy đo tải nhiều lần liền nhau thì Frappe từ chối xếp job** (`QueueOverloaded`, quá 500 job). Đây là job của chính Frappe khi tạo và xóa 200 tài khoản (`create_contact`, `delete_dynamic_links`, khoảng 3 job mỗi giây), không phải của việc báo tiến độ. Script đo nay chờ hàng đợi vơi rồi mới chạy, và dọn phần còn sót của một lần chạy bị ngắt.

**Từ diễn tập prod:**
- **`backup.sh --prod` và `restore.sh --prod` không chạy trên Windows:** script gọi `python <đường dẫn Git Bash>/scripts/prod_compose.py`; khi đặt `MSYS_NO_PATHCONV=1`, Python của Windows đọc `/d/...` thành `D:\d\...`. Nay gọi bằng đường dẫn tương đối từ gốc repo, như `deploy_prod.sh`.
- **Sao lưu thất bại để lại một thư mục dở dang** trông như bản sao lưu. Nay `backup.sh` xóa thư mục nó đã tạo khi thất bại, ghi `MANIFEST.txt` sau cùng (qua tệp tạm), và `restore.sh` từ chối thư mục không có `MANIFEST.txt`.

**Từ đo quy mô, rà soát bảo mật:**
- danh mục dự án sát ngưỡng 2 s ở 50 dự án, 300.000 việc (mục 2);
- đặt, hủy đặt máy thiếu cổng nhân viên (mục 3);
- `test_escalation_climbs_its_steps` đếm số cảnh báo leo thang của cả site, nên hỏng trên site có dữ liệu mẫu đã cũ vài ngày. Nay test chỉ xem cảnh báo của nó;
- `volume_check.py`: phép đo cộng dồn cũ không đo gì (cộng dồn chỉ chạy sau commit), nay gọi `rollup.recompute`; danh sách phiếu kho đo bằng một thủ kho (ERPNext đòi Stock User).

## 8. File chính

| File | Nội dung |
|---|---|
| Lõi `services/schedule.py` (`targets`, `_slip`), `baseline.py` (`curves_of`), `workdays.py` (`calendars_of`, `calendar_named`), `portfolio.py`, `setup/install.py` (index) | Danh mục dự án ở quy mô đầy đủ |
| Lõi `services/jobs.py` | Xếp job sau khi commit không bao giờ báo lỗi (mục 7) |
| Lõi `tests/test_security.py` (mới); `test_rollup.py`, `test_schedule.py`, `test_alerts.py` (bổ sung, sửa) | Kiểm thử |
| Lớp `services/costs.py` (`totals`, `forget_totals`), `people.py`, `quantities.py`; `api/site.py` (`assert_staff`) | Cột chi phí của danh mục; cổng nhân viên |
| `docker/docker-compose.prod.yml`, `.prod.bind.yml`, `.env.prod.example` | Prod |
| `scripts/validate_prod_env.py`, `prod_compose.py`, `deploy_prod.sh`, `backup.sh`, `restore.sh` | Prod, sao lưu, khôi phục |
| `scripts/perf/volume_check.py` (`extra`, `measure_m11`), `scripts/perf/load_progress.py` (mới) | Đo |
| `scripts/ci/test_validate_prod_env.py`, `check_repo.py` (biến của compose prod), `.github/workflows/ci.yml` | CI |
| `scripts/e2e/smoke_http.py` (`PM_ENV_FILE`) | Smoke cho bản prod |
| `.gitignore` (`backups/`), `.dockerignore` (`docker/.env.prod`) | |
| `README.md`, `docs/DEPLOYMENT.md`, `SAO_LUU_KHOI_PHUC.md`, `HUONG_DAN_SU_DUNG.md` (mới), `HIEU_NANG.md`, `DEV_WORKFLOW.md`, `NGUON_GOC.md`, `TRACEABILITY.md` | Tài liệu |

## 9. Mã sao chép

`validate_prod_env.py`, `prod_compose.py` và overlay prod sao chép từ `document_manager` rồi sửa. Chi tiết ở [NGUON_GOC.md](../NGUON_GOC.md#m11).

## 10. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **317 + 17** (trước M11: 306 + 17). Thêm `test_security`, 9 bài: 202 endpoint (lõi 163, lớp thi công 39), không cái nào mở cho khách; 113 endpoint chỉ nhận POST, trong đó có mọi endpoint có tên bắt đầu bằng động từ ghi; Website User và tài khoản chỉ có ERPNext bị từ chối ở mọi endpoint; escape của trang in và `inline_json`; ba bài về tệp tải lên. `test_rollup` thêm 2 bài: job đang chờ không xếp lại; lỗi xếp job sau commit không làm hỏng yêu cầu. `test_schedule`: `schedule.targets` khớp `summary`. `test_alerts`: bài leo thang không đếm cảnh báo của cả site |
| `run-tests --app pm_construction` | **58/58** (trước: 57). Thêm: tổng chi phí giữ trong cache tới khi chi phí đổi |
| vitest | **221/221** (M11 không đổi giao diện) |
| `scripts/ci/test_validate_prod_env.py` | **7/7**: tệp đủ thì qua; tên miền thật và https; cổng chỉ ở `127.0.0.1`; mật khẩu mạnh và khác nhau; khác bản dev; công ty, image; `DATA_ROOT` |
| `check_repo.py` | 0 lỗi (biến của compose prod có trong `.env.prod.example`) |
| `bash -n` bốn script; `docker compose config` của overlay prod, overlay bind | Đạt (cũng chạy ở job `static` của CI) |
| Quy mô đầy đủ | Mọi ngưỡng của mục 12 đạt (mục 2) |
| Đo tải 200 người | 3 lần liền 0 lỗi, 0 deadlock, 600/600, cộng dồn đúng (mục 5) |
| Diễn tập prod, nâng cấp, sao lưu, khôi phục | Mục 4, 6 |

## 11. Tiêu chí hoàn thành

Theo kế hoạch:

| Tiêu chí | Kết quả |
|---|---|
| Volume check đầy đủ, ngưỡng của mục 12 | Đạt (mục 2, [HIEU_NANG.md](../HIEU_NANG.md#m11--quy-mô-đầy-đủ-và-200-người-cùng-lúc-2026-11-16)) |
| 200 người cập nhật tiến độ đồng thời: không deadlock, không mất dữ liệu | Đạt, 3 lần liền (mục 5) |
| Rà soát bảo mật: endpoint theo role, XSS, upload | `test_security`; một lỗ hổng đã vá (mục 3) |
| Triển khai prod qua `prod_compose.py` | Diễn tập: triển khai, kiểm, nâng cấp có sao lưu (mục 4) |
| Sao lưu và khôi phục sang máy khác | Diễn tập: 28/28 dữ kiện trùng khớp (mục 6) |
| README, DEPLOYMENT, HIEU_NANG, hướng dẫn sử dụng | Có, cộng `SAO_LUU_KHOI_PHUC.md` |

**Clone sạch.** Xuất các tệp của repo, kể cả tệp chưa commit, bằng `git ls-files -co --exclude-standard`. Cổng 8891, stack `pmclone`, chạy song song với stack dev.
- bootstrap lần đầu (`bootstrap.ps1`): thoát mã 0;
- **test chạy trước dữ liệu mẫu**, trên site mới: `project_manager` 317 + 17, `pm_construction` 58/58;
- dữ liệu mẫu của lõi và lớp thi công dựng được, và hôm nay (thứ Hai) có cảnh báo "Thiếu nhật ký thi công" cho thứ Bảy 14/11. Đây là bản sửa ở mục 6;
- site mới có index `(pm_is_overdue, project)` trên Task và 14 quy tắc cảnh báo; danh mục dự án có ngày đích, độ trễ dự báo, cột chi phí và vượt định mức của lớp thi công;
- smoke 0 lỗi;
- kịch bản trình duyệt: thí điểm 23/23, vật tư-máy-nhân công 33/33, khối lượng-hiệu suất 40/40, kiểm soát dự án 37/37, biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20;
- bootstrap lần nữa trên dữ liệu đã có: chạy hết, không lỗi, smoke 0 lỗi, cảnh báo (15) và quy tắc (14) còn nguyên;
- site thứ hai chỉ có ERPNext và lõi: `project_manager` 317 + 17, 11 quy tắc cảnh báo của lõi;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 12. Điểm cần chú ý khi duyệt

- **Diễn tập prod chạy trên Windows với Docker Desktop**, chưa phải một máy chủ Linux có tên miền và TLS thật. Những phần chưa chạy thật:
  - cấu hình Caddy, nginx ở DEPLOYMENT mục 4;
  - overlay bind (`DATA_ROOT`) và `chown` cho uid 1000: chỉ được kiểm bằng `docker compose config` ở CI, vì bind mount trên Windows không giống Linux;
  - dùng image của CI (`PM_IMAGE`): diễn tập build image tại chỗ;
  - PWA và hàng đợi gửi lại khi mất mạng: cần HTTPS, đã kiểm ở M5 trên `localhost`.
  
  Nên chạy lại `deploy_prod.sh` và một lần khôi phục trên máy chủ thật trước khi đưa vào dùng.
- **Thời gian trả lời khi 200 người bấm cùng một giây** là 3–5 giây: yêu cầu xếp hàng vào 16 luồng gunicorn. Không mất, không lỗi, nhưng máy chủ có nhiều nhân hơn nên tăng `GUNICORN_WORKERS`.
- **Tổng chi phí trên danh mục dự án có thể cũ tới 10 phút** nếu số liệu đổi ngoài các đường của ứng dụng (sửa thẳng CSDL, nhập dữ liệu). Mọi đường trong ứng dụng (chi phí, khối lượng, BOQ) bỏ cache ngay. Màn chi phí của từng dự án luôn đọc số liệu mới.
- **Đối soát cộng dồn hằng đêm** tốn khoảng 2,5 s cho một dự án 6.000 việc, nên khoảng 2 phút cho 50 dự án như vậy. Chạy ở hàng đợi `long`.
- **Khôi phục phải cùng tên site**, vì khóa của ảnh và tài liệu trên MinIO gắn với tên site. `restore.sh` kiểm điều này. Đổi tên miền sau này cần một bước chuyển khóa MinIO (chưa có).
- **Mật khẩu Administrator sau khôi phục là của máy cũ.** Tài liệu ghi rõ, kèm lệnh đặt lại.
- **Log của Frappe:** bốn tiến trình gunicorn cùng xoay một tệp `frappe.log` thì đôi khi va nhau (`FileNotFoundError` trong `doRollover`). Lỗi này của Frappe, chỉ làm mất vài dòng log, không ảnh hưởng yêu cầu. M11 bỏ được gần hết dòng lỗi do trùng job, nên tệp log xoay ít hơn hẳn.
- **Trong lúc dọn diễn tập**, lệnh `down --rmi local` cũng gỡ tag của image `pm-custom:v16.26.2` và `pm-minio-mc` mà stack dev dùng chung tên. Container dev vẫn chạy được; clone sạch build lại image cùng tag. Tài liệu không dùng `--rmi`.
