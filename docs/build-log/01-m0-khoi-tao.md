# M0 — Khởi tạo repo tự đủ

## 1. Mục tiêu

Repo mới, tách hẳn khỏi `document_manager`: clone sang máy khác, chạy **một lệnh** là có site ERPNext v16 với hai app `project_manager` (lõi) và `pm_construction` (lớp thi công) đã cài, setup wizard đã xong, SPA `/pm` trả về được (yêu cầu 3.7 của prompt, mục M0 của [KE_HOACH.md](../KE_HOACH.md)).

## 2. Thành phần đã tạo

M0 chưa có DocType nghiệp vụ. Các thành phần:

| Thành phần | Mục đích |
|---|---|
| App `project_manager` | Lõi. `hooks.py` (`required_apps = ["erpnext"]`, route `/pm/<path>`), `setup/wizard.py`, `services/web.py`, `www/pm.py` + `pm.html`, `frontend/` (Vue 3 + Vite) |
| App `pm_construction` | Lớp thi công, rỗng. `required_apps = ["erpnext", "project_manager"]` |
| `docker/` | `Dockerfile` (stage Node 24.22.2 build SPA + `frappe/erpnext:v16.26.2`), compose base / local / dev, `.env.example`, `mariadb/my_custom.cnf`, `dev/watcher.py`, `dev/autoreload.py` |
| `scripts/bootstrap.ps1`, `scripts/bootstrap.sh` | Khởi động một lệnh, chạy lại an toàn |
| `scripts/e2e/smoke_http.py` | Smoke test qua HTTP (chỉ dùng thư viện chuẩn) |
| `scripts/ci/check_repo.py` | Quy tắc repo: lõi không dùng lớp thi công, không đường dẫn ngoài repo, `.env.example` đủ biến bắt buộc |
| `.github/workflows/ci.yml` | static, frontend, core-alone, clean-clone, publish GHCR |

## 3. File chính

- `docker/docker-compose.yml`:
  - Service chạy một lần: `configurator` (ghi `common_site_config`, khai báo queue `pm`), `create-site` (bỏ qua nếu site đã có; danh sách app lấy từ `PM_INSTALL_APPS`), `setup-site` (setup wizard + migrate).
  - Worker `queue-pm`.
  - Ghim tag image: `mariadb:11.8.6`, `redis:7.4.9-alpine`, `getmeili/meilisearch:v1.12.8`.
- `docker/.env.example`: compose project `pmdev`, tiền tố volume `pm`, site `pm.localhost`, port 8890, overlay chọn bằng `COMPOSE_FILE` (+ `COMPOSE_PATH_SEPARATOR=,` để giống nhau trên mọi hệ điều hành). Secret để trống.
- `apps/project_manager/project_manager/project_manager/setup/wizard.py`:
  - `ensure_setup()` gọi `frappe.desk.page.setup_wizard.setup_wizard.setup_complete` với tham số từ biến môi trường: ngôn ngữ, quốc gia, múi giờ, tiền tệ, công ty, viết tắt, hệ thống tài khoản "Standard", năm tài chính.
  - Không truyền email, nên wizard không tạo thêm System Manager thứ hai.
  - `ensure_holiday_list()` tạo lịch nghỉ cho năm tài chính: ngày nghỉ hằng tuần cộng **ngày lễ Việt Nam** (thư viện `holidays` có sẵn trong ERPNext, tên tiếng Việt), đặt làm lịch nghỉ mặc định của công ty.
- `apps/project_manager/project_manager/www/pm.py`: khách → `/login?redirect-to=…` (302, không cache); Website User → `/me`; System User → trang SPA có `window.__PM_BOOT__`.
- `services/web.py`: `inline_json` escape `<`, `>`, `&`, U+2028, U+2029 thành `\uXXXX`. **Sửa lỗi của bản gốc trong `document_manager`**: bản đó viết `"\u003c"`, mà trong chuỗi Python thường giá trị này chính là `"<"`, nên không escape được gì.

## 4. Quyết định kỹ thuật

| Quyết định | Lý do |
|---|---|
| Overlay `docker-compose.local.yml` làm mặc định; `--dev` mới mount mã nguồn | Người chỉ muốn chạy thử không cần watcher, Node chạy liên tục, polling |
| Chọn overlay qua `COMPOSE_FILE` trong `docker/.env` | Mọi lệnh `docker compose` chạy trong `docker/` tự dùng đúng overlay, không phải nhớ tham số `-f` |
| Secret sinh ngẫu nhiên khi bootstrap, không có giá trị mặc định | Không bao giờ có mật khẩu chung giữa các máy; repo không chứa secret |
| `bootstrap.ps1` lưu UTF-8 **có BOM**; dùng `$ErrorActionPreference='Continue'` + kiểm `$LASTEXITCODE` | PowerShell 5.1 đọc file không BOM theo ANSI (vỡ tiếng Việt); docker ghi tiến trình ra stderr, với `Stop` sẽ bị coi là lỗi khi output bị chuyển hướng |
| Node 24.22.2 (LTS) thay Node 20 | Node 20 đã hết hỗ trợ |
| Desk của Frappe v16 ở `/desk` | `/app` chỉ chuyển hướng 301 sang `/desk`; SPA, smoke test, README dùng `/desk` |

**Hoãn lại so với kế hoạch** (để M0 gọn; chức năng đến đâu hạ tầng đến đó):

| Hạng mục | Chuyển sang | Lý do |
|---|---|---|
| MinIO (build từ nguồn mất vài phút mỗi máy) | M5 | Lúc đó mới có tệp và ảnh |
| Overlay prod, `prod_compose.py`, `validate_prod_env.py` | M11 | Phase triển khai |
| Tham số `--seed-demo` | M2 | Khi có dữ liệu mẫu để seed |

## 5. Kiểm thử đã chạy (2026-11-02, Windows 11 + Docker Desktop)

| Kiểm thử | Kết quả |
|---|---|
| `npm test` (vitest, trong stage build của image) | 4/4 qua |
| `run-tests --app project_manager` | 10/10 qua |
| `run-tests --app pm_construction` | 2/2 qua |
| `scripts/e2e/smoke_http.py` | 9/9 qua: ping, khách bị chuyển đến đăng nhập, đăng nhập, `/pm`, bundle, route sâu, `/desk` |
| `scripts/ci/check_repo.py` | 0 lỗi; regex đã thử với ví dụ vi phạm |
| `bootstrap.ps1` lần đầu trên repo (chưa có `.env`) | Sinh 3 secret, tạo site, `Setup complete: company 'Công ty Xây dựng Mẫu', holiday list 'CTXD 2026'` |
| `bootstrap.sh` (Git Bash) lần hai | Không sinh lại secret, "Site pm.localhost already exists", build lại SPA, smoke 9/9 |
| **Clone sạch**: xuất các file git đang theo dõi (`git checkout-index`, đúng quy tắc dòng: `.ps1` CRLF + BOM, `.sh` LF) sang thư mục mới, xóa volume, chạy `bootstrap.ps1` | Smoke 9/9, test 12/12 |
| **Lõi một mình**: site `core.localhost` chỉ cài ERPNext + `project_manager` (`PM_INSTALL_APPS`), có setup wizard | `list-apps`: frappe, erpnext, project_manager; test 10/10 |
| Chạy song song với stack `document_manager` (port 8888) | Cả hai cùng phản hồi |

Lệnh kiểm thử: xem README, mục "Kiểm thử".

| CI GitHub Actions trên commit `fa114a0` (static, SPA, lõi một mình, clean clone trên Ubuntu, publish GHCR) | Xanh (người dùng xác nhận) |

**Chưa kiểm được:** bootstrap trên macOS thật (Linux đã được job `clean-clone` của CI chạy trên Ubuntu).

## 6. Điểm cần chú ý khi duyệt

- `docker compose down -v` xóa hẳn dữ liệu (README đã ghi).
- Tên công ty, viết tắt, năm tài chính phải sửa trong `docker/.env` **trước** lần bootstrap đầu tiên. Sau khi wizard đã chạy, đổi biến không có tác dụng.
- Lịch nghỉ mặc định chỉ phủ năm tài chính hiện tại. M4 (lịch trình) sẽ tự tạo các năm tiếp theo.
- Phát hiện khi khảo sát `document_manager` (không sửa trong phase này):
  - lỗi `inline_json` nói ở mục 3;
  - `docker/.env.dev` bị commit kèm secret.

## 7. Việc tiếp theo

**M1 — Nền tảng chung:**
- policy/capabilities và `project_scope`;
- nhóm quyền;
- hook phân quyền trên Project, Task và các DocType PM;
- mixin Task (`extend_doctype_class`);
- khung SPA ưu tiên điện thoại;
- bộ sinh 1 triệu task;
- spike Gantt.
