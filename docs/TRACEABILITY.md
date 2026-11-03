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
| 5.2 Phân quyền từ đầu: một hàm lọc phạm vi dự án cho mọi truy vấn | M1 | `policy.get_access`, `policy.project_sql`, `permissions.py`, `hooks.permission_query_conditions/has_permission` | `test_project_scope` (gồm `frappe.client`, report view, `search_link`, `get`) |
| 5.2 Capabilities toàn cục và vai trò trong dự án | M1 | `constants.CAPABILITIES/PROJECT_CAPABILITIES`, PM Role Profile, PM Project Role, `policy.capabilities_in` | `test_project_scope.test_capabilities_follow_the_project_role`, `test_admin_api.test_groups_copy_and_edit` |
| 5.2 Mọi DocType có `project` đều có hook phạm vi | M1 | `constants.PROJECT_SCOPED`, `hooks.py` | `test_hook_coverage` |
| 4.6 Một người nhiều dự án, mỗi dự án một vai trò | M1 | PM Project Member (+ hiệu lực theo ngày) | `test_project_scope.test_membership_outside_its_dates_gives_nothing` |
| 3.3 Không sửa lõi ERPNext; vô hiệu hành vi không hợp (4.2 kế hoạch) | M1 | `overrides/task.py` (`extend_doctype_class`), `setup/install.stop_erpnext_overdue_job`, Timesheet doc_events | `test_task_mixin` (contract + hành vi) |
| D4 Cây WBS theo dự án, không đánh số toàn bảng | M1 | `services/wbs.py` | `test_task_mixin.test_tree_paths/test_no_global_renumbering/test_moving_carries_the_subtree`, HIEU_NANG.md |
| 3.7 Cấu hình không làm tay (role, nhóm, vai trò dự án, custom field, quyền ERPNext) | M1 | `setup/install.seed_all` | `test_install` (gồm chạy lại không đổi gì) |
| 4.10 Quản trị: người dùng, nhóm quyền, nhóm nhân viên, nhật ký, giám sát | M1 | `api/users.py`, `api/permissions.py`, `api/logs.py`, `api/admin.py`, SPA `/pm/quan-tri/*` | `test_admin_api`, vitest `admin/permissions` |
| 3.6 SPA ưu tiên điện thoại | M1 (khung) | `frontend/src` (AppShell, SidebarNav, router) | vitest `boot.test.js`; kiểm 390 px không cuộn ngang |
| 12 Hiệu năng 1 triệu task | M1 | `scripts/perf/volume_check.py` | HIEU_NANG.md (thêm task 9 ms) |
| D11 Chọn Gantt | M1 (spike) | `spikes/gantt/` | spikes/GANTT.md |
