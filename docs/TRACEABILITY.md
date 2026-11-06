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
| 4.1 Mỗi việc đúng một người chịu trách nhiệm chính; RACI; nhận / từ chối có lý do; thu hồi; lịch sử không xóa | M2 | PM Task Assignment, `services/assignments.py`, `api/tasks.py` | `test_assignments` |
| 4.1 Giao cho đội / tổ / nhà thầu phụ | M2 | PM Team, `policy.teams_of`, `policy.assigned_task_sql` | `test_assignments.test_a_team_member_answers_for_the_team`, `test_a_crew_lead_sees_only_the_tasks_given_to_their_crew` |
| 4.1 Lịch sử đổi người, đổi hạn kèm lý do | M2 | `services/progress.record_activity` (doc_event Task), `services/tree.update` | `test_progress.test_deadline_changes_need_a_reason_once_work_is_given`, `test_assignments.test_one_accountable_person_at_a_time` |
| 4.1 Cây WBS: giai đoạn → hạng mục → công việc; thêm, di chuyển, sắp xếp, hủy | M2 | `services/tree.py`, `api/wbs.py`, SPA tab Công việc | `test_tree` |
| 4.1 Tạo dự án từ mẫu | M2 | `services/projects.create/copy_wbs`, `services/tree.bulk_insert` | `test_tree.test_project_from_a_template` |
| 4.10 Nhập WBS từ Excel, có chạy thử | M2 | `services/wbs_import.py`, SPA `ImportDialog.vue` | `test_tree.test_import_preview_shows_every_problem`, `test_import_writes_the_tree_and_the_owners` |
| 4.2 Cập nhật tiến độ theo việc, Kanban, kế hoạch so với thực tế | M2 | `services/progress.py`, `services/work.kanban`, SPA Kanban, `ProgressBar`, `SCurve` | `test_progress`, `test_work`, vitest `work.test.js` |
| 4.3 Tiến độ tự cộng dồn lên nhóm và dự án | M2 | `services/rollup.py`, `overrides/task.update_project`, queue `pm`, cron `sweep`, `reconcile_all` | `test_rollup`; HIEU_NANG.md (báo tiến độ → % dự án < 5 s) |
| 4.3 Lý do chậm và khâu gây chậm bắt buộc khi trễ | M2 | PM Delay Reason, PM Delay Source, `progress._apply_delay` | `test_progress.test_late_work_says_why` |
| 4.3 Cảnh báo đến hạn và quá hạn (bản đơn giản) | M2 | `services/reminders.py` (07:00), `rollup.refresh_overdue_flags` (hằng ngày) | `test_work.test_daily_reminder_once_a_day`, `test_rollup.test_lateness` |
| 4.2 Đường cong S từ số liệu hằng ngày | M2 | PM Snapshot, `rollup.take_snapshots`, SPA `SCurve.vue` | `test_rollup.test_daily_snapshot_is_one_row_per_day`, vitest |
| 4.4 Ai đang làm gì, chậm ở khâu nào | M2 | `services/work.who_does_what`, SPA tab Ai làm gì | `test_work.test_who_does_what` |
| 3.5 Gửi lại không bị trùng (`client_uuid`) | M2 (báo tiến độ) | PM Progress Entry `client_uuid` unique | `test_progress.test_the_same_send_twice_is_one_report` |
| 4.8 Người dùng tự thiết kế biểu mẫu: văn bản, số, ngày, chọn, hộp kiểm, bảng, ảnh, chữ ký | M3 | PM Form Template, `services/form_templates.py`, SPA `FormTemplatePage.vue`, `DynamicForm.vue` | `test_forms.TestTemplates`, `TestValues`, vitest `forms.test.js`, `forms_flow.mjs` |
| 4.8 Mẫu có phiên bản, đổi phiên bản không hỏng bản đã nộp | M3 | `form_templates.new_version/activate`, controller PM Form Template | `test_forms.TestTemplates.test_a_new_version_leaves_filled_forms_alone`, `test_a_template_in_use_is_frozen` |
| 4.8 Biểu mẫu gắn dự án / hạng mục / công việc; Nháp → Đã nộp → Đã duyệt | M3 | PM Form Submission, `services/forms.py`, SPA `FormSubmissionPage.vue`, `TaskForms.vue`, `FormsTab.vue` | `test_forms.TestWorkflow` |
| 4.8 In PDF, xuất Excel | M3 | `services/form_output.py`, `templates/pm_form_print.html` | `test_forms.TestOutput`, `forms_flow.mjs` |
| 4.8 Bắt buộc biểu mẫu đã duyệt mới đóng được việc, hạng mục | M3 | PM Gate Requirement, `services/gates.py`, `overrides/task.py`, `rollup._aggregate` | `test_forms.TestGates` |
| 4.8 Gói mẫu có sẵn, lớp ngành thêm gói riêng | M3 (chung) | `setup/form_pack.py`, hook `pm_form_packs` | `test_forms.TestTemplates.test_the_general_pack_is_installed_once` |
| 3.5 Ảnh, chữ ký trên điện thoại | M3 | `FormPictures.vue`, `SignaturePad.vue`, `forms.attach` | `test_forms.TestFiles`, `forms_flow.mjs` (390 px, có cảm ứng) |
| 5.5 Tệp private theo quyền của biểu mẫu; không mượn tệp người khác; escape khi in | M3 | `forms._files`, `forms.attach`, `form_output._picture` | `test_forms.TestFiles`, `TestOutput.test_answers_are_escaped_in_the_print`, `test_pictures_of_another_form_are_not_printed` |
| 4.2 Phụ thuộc FS/SS/FF/SF có độ trễ, phát hiện vòng tròn | M4 | PM Task Dependency, `services/schedule.add_dependency`, `services/cpm.order`, SPA `TaskLinks.vue` | `test_cpm.test_circles_are_found_at_any_length`, `test_schedule.TestDependencies` |
| D10 Đường găng tính ở server, theo ngày làm việc | M4 | `services/cpm.py`, `services/workdays.py`, `schedule.compute_plan` | `test_cpm`, `test_schedule.TestPlan` |
| 4.2 Gantt: phụ thuộc, đường găng, kéo-thả, so với baseline; điện thoại chỉ xem | M4 | `GanttChart.vue`, `lib/gantt.js`, `GanttTab.vue`, `schedule.gantt` | vitest `gantt.test.js`, `schedule_flow.mjs`, HIEU_NANG.md |
| 4.2 Xem trước khi dời lịch, việc sau bị đẩy theo, có lý do và lịch sử | M4 | `schedule.preview/apply`, `MovePreview.vue`, `activity.record_many` | `test_schedule.TestMoving`, `schedule_flow.mjs` |
| 4.2 Lịch thi công | M4 | `schedule.calendar_view`, `CalendarTab.vue` | `test_schedule.TestScreens.test_calendar`, vitest |
| 4.2 Baseline nhiều phiên bản, so sánh trên Gantt và bảng | M4 | PM Baseline (+Task, Curve), `services/baseline.py`, `BaselineTab.vue` | `test_schedule.TestBaseline` |
| 4.2 Đường cong S kế hoạch và thực tế, chênh lệch ngày, dự báo ngày hoàn thành | M4 | `baseline.curve_points/curve_for_chart`, `schedule.compute_forecast`, `SCurve.vue`, `OverviewTab.vue` | `test_schedule.TestForecast`, `test_baseline_move_gantt_forecast` |
