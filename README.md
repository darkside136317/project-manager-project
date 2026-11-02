# Project Manager — Quản lý dự án trên ERPNext

Hệ thống quản lý dự án tái sử dụng được cho nhiều ngành, thí điểm cho **thi công xây dựng**. Chạy trên
Frappe/ERPNext v16 bằng Docker. Kế hoạch đầy đủ: [docs/KE_HOACH.md](docs/KE_HOACH.md).

| App | Vai trò |
|---|---|
| `project_manager` | Lõi dùng chung mọi ngành: dự án, công việc, tiến độ, giao việc, cảnh báo, biểu mẫu, phân quyền, SPA `/pm` |
| `pm_construction` | Lớp nghiệp vụ thi công: hạng mục, khối lượng, nhật ký thi công, vật tư, máy, nghiệm thu. Phụ thuộc lõi; lõi không bao giờ import lớp này |

Trạng thái: **M0** — khung repo tự đủ (Docker, hai app rỗng, bootstrap, CI). Tiến độ: [docs/build-log/00-tong-quan-tien-do.md](docs/build-log/00-tong-quan-tien-do.md).

## Chạy thử trên máy

Yêu cầu: Docker Desktop (Windows/macOS) hoặc Docker Engine 24+ với Compose v2 (Linux); Docker được cấp **≥ 8 GB RAM**; khoảng 15 GB đĩa trống. Không cần cài Python, Node hay Frappe trên máy.

```bash
git clone https://github.com/darkside136317/project-manager-project.git
cd project-manager-project
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

Linux, macOS, Git Bash:

```bash
scripts/bootstrap.sh
```

Script bootstrap:
1. kiểm tra Docker;
2. tạo `docker/.env` từ `docker/.env.example` và **tự sinh mật khẩu** cho các biến trống;
3. build image `pm-custom` (lần đầu mất vài phút);
4. tạo site, cài ERPNext và hai app, chạy setup wizard ERPNext (công ty, năm tài chính, lịch nghỉ có ngày lễ Việt Nam) theo `docker/.env`;
5. khởi động toàn bộ dịch vụ và chờ site phản hồi.

Sau đó mở:
- `http://localhost:8890/pm` — giao diện quản lý dự án;
- `http://localhost:8890/desk` — ERPNext Desk.

Tài khoản `Administrator`, mật khẩu là `ADMIN_PASSWORD` trong `docker/.env`.

Chạy lại script bất cứ lúc nào: dữ liệu và mật khẩu được giữ nguyên, site được migrate. Muốn đổi tên công ty, viết tắt, năm tài chính… thì sửa `docker/.env` **trước** lần bootstrap đầu tiên.

Chạy cùng máy với `document_manager` được: hệ thống này dùng port `8890`, compose project `pmdev`, tiền tố volume `pm`, site `pm.localhost` (đều đổi được trong `docker/.env`).

### Dừng, xem log, xóa

```bash
cd docker
docker compose stop                 # dừng
docker compose logs -f backend      # xem log
docker compose down -v              # XÓA HẲN dữ liệu (volume) — không khôi phục được
```

## Phát triển

```bash
scripts/bootstrap.sh --dev          # hoặc: scripts\bootstrap.ps1 -Dev
```

Chế độ dev mount mã nguồn vào container: Python tự nạp lại, thay đổi DocType/hook tự `bench migrate`, SPA tự build lại. Quay về chạy image: `--local` / `-Local`. Chi tiết: [docs/DEV_WORKFLOW.md](docs/DEV_WORKFLOW.md).

## Kiểm thử

```bash
cd docker
docker compose exec backend bench --site pm.localhost set-config allow_tests true
docker compose exec backend bench --site pm.localhost run-tests --app project_manager
docker compose exec backend bench --site pm.localhost run-tests --app pm_construction
cd .. && python scripts/e2e/smoke_http.py
```

SPA: `npm ci && npm test` trong `apps/project_manager/frontend`. CI (`.github/workflows/ci.yml`) chạy kiểm tra tĩnh, test SPA, test lõi khi **không** cài lớp thi công, và một bản clone sạch bootstrap từ đầu.

## Cấu trúc thư mục

```
apps/project_manager/      lõi (Frappe app) + frontend/ (Vue 3 + Vite → public/spa)
apps/pm_construction/      lớp thi công (Frappe app)
docker/                    Dockerfile, compose (base, local, dev), .env.example, mariadb/, dev/
scripts/                   bootstrap.ps1, bootstrap.sh, e2e/, ci/
docs/                      kế hoạch, nhật ký xây dựng, truy vết yêu cầu, quy trình dev
```

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `Docker chưa chạy` | Mở Docker Desktop, đợi biểu tượng chuyển xanh rồi chạy lại |
| Port 8890 đã bị dùng | Đổi `HTTP_PUBLISH_PORT` và `PUBLIC_URL` trong `docker/.env`, chạy lại bootstrap |
| Site trả 502 sau khi máy ngủ dậy | `cd docker && docker compose up -d` rồi `docker compose restart frontend` |
| Script `.sh` báo `\r: command not found` | Repo bị clone với CRLF: `git config core.autocrlf false`, xóa thư mục rồi clone lại (`.gitattributes` đã ép LF) |
| PowerShell chặn script | Chạy đúng lệnh có `-ExecutionPolicy Bypass` ở trên |
