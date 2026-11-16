# Nguồn gốc mã sao chép

Một phần hạ tầng và mẫu code được **sao chép** từ dự án `document_manager` (repo `darkside136317/document-manager-project`) trong lúc xây dựng. Bản sao đã trở thành mã của repo này: repo này không import, không dùng submodule, không cài gói và không dùng chung image, container, network hay volume với `document_manager`.

| File ở repo này | Nguồn | Thay đổi so với nguồn |
|---|---|---|
| `docker/Dockerfile` | `docker/Dockerfile` | Node 24.22.2 thay Node 20 (hết hỗ trợ); hai app; bỏ Tesseract/poppler/libmagic (chưa cần OCR); image `pm-custom` |
| `docker/docker-compose.yml` | `docker/docker-compose.yml` | Bỏ MongoDB/PDFluent; thêm `setup-site` (setup wizard từ `.env`), worker `queue-pm`, cấu hình queue `pm`, `PM_INSTALL_APPS`; ghim `mariadb:11.8.6`, `redis:7.4.9-alpine`, `meilisearch:v1.12.8`; tiền tố volume `pm` |
| `docker/docker-compose.local.yml` | — | Mới: chỉ mở port, chạy image đã build (mặc định của bootstrap) |
| `docker/docker-compose.dev.yml` | `docker/docker-compose.dev.yml` | Mount hai app; `spa-watch` thay `staff-ui`; port dev 8890/7701 |
| `docker/mariadb/my_custom.cnf` | `docker/mariadb/my_custom.cnf` | Giữ nguyên các tham số, bỏ phần binlog đã comment |
| `docker/dev/watcher.py`, `docker/dev/autoreload.py` | cùng tên | Theo dõi nhiều app (`PM_APP_DIRS`) |
| `.gitattributes`, `.dockerignore`, `.gitignore` | cùng tên | Đổi đường dẫn; thêm `*.xlsx`, `*.docx` nhị phân |
| `apps/project_manager/project_manager/www/pm.py`, `pm.html` | `www/dashboard.py`, `dashboard.html` | Trang chủ SPA `/pm`, boot data rút gọn, chặn khách và Website User |
| `apps/project_manager/project_manager/project_manager/services/web.py` | `services/web.py` | **Sửa lỗi**: bản gốc viết `"\u003c"` — trong chuỗi Python thường đó chính là `"<"`, nên không escape được (nguy cơ XSS). Bản này dùng `"\\u003c"` và có test |
| `apps/project_manager/frontend/vite.config.js` | `frontend/vite.config.js` | Ra `public/spa`, biến `PM_WATCH_POLL` |
| `.github/workflows/ci.yml` | `.github/workflows/ci.yml` | Thêm job lõi chạy một mình, job clean clone, kiểm tra quy tắc repo |

Không sao chép: `docker/.env.dev` của `document_manager` (đang bị commit và chứa secret), các `Dockerfile.*-overlay` (vá nóng một lần triển khai), MongoDB/GridFS, PDFluent.

## M1

| File ở repo này | Nguồn (`document_manager/document_manager/document_manager/...`) | Thay đổi so với nguồn |
|---|---|---|
| `policy.py` | `policy.py` | Phạm vi theo **dự án** (thành viên + PM Access + PM Group) thay cho phông; thêm vai trò trong dự án (`capabilities_in`); bỏ độc giả, mức mật, chế độ xem độc giả |
| `permissions.py` | `permissions.py` | Bộ điều hợp chung theo cột `project`; bỏ phần độc giả, trạng thái công bố |
| `constants.py` | `constants.py` | Viết lại: nhóm quyền, capabilities, vai trò dự án, loại nút, màn hình |
| `services/errors.py`, `services/queries.py` | cùng tên | Giữ nguyên (đổi câu thông báo) |
| `services/permission_matrix.py` | cùng tên | Đổi import và biến cache |
| `services/audit.py` | cùng tên | Ghi `PM Audit Log`, thiết lập `PM Settings`; thêm `purge_expired` hằng ngày |
| `services/notify.py`, `services/health.py` | cùng tên | Giữ phần chung; health kiểm Meilisearch và job Overdue của ERPNext |
| `services/ui.py` | cùng tên | Bỏ chế độ số hóa và từ điển gợi ý |
| `setup/install.py` (`ensure_single_defaults`) | `setup/install.py` | Kiểm dòng `tabSingles` thay vì giá trị (ô Check chưa lưu đọc ra 0) |
| `api/crud.py`, `api/meta.py`, `api/boot.py`, `api/users.py`, `api/permissions.py`, `api/logs.py`, `api/admin.py`, `api/account.py` | cùng tên | Bỏ phần lưu trữ; phạm vi theo dự án trong `users.py`; liên kết đặt mật khẩu dùng `/update-password` của Frappe |
| DocType PM Role Profile/Capability, PM Group (+Member, Role), PM Access (+Project), PM Settings, PM Audit Log | Staff Role Profile/Capability, Staff Group, Staff Access, Document Manager Settings, Business Activity Log | Tiền tố `PM`, phạm vi theo dự án |
| `frontend/src/components/*`, `lib/*`, `pages/{MasterList,MasterPage,MasterTree,UsersPage,RolesPage,LogsPage,MonitorPage,SettingsPage,NotFound,ForbiddenPage}.vue`, `styles/` | `frontend/src/...` | Tiền tố `--pm-`, `/pm`, `__PM_BOOT__`; bỏ số hóa, độc giả, phiếu, tìm kiếm lưu trữ; `ProjectPicker` thay `FondsPicker`; viết lại `api.js`, `boot.js`, `router.js`, `DashboardHome.vue`, `MonitorPage.vue` |
| `frontend/tests/{admin,api,components,lib,permissions}.test.js` | `frontend/tests/` | Dữ liệu và kỳ vọng theo phạm vi dự án |

## M2

Không sao chép thêm từ `document_manager`. Các dịch vụ (giao việc, tiến độ, rollup, cây WBS, mẫu dự án, nhập Excel), các màn hình (Dự án, Kanban, Ai làm gì, Việc của tôi, chi tiết công việc) và biểu đồ đường cong S đều viết mới.

## M3

Không sao chép thêm từ `document_manager`. Biểu mẫu động, bản in, chữ ký và kịch bản Playwright đều viết mới.

## M4

Không sao chép thêm từ `document_manager`. `GanttChart.vue` phát triển từ `spikes/gantt/src/CanvasView.vue` của chính repo này (spike ở M1). Đường găng, dự báo, baseline, lịch và các tab đều viết mới.

## M5

| File | Nguồn | Xử lý |
|---|---|---|
| `services/object_storage.py` | `document_manager/services/object_storage.py` | Sao chép rồi sửa: cấu hình từ `common_site_config`, ba loại đối tượng (ảnh, ảnh nhỏ, tài liệu), đọc từng khúc, dọn đối tượng mồ côi, kho trong bộ nhớ cho test |
| `services/search_index.py` | `document_manager/services/search_index.py` | Sao chép cách tạo client và cấu hình chỉ mục; phần dữ liệu, lọc quyền, đối soát viết mới |
| `docker/minio/Dockerfile.server`, `Dockerfile.mc` | `document_manager/docker/minio/` | Sao chép (cùng bản phát hành); thêm `curl` để healthcheck. Chính sách quyền của ứng dụng sinh trong `minio-init` theo tên bucket |

Phần còn lại (dòng thời gian, ảnh, tài liệu, hàng đợi gửi lại, service worker, realtime) viết mới.

## M6

Không sao chép thêm từ `document_manager`. Lớp thi công (`apps/pm_construction`) và các điểm mở rộng của lõi (`extensions.py`, `frontend/src/modules.js`, `services/jobs.py`) đều viết mới. BOQ mẫu (`services/boq_import.SAMPLE`) là số liệu minh họa, mã hiệu theo cách đánh mã định mức thông dụng, đơn giá không lấy từ bộ đơn giá nào.

## M7

Không sao chép thêm từ `document_manager`. Cảnh báo, sức khỏe, chuyển giai đoạn, tóm tắt, danh mục dự án (`services/alerts.py`, `risk.py`, `phases.py`, `digest.py`, `portfolio.py`) và các màn hình của chúng đều viết mới. Thông báo trong ứng dụng vẫn đi qua `services/notify.py` (sao chép từ M1).

## M8

Không sao chép thêm từ `document_manager`. Vật tư, máy, nhân công, chi phí (`pm_construction/services/materials.py`, `machines.py`, `labour.py`, `costs.py`) và phạm vi kho của lõi (`permissions.stock_query`) đều viết mới, trên các DocType kho, mua hàng, tài sản của ERPNext. Định mức và đơn giá của dữ liệu mẫu (`setup/demo_site.py`) là số minh họa, không lấy từ bộ định mức hay bảng giá nào.

## M9

Không sao chép thêm từ `document_manager`. Khối lượng công việc, hiệu suất, danh mục dự án v2, đặt máy đều viết mới.

## M10

| File ở repo này | Nguồn (`document_manager/...`) | Thay đổi so với nguồn |
|---|---|---|
| `project_manager/services/reports/base.py` | `document_manager/services/reports/base.py` | Phạm vi theo dự án (`Where.project_scope`) thay cho phông và mức mật; `may_run` thay cho danh sách DocType phải đọc được; thêm `order`; cột tiền (Currency) |
| `project_manager/services/reports/__init__.py` | `document_manager/services/reports/__init__.py` | Báo cáo của lớp ngành qua hook `pm_reports`; bộ lọc bắt buộc |
| `project_manager/services/reports/output.py` | `document_manager/services/reports/output.py` | Đầu trang là Company mặc định của ERPNext (không có Organization Info); cột tiền; `to_pdf` dùng chung cho gửi theo lịch |
| `project_manager/api/reports.py` | `document_manager/api/reports.py` | Cổng nhân viên của repo này; thêm các API gửi theo lịch |
| `project_manager/templates/pm_report_print.html` | `document_manager/templates/reports/report_print.html` | Đổi chữ ký "Lãnh đạo đơn vị" |
| `frontend/src/lib/reports.js`, `components/FilterForm.vue` | `frontend/src/lib/reports.js`, `components/FilterForm.vue` | Bỏ phần kiểm kê (cột chênh lệch); thêm cột tiền, lịch gửi |
| `frontend/src/pages/ReportsHub.vue`, `ReportPage.vue` | cùng tên | Bỏ liên kết kiểm kê, biểu đồ; thêm danh sách và ngăn gửi theo lịch, bộ lọc bắt buộc |

Viết mới: ngân sách và EVM (`services/budget.py`), rủi ro, vấn đề, phát sinh (`services/control.py`), gửi báo cáo theo lịch (`services/reports/schedule.py`), MS Project XML (`services/msproject.py`), đóng dự án và gói hồ sơ (`services/closing.py`), các báo cáo (`services/reports/core.py`, lớp thi công `services/reporting.py`).


## M11

| File ở repo này | Nguồn (`document-manager-project/...`) | Thay đổi so với nguồn |
|---|---|---|
| `scripts/validate_prod_env.py` | `scripts/validate_prod_env.py` | Biến của repo này (MinIO của ứng dụng, Meilisearch, công ty); bắt buộc `HTTP_PUBLISH_PORT=127.0.0.1:<cổng>`; `DATA_ROOT` tuyệt đối và nằm ngoài mã nguồn; không dùng lại tiền tố volume hay mật khẩu của `docker/.env`; chế độ diễn tập `PM_REHEARSAL=1` cho tên `*.test` qua http |
| `scripts/prod_compose.py` | `scripts/prod_compose.py` | Thêm overlay bind khi có `DATA_ROOT`; giá trị của `docker/.env.prod` thắng biến môi trường của máy; bỏ overlay MinIO riêng (MinIO đã ở compose gốc) |
| `docker/docker-compose.prod.yml`, `docker-compose.prod.bind.yml` | `docker/docker-compose.prod.yml`, `docker-compose.prod.bind.yml` | Image `pm-custom` (hoặc image CI), các dịch vụ của repo này (queue `pm`, Meilisearch, MinIO), giới hạn bộ nhớ theo biến, chỉ nginx mở và chỉ ở `127.0.0.1` |

Viết mới: `scripts/deploy_prod.sh`, `backup.sh`, `restore.sh` (DM không có script sao lưu, khôi phục), `scripts/perf/load_progress.py`, phần M11 của `scripts/perf/volume_check.py`, `tests/test_security.py`, tài liệu `DEPLOYMENT.md`, `SAO_LUU_KHOI_PHUC.md`, `HUONG_DAN_SU_DUNG.md`.
