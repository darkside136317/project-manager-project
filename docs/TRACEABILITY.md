# Truy vết yêu cầu → mã → kiểm thử

Mục yêu cầu theo `prompt-project-manager-plan.md` (prompt gốc) và [KE_HOACH.md](KE_HOACH.md). Mỗi phase thêm dòng mới.

| Yêu cầu | Phase | Mã | Kiểm thử |
|---|---|---|---|
| 3.7 Không phụ thuộc bên ngoài repo (đường dẫn, repo khác) | M0 | `scripts/ci/check_repo.py` | CI `static` |
| 3.4 Lõi không import lớp thi công | M0 | `scripts/ci/check_repo.py`; `pm_construction/hooks.py` (`required_apps`) | CI `static`, `core-alone`; `pm_construction.tests.test_install` |
| 3.7 Ghim phiên bản | M0 | `docker/Dockerfile` (`node:24.22.2-slim`, `frappe/erpnext:v16.26.2`), `docker/docker-compose.yml` (`mariadb:11.8.6`, `redis:7.4.9-alpine`, `meilisearch:v1.12.8`), `package-lock.json` | CI `frontend`, `clean-clone` |
| 3.7 Cấu hình không làm tay: setup wizard, công ty, năm tài chính, kho, lịch nghỉ | M0 | `project_manager/setup/wizard.py`, service `setup-site` | `project_manager.tests.test_bootstrap.TestBootstrapDefaults`, `TestFiscalYearDates` |
| 3.7 Khởi động một lệnh, tự sinh secret, chạy lại không hỏng | M0 | `scripts/bootstrap.ps1`, `scripts/bootstrap.sh`, `docker/.env.example` | CI `clean-clone` (chạy bootstrap hai lần); kiểm thủ công trên Windows |
| 3.7 Đa nền tảng, LF cho script | M0 | `.gitattributes` | Clone thử trên Windows |
| 3.7 `.env.example` đủ biến | M0 | `docker/.env.example` | `scripts/ci/check_repo.py` |
| 3.6 SPA `/pm` cho người dùng nội bộ | M0 (khung) | `www/pm.py`, `www/pm.html`, `frontend/` | `TestSpaHost`, `frontend/tests/boot.test.js`, `scripts/e2e/smoke_http.py` |
| 5.5 JSON nhúng trong `<script>` không thoát được thẻ | M0 | `services/web.inline_json` | `TestSpaHost.test_inline_json_cannot_close_the_script` |
| 5.6 Chạy cùng máy với `document_manager` | M0 | `docker/.env.example` (`pmdev`, `pm`, `pm.localhost`, 8890) | Chạy song song trên máy dev |
| 5.1 Queue riêng `pm` | M0 (hạ tầng) | `configurator` (`workers.pm`), service `queue-pm` | — (dùng từ M2) |
