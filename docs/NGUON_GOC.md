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
| `apps/project_manager/project_manager/project_manager/services/web.py` | `services/web.py` | **Sửa lỗi**: bản gốc thay `"<"` bằng `"<"` — trong chuỗi Python thường đó chính là `"<"`, nên không escape được (nguy cơ XSS). Bản này dùng `"\\u003c"` và có test |
| `apps/project_manager/frontend/vite.config.js` | `frontend/vite.config.js` | Ra `public/spa`, biến `PM_WATCH_POLL` |
| `.github/workflows/ci.yml` | `.github/workflows/ci.yml` | Thêm job lõi chạy một mình, job clean clone, kiểm tra quy tắc repo |

Không sao chép: `docker/.env.dev` của `document_manager` (đang bị commit và chứa secret), các `Dockerfile.*-overlay` (vá nóng một lần triển khai), MongoDB/GridFS, PDFluent.
