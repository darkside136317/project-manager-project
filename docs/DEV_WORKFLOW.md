# Quy trình phát triển

## Chế độ dev

```bash
scripts/bootstrap.sh --dev        # Windows: scripts\bootstrap.ps1 -Dev
```

`--dev` đặt `COMPOSE_FILE=docker-compose.yml,docker-compose.dev.yml` trong `docker/.env`. Từ đó mọi lệnh `docker compose` chạy trong `docker/` đều dùng overlay dev:

| Dịch vụ | Việc làm |
|---|---|
| backend | gunicorn `--reload` (theo dõi bằng polling) |
| queue-pm, queue-short, queue-long, scheduler | chạy qua `dev/autoreload.py`: khởi động lại khi có file `.py` đổi |
| dev-watcher | đổi DocType JSON / fixtures / `patches.txt` / `hooks.py` / `install.py` → `bench migrate`; đổi `.html/.js/.css/.md` → xóa cache website |
| spa-watch | `npm run watch` trong `apps/project_manager/frontend` → build lại vào `project_manager/public/spa` |
| meilisearch | mở thêm `127.0.0.1:7701` để gỡ lỗi |

Polling được dùng vì bind mount từ Windows không phát sự kiện file.

Quay lại chạy image: `scripts/bootstrap.sh --local`. Sau khi đổi mã nguồn ở chế độ local, phải build lại image (`scripts/bootstrap.sh`).

## Lệnh thường dùng (trong `docker/`)

```bash
docker compose exec backend bench --site pm.localhost migrate
docker compose exec backend bench --site pm.localhost console
docker compose exec backend bench --site pm.localhost run-tests --app project_manager --module project_manager.tests.test_bootstrap
docker compose logs -f backend queue-pm
docker compose exec backend bench --site pm.localhost execute project_manager.project_manager.setup.demo.up    # dữ liệu mẫu
docker compose exec backend bench --site pm.localhost execute project_manager.project_manager.setup.demo.down  # gỡ dữ liệu mẫu
```

Đo rollup (dự án tạm 2.000 việc, tự xóa; worker `queue-pm` phải đang chạy):

```bash
docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - < ../scripts/perf/rollup_check.py
```

Kịch bản trình duyệt (cần Edge hoặc Chrome đã cài; tạo một dự án và một mẫu mã `E2E-...`, nên chỉ chạy trên site thử hoặc site dev; ảnh chụp từng bước nằm ở `scripts/e2e/ui/out/`):

```bash
cd scripts/e2e/ui && npm ci && node forms_flow.mjs
```

## Lưu ý

- **Git Bash trên Windows** đổi đường dẫn dạng `/home/...` trong tham số lệnh: đặt `MSYS_NO_PATHCONV=1` khi gọi `docker exec -w /home/...` hoặc truyền đường dẫn container. `scripts/bootstrap.sh` đã đặt sẵn.
- **Chạy script Python trong container**: truyền qua stdin (`docker compose exec -T backend env/bin/python - < file.py`); `/tmp` của máy không chia sẻ với container.
- **Worker và scheduler** ở chế độ local không tự nạp lại code: build lại image hoặc dùng `--dev`.
- **Đường dẫn test** là `project_manager.tests.test_x` (gói app), không phải gói module.
- **Không sửa DocType JSON khi đang chạy bộ test**: dev-watcher sẽ migrate giữa chừng và làm hỏng các module test sau.
- **MariaDB 11.8** cần `innodb_snapshot_isolation=OFF` (đã đặt trong `docker/mariadb/my_custom.cnf`), nếu không sẽ gặp lỗi 1020 "Record has changed since last read".
- **Jinja của Frappe v16 không tự escape**: luôn dùng `| e` hoặc `{% autoescape true %}`; dữ liệu JSON nhúng vào `<script>` dùng `services/web.inline_json`.
- Không ghi secret vào code, tài liệu hay log; chỉ dùng tên biến môi trường.
- **Frappe lưu các tệp cùng nội dung chung một URL:** test cần hai ảnh "khác nhau" phải dùng nội dung khác nhau.
- **Heredoc dài có dấu nháy làm hỏng công cụ Bash của Claude:** ghi tệp bằng Write rồi chạy.
- **Ngày của Task trong ERPNext v16 là Datetime** (`exp_start_date`, `exp_end_date`): so sánh bằng `getdate`, ô `type="date"` lấy 10 ký tự đầu.
- **Test có `frappe.db.rollback()` toàn phần** (ví dụ job xử lý lỗi) phải mock `frappe.db.rollback`, nếu không savepoint của `PMTestCase` mất và test sau lỗi.
