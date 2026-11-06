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
