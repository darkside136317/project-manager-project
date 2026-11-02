# Kế hoạch: Hệ thống Quản lý Dự án Thi công trên ERPNext — `project_manager` + `pm_construction`

## Context

Người dùng muốn xây một hệ thống quản lý dự án **tái sử dụng được**, thí điểm cho **doanh nghiệp thi công xây dựng**. Yêu cầu nằm trong `D:\Documents\frappe_docker\prompt-project-manager-plan.md`:
- giao việc rõ trách nhiệm;
- tiến độ trực quan (Gantt, Kanban, lịch, kế hoạch so với thực tế);
- tự động cộng dồn tiến độ, chuyển giai đoạn và cảnh báo;
- hiệu suất nhân sự;
- vật tư, máy, nhân công;
- nhiều dự án trên một nền tảng;
- trao đổi theo từng đầu việc;
- biểu mẫu động.

Hệ thống chạy trên **ERPNext có sẵn**, đặt trong **repo mới hoàn toàn tách khỏi `document_manager`**: clone sang máy khác là chạy được đủ chức năng. Kiến trúc, hạ tầng và mẫu code được sao chép từ `document_manager`, dự án đã qua G0–G9 và Phân quyền v2.

**Đã khảo sát:**
- `document_manager`: backend, Docker, SPA, CI.
- ERPNext **16.26.2** / Frappe **16.26.3** trong container `docker-backend-1`. Python 3.14.2, HRMS không cài và không cần.

**Ba quyết định đã chốt với người dùng:**
- Gantt: làm thử nghiệm (spike) ở M1 rồi chọn thư viện.
- Offline: chỉ có hàng đợi gửi lại cho dữ liệu ghi thêm.
- Thí điểm: sau M7.

---

## 1. Tóm tắt

- **Một repo** `project-manager-project` chứa **hai app Frappe**:
  - `project_manager`: lõi dùng chung mọi ngành.
  - `pm_construction`: lớp thi công, phụ thuộc lõi.
- Lõi **không bao giờ import** lớp thi công. Lớp thi công đăng ký phần mở rộng qua hook `pm_extensions`: phương pháp tính tiến độ, điều kiện chuyển giai đoạn, loại cảnh báo, màn hình, báo cáo, gói mẫu.
- **ERPNext** cung cấp Project, Task, Timesheet, Stock, Buying, Asset. Hệ thống chỉ mở rộng bằng:
  - custom field;
  - **một mixin Task** qua hook `extend_doctype_class`, đã kiểm có trong Frappe v16 tại `frappe/model/base_document.py:190`;
  - doc_events, query conditions.
- Không sửa lõi ERPNext và không dùng `override_doctype_class`.
- **Phân quyền** gồm capabilities toàn cục và vai trò theo từng dự án. Mọi truy vấn đi qua **một hàm `project_scope`**, kể cả truy vấn trên DocType ERPNext.
- **Tự động hóa** chạy qua queue riêng `pm`:
  - cộng dồn tiến độ tăng dần, chỉ tính lại các node cha bị ảnh hưởng;
  - đường găng (CPM) tính ở server;
  - dự báo trễ, cảnh báo có leo thang, chuyển giai đoạn theo điều kiện.
- **Giao diện:**
  - SPA Vue 3, ưu tiên điện thoại, PWA có hàng đợi gửi lại khi mất mạng;
  - Desk ERPNext dành cho kế toán và thủ kho khi cần.
- **Lộ trình** M0–M11. **Thí điểm sau M7**: đủ lõi, lớp thi công cơ bản và cảnh báo. Vật tư, máy, nhân công vào M8.
- **Repo tự đủ:** ghim phiên bản; bootstrap một lệnh (PowerShell và bash) tự sinh secret; cấu hình mặc định bằng code; CI có job "clean clone".

---

## 2. Quyết định D1…D20

Trạng thái: ✅ đã chốt · ❓ cần người dùng xác nhận khi duyệt kế hoạch · ⚙️ quyết định kỹ thuật, sẽ đổi nếu kiểm chứng ở M1 thất bại.

| # | Quyết định | Chọn | Phương án thay thế | Lý do | TT |
|---|---|---|---|---|---|
| D1 | Số app | 2 app trong 1 repo (`project_manager`, `pm_construction`) | 1 app có module "Thi công" | Ranh giới kiểm được bằng CI: chạy test lõi khi không cài lớp thi công. Ngành khác chỉ cần thêm app lớp mới | ✅ |
| D2 | Nền ERPNext | Image `frappe/erpnext:v16.26.2`, ghim tag | `apps.json` + `bench get-app` | Giống `document_manager`, đã chạy ổn; build nhanh, mọi máy giống nhau | ✅ |
| D3 | Giai đoạn / Hạng mục / Công tác | Đều là **node Task**, phân loại bằng `pm_node_type` → `PM Node Type` | DocType riêng cho từng cấp | Một cây duy nhất cho rollup, Gantt, phụ thuộc giữa các cấp; một cột `project` để phân quyền | ⚙️ |
| D4 | Đánh số cây Task | Mixin thay `update_nsm`: dùng `pm_lft/pm_rgt` **trong phạm vi từng dự án**; `lft/rgt` toàn cục để 0 | Giữ nested set của Frappe | Đã kiểm `nestedset.py:90`: mỗi lần thêm task, Frappe chạy `UPDATE tabTask SET rgt=rgt+2` trên **toàn bảng**. Với 1 triệu task, việc này khóa dữ liệu của mọi dự án | ⚙️ |
| D5 | Can thiệp ERPNext | 1 mixin Task (`extend_doctype_class`) + flags + doc_events + dừng 1 job lịch | `override_doctype_class` | Phạm vi can thiệp nhỏ nhất; có contract test khi nâng cấp | ✅ |
| D6 | Thành viên dự án | DocType riêng `PM Project Member` (user, vai trò dự án, hiệu lực); đồng bộ một chiều sang `Project User` | Mở rộng `Project User` | Truy vấn theo user trên mọi dự án có index; sửa thành viên không phải lưu Project | ⚙️ |
| D7 | Phân quyền | Capabilities toàn cục + `PM Project Role` theo dự án; một hàm `project_scope(user)` | Chỉ dùng User Permission của Frappe | Bê nguyên mô hình `staff_scope` đã kiểm chứng; ERPNext không lọc Project/Task theo người dùng | ✅ |
| D8 | Tiến độ cộng dồn | ERPNext để `Manual`; rollup tăng dần của hệ thống. Phương pháp: thời lượng (mặc định), task_weight, bằng nhau, **giá trị dự toán** (lớp thi công) | Dùng `percent_complete_method` của ERPNext | ERPNext đếm cả task nhóm, không cộng dồn từ con lên cha, và lưu Project từ bản cache có thể đã cũ | ✅ |
| D9 | Phụ thuộc task | Bảng `PM Task Dependency` (FS/SS/FF/SF, lag); `depends_on` của ERPNext để trống | Dùng `Task Depends On` | ERPNext chỉ có FS; kiểm tra vòng lặp dừng sau 15 bước; `populate_depends_on` lưu cả task cha theo dây chuyền | ✅ |
| D10 | Đường găng | Tính ở server (Python, theo ngày làm việc); client chỉ xem trước khi kéo | Tính trong thư viện Gantt | Không phụ thuộc thư viện; dùng chung cho cảnh báo và dự báo | ✅ |
| D11 | Thư viện Gantt | Spike M1 với 5.000 task trên điện thoại tầm trung: SVAR Gantt (MIT), frappe-gantt, tự vẽ canvas | Bryntum (thương mại), dhtmlx (GPL, đường găng chỉ có ở bản trả phí) | Người dùng chọn thử nghiệm trước | ✅ |
| D12 | Offline | Hàng đợi gửi lại cho dữ liệu chỉ ghi thêm (tiến độ, nhật ký, ảnh, chấm công, đề xuất vật tư nháp), khóa `client_uuid` | Chỉ online / offline đầy đủ | Người dùng chọn | ✅ |
| D13 | Dòng thời gian trao đổi | Bảng riêng `PM Activity` (autoincrement, có cột `project`) | Comment / Version của Frappe | Dự kiến 5 triệu dòng; cần lọc theo dự án bằng SQL; dữ liệu không sửa được; cần idempotency cho offline | ⚙️ |
| D14 | Baseline | Header + bảng dòng chèn hàng loạt + đường cong tính sẵn | Lưu JSON | So sánh theo từng task, vẽ đường cong S không phải quét | ⚙️ |
| D15 | Gắn vật tư với công tác | Custom field `pmc_task` trên dòng Material Request Item / PO Item / PR Item / Stock Entry Detail; `pm_project` trên header Material Request | DocType cấp phát riêng | Dùng luồng kho của ERPNext (giá trị tồn, sổ kho); `get_mapped_doc` tự chép trường cùng tên | ✅ |
| D16 | Máy thi công | `PMC Machine`: máy sở hữu liên kết `Asset`; máy thuê không phải Asset; điều chuyển máy sở hữu tạo `Asset Movement` | Chỉ dùng Asset | Asset không có trường dự án; máy thuê không phải tài sản kế toán | ✅ |
| D17 | Mẫu dự án | Project có `pm_is_template=1` + dịch vụ nhân bản (chèn hàng loạt) | `Project Template` của ERPNext | Template ERPNext chỉ có task phẳng, chép từng bản ghi và chạy qua nested set toàn cục | ⚙️ |
| D18 | Thời điểm thí điểm | Sau M7 | Sau M5 / sau M8 | Người dùng chọn | ✅ |
| D19 | Repo | `D:\Documents\project-manager-project`, remote `github.com/darkside136317/project-manager-project` (**riêng tư**) | Đặt trong `frappe_docker` | Tách khỏi repo upstream của Frappe; cùng tài khoản với DM | ✅ |
| D20 | Cấu hình mặc định để chạy cùng máy với DM | `COMPOSE_PROJECT_NAME=pmdev`, `DATA_VOLUME_PREFIX=pm`, site `pm.localhost`, port `8890` | — | `document_manager` dùng `docker` / `docmanager` / `8888` | ✅ |

---

## 3. Tái sử dụng từ `document_manager`

Gốc nguồn: `document-manager-project/apps/document_manager/document_manager/document_manager/` (viết tắt `dm/`). Mỗi file sao chép được ghi nguồn gốc trong `docs/NGUON_GOC.md`. Repo mới không import, không dùng submodule, không dùng chung image hay volume với DM.

| Thành phần | Nguồn | Xử lý |
|---|---|---|
| `services/errors.py` (`retry_on_deadlock`, `log_exception`) | `dm/services/errors.py` | **Sao chép nguyên** |
| `services/queries.py` (`capped_count`, `total_of_short_page`, `bounded_scan`) | `dm/services/queries.py` | **Sao chép nguyên** |
| Khung báo cáo (`Report`, `register`, `Where`, `output.py` CSV/XLSX/PDF) | `dm/services/reports/base.py`, `__init__.py`, `output.py` | Sao chép rồi sửa: `Where.fonds_scope` → `Where.project_scope`; bỏ `archive.py`, `readers.py` |
| Ghi nhật ký (`log_activity`, `audit_doc_event`, đăng nhập/đăng xuất, `purge_logs`) + vòng `doc_events` trong hooks | `dm/services/audit.py`, `hooks.py` | Sao chép rồi sửa danh sách DocType |
| `notify_user`, `notify_capability`, `unread_count`, `mark_read` | `dm/services/notify.py` | Sao chép phần chung; bỏ phần phiếu |
| `check_services` (cache 20 s / 60 s), `_short()` | `dm/services/health.py` | Sao chép rồi sửa danh sách dịch vụ |
| MinIO `ObjectStorage` | `dm/services/object_storage.py` | Sao chép rồi sửa (bỏ `upload_document_file`) |
| Meilisearch: index sau commit, đối soát, lọc quyền | `dm/services/search_index.py` | Sao chép rồi sửa: index `PM Activity`, Task, tài liệu |
| `policy.py` (`is_admin`, `capabilities_of`, `has_capability`, `assert_capability`, memo theo request) | `dm/policy.py` | Sao chép rồi sửa: `staff_scope` → `project_scope`; thêm `capabilities_in(project)`; bỏ nhánh độc giả và mức mật |
| Bộ điều hợp quyền `_archive_query` / `_archive_permission` / `PARENT_OF` | `dm/permissions.py` | Sao chép rồi sửa thành `project_query(doctype, column)` / `project_permission` chung |
| Staff Role Profile + Capability, Staff Group (+Member), Staff Access | `dm/doctype/...` | Sao chép rồi sửa: Staff Access → `PM Access` (+`PM Access Project`) |
| Ma trận Custom DocPerm | `dm/services/permission_matrix.py` | **Sao chép nguyên** (đổi `ROLE_MATRIX`) |
| API khung: `crud.py`, `meta.py`, `ui.describe/REGISTRY`, `boot.py`, `users.py`, `permissions.py`, `logs.py`, `admin.py`, `reports.py` | `dm/api/`, `dm/services/ui.py` | Sao chép rồi sửa: bỏ phần lưu trữ; đổi `REGISTRY` và menu |
| Dựng workflow từ tuple, `ensure_*` idempotent, `ensure_single_defaults` | `dm/setup_workflows.py`, `dm/setup/install.py` | Sao chép mẫu, viết lại trạng thái và vai trò |
| `inline_json`, `csrf_token` | `dm/services/web.py` | Sao chép **và sửa lỗi**: `"\u003c"` → `"\\u003c"` (tương tự cho `>` và `&`). Bản gốc không escape được, có nguy cơ XSS |
| Docker: compose base/dev/prod/minio/bind, `Dockerfile` (stage Node + `frappe/erpnext`), `mariadb/my_custom.cnf`, `minio/` (build từ nguồn), `dev/watcher.py`, `dev/autoreload.py`, `.gitattributes`, `.dockerignore` | `document-manager-project/docker/` | Sao chép rồi sửa: tên image `pm-custom`, 2 app, queue `pm`, port 8890, site `pm.localhost`; bỏ Tesseract/OCR, Mongo, PDFluent |
| Overlay Dockerfile (`*-overlay`, `upload1g`) | `docker/` | **Bỏ**: vá nóng cho một lần triển khai, phụ thuộc file không có trong repo |
| `scripts/start-dev.sh` | `scripts/` | **Viết mới**: `bootstrap.ps1` + `bootstrap.sh` |
| `prod_compose.py`, `validate_prod_env.py` | `scripts/` | Sao chép rồi sửa |
| SPA: AppShell, SidebarNav, Breadcrumbs, PageHeader, CommandPalette, UserMenu, NotificationBell, EmptyState, StatusBadge, ToastHost, ConfirmDialog, ReasonDialog, Drawer, RecordDrawer, FormRenderer, FieldInput, LinkSelect, TableInput, DataTable, FilterForm, PaginationBar, BarChart, TreeNode, FileUploader, ExportPanel, ImportPanel; `lib/api.js`, `boot.js`, `doctype.js`, `format.js`, `toast.js`, `theme.js`, `upload.js`, `useTree.js`, `reports.js`, `admin.js`; trang Master*, Reports*, Users/Roles/Groups/Logs/Monitor/Settings | `frontend/src/` | Sao chép rồi sửa: tiền tố `dm-`/`__DM_BOOT__` → `pm-`/`__PM_BOOT__`; `api.js` bỏ `workMode` và đổi đường dẫn method |
| Component và trang lưu trữ (ArchiveTree, FondsPicker, Slip*, Preservation*, Exchange*...) | `frontend/src/` | **Bỏ** |
| Test: mẫu `IntegrationTestCase` + savepoint + vô hiệu `frappe.db.commit` + `_forget_caches` | `tests/` | Sao chép mẫu vào `tests/helpers.py` (DM không có base class chung → tạo mới `PMTestCase`) |
| E2E: Playwright `.mjs` + `nav.mjs`, `e2e_http.py`, `accounts.py up/down`, `perf/volume_check.py` | `scripts/` | Sao chép rồi sửa: site lấy từ `.env`, không hard-code (bản gốc ghi sai `docmanager.yourdomain.com`) |
| CI (static, frontend, test, publish GHCR) | `.github/workflows/ci.yml` | Sao chép rồi sửa: thêm `test-core`, `clean-clone`, lint ranh giới |
| `docker/.env.dev` | — | **Không sao chép**: file này đang bị commit trong DM và chứa secret khác file mẫu |

---

## 4. Tận dụng ERPNext v16

### 4.1. DocType dùng đến

| DocType | Cách dùng | Custom field (core `pm_`, thi công `pmc_`) |
|---|---|---|
| Project | Dự án / công trình | `pm_code`, `pm_state` (Chuẩn bị/Đang thực hiện/Tạm dừng/Đóng/Hủy), `pm_is_template`, `pm_rollup_method`, `pm_holiday_list`, `pm_health`, `pm_spi`, `pm_forecast_end`, `pm_primary_baseline`, `pm_current_phase`, `pm_manager`. Property Setter: `percent_complete_method` = Manual, chỉ đọc |
| Task | Mọi node WBS | `pm_node_type`, `pm_lft`, `pm_rgt`, `pm_level`, `pm_wbs_code`, `pm_sort`, `pm_duration`, `pm_rollup_weight`, `pm_accountable`, `pm_accountable_team`, `pm_reviewer`, `pm_is_critical`, `pm_total_float`, `pm_forecast_end`, `pm_spi`, `pm_risk`, `pm_is_overdue`, `pm_delay_days`, `pm_delay_reason`, `pm_delay_source`, `pm_planned_value`, `pm_earned_value`, `pm_last_progress_on`, `pm_gate_mode`. Thi công: `pmc_uom`, `pmc_planned_qty`, `pmc_unit_price`, `pmc_estimate_value`, `pmc_done_qty`, `pmc_accepted_qty`, `pmc_boq_item`, `pmc_norm_code` |
| Timesheet / Timesheet Detail | Chấm công kỹ sư theo task | Không thêm; ràng buộc mọi dòng cùng `parent_project` |
| Employee, Department, Holiday List | Nhân sự, lịch nghỉ | Không thêm |
| Warehouse, Location | Kho và vị trí công trường | `pm_project` |
| Item, Material Request (+Item), Purchase Order/Receipt/Invoice (+Item), Stock Entry (+Detail) | Luồng vật tư | MR header: `pm_project` (bắt buộc, chép xuống `project` của từng dòng). Các dòng: `pmc_task`. Stock Entry: `pmc_kind` (Cấp phát/Hoàn trả/Hao hụt/Điều chuyển) |
| Asset, Asset Movement, Asset Maintenance | Máy sở hữu | Asset Movement: `pm_project` |
| Company, Cost Center, Fiscal Year | Tạo khi bootstrap (setup wizard) | — |

### 4.2. Hành vi ERPNext cần vô hiệu (đã kiểm trong mã nguồn v16)

| Hành vi | Cách xử lý |
|---|---|
| Nested set toàn cục khi thêm task (`nestedset.py:90`) | Mixin `update_nsm` chỉ duy trì `pm_lft/pm_rgt` trong phạm vi dự án. Nhập, nhân bản, sắp xếp: đánh số trong bộ nhớ rồi ghi theo lô. Test cấm gọi `rebuild_tree("Task")` |
| `populate_depends_on` thêm task con vào `depends_on` của cha rồi `parent.save()` (`task.py:303`) | Mixin bỏ qua. Patch xóa các dòng cha↔con hiện có |
| `reschedule_dependent_tasks` (thực tế không chạy), `check_recursion` dừng sau 15 bước | Mixin bỏ qua; kiểm tra vòng lặp bằng thuật toán sắp xếp tô-pô (Kahn) không giới hạn bước, trên `PM Task Dependency` |
| Kiểm ngày con ≤ cha, mọi ngày ≤ ngày kết thúc dự án | Mixin nới lỏng: không kiểm ngày thực tế; ngày của node nhóm do rollup tính; vượt ngày dự án thì tự gia hạn (có ghi lý do) hoặc báo lỗi nếu dự án bật chế độ chặt |
| `Task.update_project` lưu Project từ `get_cached_doc` | Mixin thay bằng "đánh dấu cần tính lại + enqueue rollup". Ghi bằng `frappe.db.set_value` |
| `percent_complete_method` tự đặt Completed khi đạt 100 | Đặt Manual. `status` của ERPNext suy ra từ `pm_state` |
| Timesheet submit/cancel ép trạng thái Task thành Completed/Working | Timesheet `before_submit/before_cancel` bật cờ `pm_ts_sync`. Khi cờ bật, Task `before_validate` khôi phục `status` và `progress` từ DB, chỉ giữ thời gian và chi phí |
| Job hằng ngày `set_tasks_as_overdue` | `after_migrate` đặt `Scheduled Job Type.stopped=1`; trang giám sát cảnh báo nếu job bị bật lại. Thay bằng một câu SQL cập nhật `pm_is_overdue`/`pm_delay_days` |

Mỗi method mà mixin ghi đè có **contract test**: kiểm method còn tồn tại trên lớp Task của ERPNext, kèm test hành vi. Chạy lại trước mỗi lần nâng cấp ERPNext.

---

## 5. Kiến trúc

```
Trình duyệt / PWA điện thoại ──► nginx (frontend:8080 → host 8890)
                                   ├─ /pm/*      SPA Vue 3 (staff, mobile-first)
                                   ├─ /desk/*    Desk ERPNext (kế toán, thủ kho, quản trị)
                                   └─ /api/*     backend (gunicorn)
backend ── project_manager (services/ → api/) ◄── pm_construction (đăng ký qua hook pm_extensions)
   │            └── ERPNext (Project, Task, Stock, Buying, Asset) + Frappe
   ├─ MariaDB 11.8   ├─ Redis cache / queue   ├─ Meilisearch   ├─ MinIO (tệp, ảnh)
   └─ worker: pm (rollup, CPM, fan-out), short, default, long · scheduler · websocket (realtime)
```

**Hợp đồng mở rộng `pm_extensions`** (trong `hooks.py` của `pm_construction`; lõi đọc bằng `frappe.get_hooks`):
`rollup_methods`, `gate_checks`, `alert_rule_types`, `node_types` (fixtures), `spa_modules` (route và menu), `reports`, `form_packs`, `project_close_handlers`.

Lõi có test chạy khi **không cài** `pm_construction`. CI có lint cấm `import pm_construction` trong lõi.

**Cấu trúc repo:**
```
project-manager-project/
├── apps/project_manager/project_manager/{hooks.py, patches.txt, fixtures/, tests/, www/pm.(html|py)}
│   └── project_manager/{policy.py, permissions.py, constants.py, extensions.py, setup/, services/, api/, doctype/}
│   └── frontend/ (Vite → public/spa)
├── apps/pm_construction/pm_construction/{hooks.py, fixtures/, tests/}
│   └── pm_construction/{services/, api/, doctype/}   (+ frontend module tích hợp vào SPA lõi qua spa_modules)
├── docker/{docker-compose.yml, .dev.yml, .prod.yml, .prod.minio.yml, .prod.bind.yml, Dockerfile, mariadb/, minio/, dev/, .env.example, .env.prod.example}
├── scripts/{bootstrap.ps1, bootstrap.sh, prod_compose.py, validate_prod_env.py, e2e/, perf/, demo/}
├── docs/{KE_HOACH.md, NGUON_GOC.md, TRACEABILITY.md, DEV_WORKFLOW.md, DEPLOYMENT.md, HIEU_NANG.md, build-log/}
├── .gitattributes  .dockerignore  .gitignore  README.md
└── .github/workflows/ci.yml
```

**Compose (dev):**

| Service | Mục đích | Cổng host |
|---|---|---|
| db (`mariadb:11.8.x`) | Cơ sở dữ liệu | — |
| redis-cache, redis-queue (`redis:7.4.x-alpine`) | Cache, hàng đợi | — |
| meilisearch (`v1.12.x`) | Tìm kiếm toàn văn | 127.0.0.1:7701 (chỉ dev) |
| minio, minio-init | Lưu tệp và ảnh (build từ nguồn, như DM) | 127.0.0.1:9101 (chỉ dev) |
| configurator, create-site, setup-site (chạy một lần) | Cấu hình, tạo site, chạy setup wizard | — |
| backend, websocket | API, realtime | — |
| frontend (nginx) | Cổng vào | 127.0.0.1:${HTTP_PUBLISH_PORT:-8890} |
| queue-pm, queue-short, queue-long, scheduler | Xử lý nền | — |
| dev-watcher, spa-watch (chỉ dev) | Tự migrate, build SPA | — |

Volume: `${DATA_VOLUME_PREFIX:-pm}_{db-data,sites,logs,redis-queue-data,meili-data,minio-data}`; network `${DATA_VOLUME_PREFIX}_network`.

---

## 6. Mô hình dữ liệu

**Quy ước:**
- Mọi DocType nghiệp vụ có cột `project`, gán trong `validate`, để phân quyền bằng SQL.
- Bảng dữ liệu lớn dùng `autoname: autoincrement` và phân trang keyset.
- Index khai báo trong `on_doctype_update`, kèm patch cho site đã có.

### 6.1. Lõi `project_manager`

| DocType | Trường chính | Ghi chú / index |
|---|---|---|
| PM Settings (Single) | Phương pháp rollup mặc định, lịch nghỉ, giờ gửi tóm tắt, ngưỡng sức khỏe, bật/tắt dịch vụ ngoài | — |
| PM Node Type | label, is_group, allowed_children, counts_in_rollup, requires_accountable, default_gate_mode | Seed sẵn: Giai đoạn, Nhóm việc, Công việc, Việc con, Mốc |
| PM Project Role (+Capability) | label, task_visibility (Tất cả / Được giao), required_frappe_roles, capabilities | Seed theo mục 7 |
| PM Project Member | project, user, employee, project_role, valid_from/to, is_active, allocation_pct | unique (project, user, project_role); idx (user, is_active) |
| PM Access (+PM Access Project), Staff Group (+Member), Staff Role Profile (+Capability), Business Activity Log | Sao chép từ DM. Phạm vi: Tất cả dự án / Dự án được chọn / Chỉ dự án tham gia | — |
| PM Team (+Member) | team_type (Phòng / Tổ đội / Nhà thầu phụ), leader, supplier, members | PMT-.#### |
| PM Task Assignment | task, project, raci (A/R/C/I/Duyệt), user hoặc team, state (Chờ nhận / Đã nhận / Từ chối / Thu hồi / Xong), decline_reason, assigned_by/on, responded_on, assigned_qty, is_active, `accountable_key` | autoincrement; **unique(accountable_key)** bảo đảm mỗi task đúng một người chịu trách nhiệm chính. Không xóa, chỉ thu hồi |
| PM Task Dependency | project, predecessor, successor, type (FS/SS/FF/SF), lag_days | unique (predecessor, successor) |
| PM Delay Reason, PM Delay Source | Mã lý do chậm; khâu gây chậm (Thiết kế / Cung ứng / Thi công / CĐT / TVGS / Thời tiết) | Seed |
| PM Activity | project, reference_doctype/name, task, type (comment / progress / field_change / assignment / deadline_change / status / attachment / form / system), actor, content, data JSON, mentions, client_uuid | autoincrement; idx (reference, id), (project, id); unique (client_uuid). Không sửa, không xóa cứng |
| PM Follow | user, reference, watching, muted, last_read_id | unique (user, reference) |
| PM Media | file, project, reference, lat, lng, taken_at, thumbnail, client_uuid | idx (project, taken_at) |
| PM Progress Entry | task, project, entry_date, reporter, team, progress_before/after, qty_delta, man_days, note, client_uuid | idx (task, entry_date), (team, entry_date) |
| PM Baseline / PM Baseline Task / PM Baseline Curve | Header (số, chính/phụ, BAC); dòng (task, start, finish, weight, planned_value); đường cong theo tuần | unique (baseline, task) |
| PM Snapshot | Tiến độ, EV, SPI, dự báo, sức khỏe hằng ngày theo dự án và node nhóm (độ sâu ≤ 3) | unique (node, date) |
| PM Gate Requirement | task (node giai đoạn), type (biểu mẫu đã duyệt / con xong / tiến độ ≥ / phần mở rộng), form_template_code, blocks (đóng việc / chuyển giai đoạn) | idx (task) |
| PM Form Template (+PM Form Field) | code, version, status (Nháp / Đang dùng / Ngừng), fields (text / số / ngày / chọn / checkbox / bảng / ảnh / chữ ký), mẫu in | `{code}-v{##}`; bản đang dùng không sửa được, sửa là tạo phiên bản mới |
| PM Form Submission | template, project, reference, task, data JSON, workflow (Nháp → Đã nộp → Đã duyệt / Trả lại), PDF đã chốt | idx (project, template_code, state) |
| PM Document (+PM Document Version) | project, task, category, status (Nháp / Đã duyệt / Thay thế), current_version; mỗi phiên bản có file, ghi chú, checksum | PMD-.YYYY.-.##### |
| PM Alert Rule (+Escalation, +Recipient), PM Alert, PM Notification Preference | Xem mục 9 | PM Alert: unique (rule, reference, episode) |
| PM Resource Capacity, PM Performance Snapshot | Năng lực theo ngày; số liệu theo tuần cho người / đội / dự án | idx (user, week), (team, week) |
| PM Budget (+Line), PM Risk, PM Issue, PM Change Request | Mục 4.9 của prompt | M10 |

### 6.2. Lớp thi công `pm_construction`

| DocType | Nội dung |
|---|---|
| PMC BOQ / PMC BOQ Item | Bảng khối lượng có phiên bản: mã định mức, đơn vị, khối lượng, đơn giá, thành tiền, tách vật liệu/nhân công/máy, liên kết task; nhập từ Excel |
| PMC Material Norm (+Material) | Định mức vật tư theo mã định mức (vật tư, lượng / đơn vị, % hao hụt) |
| PMC Material Plan / PMC Material Usage | Kế hoạch vật tư theo công tác (sinh khi duyệt BOQ); sử dụng thực tế theo công tác |
| PMC Site Diary (+thời tiết / nhân lực / máy / công việc) | Nhật ký thi công: unique (project, ngày); có workflow, người lập, người xác nhận |
| PMC Acceptance Pack Template / PMC Acceptance | Nghiệm thu: loại, task, khối lượng nghiệm thu, các bên, biểu mẫu đi kèm, workflow |
| PMC Machine / PMC Machine Transfer / PMC Machine Shift | Máy (liên kết Asset hoặc thuê), đơn giá ca, định mức nhiên liệu; điều chuyển; nhật ký ca máy theo task |
| PMC Worker / PMC Crew Attendance (+lines) | Công nhân thời vụ (CCCD ở permlevel 1); chấm công theo tổ, ngày, task |

---

## 7. Phân quyền

1. **Capabilities toàn cục** (Staff Role Profile): `portfolio.view_all`, `project.create`, `perf.view_all`, `stock.cross_project`, `finance.view_all`, `master.manage`, `users.manage`.
2. **`project_scope(user)` → `(read_set|None, write_set|None, roles_by_project)`**, cache theo request.
   - read_set = PM Access ∪ Staff Group (apply_scope) ∪ thành viên đang hiệu lực. `None` nghĩa là xem tất cả dự án.
   - write_set = dự án có vai trò mang quyền ghi.
3. **Quyền trong một dự án:** `capabilities_in(project, user)` = quyền toàn cục ∪ quyền của vai trò dự án; kiểm bằng `assert_project_capability`.
4. **Chế độ "Được giao"** (tổ trưởng, nhà thầu phụ, khách): chỉ thấy task có `PM Task Assignment` của mình hoặc của đội mình.
5. **Role Frappe chỉ dùng làm nhóm quyền thô:**
   - PM User; PM Field (không vào Desk); PM External.
   - Stock / Purchase / Accounts User của ERPNext, gán theo `required_frappe_roles` khi lưu thành viên.
   - Trường chi phí ở permlevel 1.

**Nhóm quyền mặc định:**

| Nhóm | Phạm vi | Quyền chính |
|---|---|---|
| Quản trị hệ thống | Toàn bộ | Mọi quyền, `users.manage` |
| Giám đốc | Toàn bộ, chỉ đọc chi tiết | `portfolio.view_all`, `perf.view_all`, `finance.view_all` |
| Quản lý dự án | Dự án được giao | Lập kế hoạch, baseline, giao việc, duyệt, `perf.view_project` |
| Chỉ huy trưởng | Dự án | Giao việc, duyệt nhật ký, nghiệm thu, `perf.view_project` |
| Kỹ sư | Dự án | Cập nhật tiến độ, nhật ký, đề xuất vật tư, trao đổi |
| Tổ trưởng | Task được giao | Nhận việc, cập nhật tiến độ, chấm công tổ |
| Thủ kho | Kho của dự án | Nhập, xuất, chuyển kho, kiểm kê |
| Kế toán | Theo dự án hoặc `finance.view_all` | Chi phí, mua hàng (Desk) |
| Khách (CĐT/TVGS) | Dự án, chế độ được giao | Xem tiến độ, duyệt nghiệm thu (để sau) |

**Lọc theo phạm vi trên từng DocType:** một bộ điều hợp chung `project_query(doctype, column)` / `project_permission(doc)` cùng bản đồ `PARENT_OF`.
- Project: theo `name`.
- Task: theo `project`, cộng nhánh "Được giao".
- Mọi DocType PM/PMC: theo `project`.
- Timesheet: theo `parent_project`.
- Stock Entry: theo `project`; chuyển kho cần quyền ghi trên cả hai kho.
- Material Request: theo `pm_project`.
- PO/PR/PI: theo `project`.
- Warehouse, Location: theo `pm_project`.
- Asset Movement: theo `pm_project`.
- Asset: chỉ đọc cho thành viên.
- File: luôn là private; tải qua API của hệ thống (URL ký của MinIO).
- Meilisearch và realtime: lọc theo `read_set` ở server.

**Test CI bắt buộc:** mọi DocType có trường `project` đều phải có hook phân quyền.

**Ai xem được hiệu suất của ai:**
- Mỗi người xem được của chính mình.
- Tổ trưởng xem được đội mình.
- Người có `perf.view_project` xem trong dự án đó.
- Người có `perf.view_all` xem tất cả.

---

## 8. API và màn hình SPA

**API lõi** (`project_manager/api/`):
- Sao chép từ DM: `crud`, `meta`, `boot`, `users`, `permissions`, `logs`, `admin`, `reports`.
- Viết mới:
  - `projects` (tạo, nhân bản mẫu, thành viên, trạng thái, đóng dự án);
  - `wbs` (cây, thêm/sửa/di chuyển theo lô, nhập Excel);
  - `assignments` (giao, nhận, từ chối, thu hồi, lịch sử);
  - `progress` (ghi tiến độ có `client_uuid`, lý do chậm);
  - `schedule` (phụ thuộc, CPM, xem trước dời lịch, baseline, đường cong S);
  - `activity` (dòng thời gian, comment, @mention, đánh dấu đã đọc);
  - `media` / `documents`;
  - `forms` (mẫu, phiên bản, nộp, duyệt, PDF, Excel);
  - `alerts` (danh sách, xác nhận, quy tắc);
  - `perf`, `portfolio`, `exchange` (Excel, MS Project XML);
  - `sync` (nhận lô từ hàng đợi offline).

**API thi công** (`pm_construction/api/`): `boq`, `diary`, `acceptance`, `materials`, `machines`, `labour`.

**Màn hình SPA** (`/pm/...`). 📱 = ưu tiên điện thoại:

| Route | Mục đích |
|---|---|
| `/pm` | Trang chủ theo vai trò: việc của tôi, cảnh báo, dự án 📱 |
| `/pm/viec-cua-toi` | Việc được giao, nhận/từ chối, cập nhật nhanh 📱 |
| `/pm/du-an` | Danh sách dự án, tạo từ mẫu |
| `/pm/du-an/:id/tong-quan` | Sức khỏe, tiến độ, đường cong S, cảnh báo 📱 |
| `/pm/du-an/:id/wbs` | Cây WBS, giao việc, RACI |
| `/pm/du-an/:id/kanban` | Kanban 📱 |
| `/pm/du-an/:id/gantt` | Gantt (điện thoại: chỉ đọc, độ sâu ≤ 3) |
| `/pm/du-an/:id/lich` | Lịch thi công 📱 |
| `/pm/du-an/:id/ai-lam-gi` | Ai đang làm gì, chậm ở đâu |
| `/pm/du-an/:id/trao-doi` | Dòng thời gian dự án 📱 |
| `/pm/du-an/:id/tai-lieu` | Tài liệu dự án |
| `/pm/du-an/:id/bieu-mau` | Biểu mẫu đã nộp và chờ duyệt 📱 |
| `/pm/du-an/:id/thanh-vien` | Thành viên và vai trò |
| `/pm/du-an/:id/baseline` | Baseline, so sánh kế hoạch với thực tế |
| `/pm/cong-viec/:id` | Chi tiết task: tiến độ, trao đổi, ảnh, biểu mẫu 📱 |
| `/pm/canh-bao` | Cảnh báo của tôi 📱 |
| `/pm/hang-doi` | Hàng đợi gửi offline 📱 |
| `/pm/danh-muc-du-an` | Dashboard nhiều dự án |
| `/pm/hieu-suat`, `/pm/khoi-luong-cong-viec` | Hiệu suất, workload |
| `/pm/bieu-mau-mau` | Thiết kế mẫu biểu mẫu |
| `/pm/bao-cao[/:slug]` | Báo cáo (sao chép ReportsHub và ReportPage) |
| `/pm/quan-tri/*` | Người dùng, nhóm quyền, vai trò dự án, quy tắc cảnh báo, nhật ký, giám sát, cài đặt (sao chép) |
| `/pm/danh-muc/:slug` | Danh mục dùng chung (MasterPage/MasterTree) |
| Thi công: `/pm/du-an/:id/boq` | Bảng khối lượng |
| Thi công: `/pm/du-an/:id/nhat-ky` | Nhật ký thi công 📱 |
| Thi công: `/pm/du-an/:id/nghiem-thu` | Nghiệm thu 📱 |
| Thi công: `/pm/du-an/:id/vat-tu` | Vật tư 📱 |
| Thi công: `/pm/du-an/:id/may` | Máy thi công 📱 |
| Thi công: `/pm/du-an/:id/cham-cong` | Chấm công 📱 |
| Thi công: `/pm/dinh-muc` | Định mức vật tư |
| Thi công: `/pm/doi-thi-cong` | Tổ đội thi công |

---

## 9. Tự động hóa

**Cộng dồn tiến độ:**
1. Mixin đánh dấu node cha cần tính lại bằng `SADD pm:dirty:{project}`, rồi enqueue `rollup_project` với `job_id=pm-rollup:{project}`, `deduplicate=True`, chạy sau commit.
2. Job xử lý từng cấp lên trên, mỗi cấp một câu `GROUP BY parent_task` gom: tổng trọng số, tổng (trọng số × tiến độ), ngày sớm nhất/muộn nhất, đếm trạng thái, PV, EV. Chỉ ghi những dòng có thay đổi. Độ sâu ≤ 6 nên tối đa 6 câu truy vấn. Mọi thao tác ghi được bọc trong `retry_on_deadlock`.
3. Cron mỗi 5 phút gom các khóa còn sót. Job đối soát hằng đêm (queue long) tính lại toàn cây và ghi số chỗ lệch đã sửa.
4. `pm_rollup_weight` của task lá được tính trong `validate`, theo phương pháp: thời lượng / task_weight / bằng nhau / thủ công. Lớp thi công thêm phương pháp **giá trị dự toán** (khối lượng × đơn giá), với tiến độ = khối lượng đã làm / khối lượng thiết kế.

**Chuyển giai đoạn:**
- Node giai đoạn có `pm_gate_mode`: Tự động / Cần duyệt / Thủ công.
- Kiểm điều kiện khi rollup đánh dấu giai đoạn đã xong, hoặc khi một biểu mẫu được duyệt.
- Đủ điều kiện thì đóng giai đoạn, mở giai đoạn kế tiếp, cập nhật `pm_current_phase`, ghi activity và gửi thông báo.
- Chế độ "Cần duyệt" thì báo quản lý dự án xác nhận.
- Lớp thi công thêm điều kiện qua `gate_checks`, ví dụ mọi nghiệm thu đã duyệt.

**Dự báo trễ** (task lá đang chạy; chạy hằng đêm và sau mỗi lần ghi tiến độ):
- Tiến độ kế hoạch hôm nay: `p = wd(S,t)/wd(S,E)`, với `wd` là số ngày làm việc.
- Tốc độ: `r = 0.6·Δtiến độ 14 ngày/wd(14 ngày) + 0.4·tiến độ/wd(A,t)`, với A là ngày bắt đầu thực tế.
- Ngày hoàn thành dự báo: `F = t + ⌈(100−tiến độ)/r⌉` ngày làm việc. Độ trễ: `slip = wd(E,F)`. `SPI = tiến độ/(100·p)`.
- **Đỏ:** slip vượt max(ngưỡng, 10% thời lượng), hoặc SPI < 0.8, hoặc task trên đường găng có slip > 0.
- **Vàng:** slip > 0 hoặc SPI < 0.95.
- **Đình trệ:** `r = 0` và không cập nhật quá N ngày.
- Sức khỏe dự án lấy mức xấu nhất. Xấu đi thì đổi ngay; tốt lên phải ổn định 3 ngày liên tiếp mới đổi.

**Đường găng:**
- Sắp xếp tô-pô (Kahn), tìm ra vòng lặp nếu có.
- Lượt xuôi và lượt ngược cho FS/SS/FF/SF có lag, theo chỉ số ngày làm việc từ Holiday List.
- Ghi `pm_total_float` và `pm_is_critical`.
- Job `pm-cpm:{project}` (debounce) chạy khi đổi phụ thuộc hoặc ngày, và hằng đêm.
- Dời các task phía sau: mặc định hiển thị bản xem trước để người dùng xác nhận.

**Cảnh báo:**
- **Loại quy tắc:** sắp đến hạn, quá hạn, nguy cơ trễ, chậm trên đường găng, đổi sức khỏe, chưa nhận việc, không cập nhật, biểu mẫu chờ duyệt. Lớp thi công thêm: vượt định mức vật tư, thiếu nhật ký.
- **Mỗi quy tắc có:** tham số, loại node áp dụng, người nhận (A / R / Duyệt / người theo dõi / vai trò dự án / cấp trên `reports_to`), kênh, quiet hours, các bậc leo thang (sau X ngày → vai trò Y).
- **Đánh giá:**
  - Quy tắc theo thời gian: cron 06:00.
  - Nguy cơ trễ: sau job dự báo hằng đêm.
  - Quy tắc theo sự kiện: chạy trong hook.
  - Leo thang: cron mỗi giờ.
- **Tóm tắt:** 07:00 hằng ngày và sáng thứ Hai hằng tuần.
- **Chống gửi trùng:** unique (rule, reference, episode) + Redis `SET NX` 24 giờ. Chỉ gửi khi cảnh báo mới hoặc tăng bậc.

**Hàng đợi:**
- `pm`: rollup, CPM, phát thông báo, cập nhật index.
- `default`: cảnh báo theo sự kiện, ảnh thu nhỏ, PDF biểu mẫu, tóm tắt.
- `long`: đối soát, snapshot, hiệu suất, baseline, nhập/xuất, nhân bản WBS lớn, dựng lại index.

---

## 10. Lộ trình

Quy ước cỡ việc: S ≤ 2 tuần, M 3–5 tuần, L 6–8 tuần (đội nhỏ). Mỗi phase ghi `docs/build-log/NN-*.md` và cập nhật `TRACEABILITY.md`.

**DoD chung cho mọi phase:**
- Test Python, vitest, e2e HTTP và browser flow (kích thước máy tính và điện thoại) đều xanh.
- Image được build lại.
- **Clone sang thư mục mới, chạy bootstrap, toàn bộ chức năng của phase hoạt động.**
- Có checklist demo kèm URL.
- Dừng lại chờ người dùng duyệt. Chỉ commit khi người dùng yêu cầu.

### M0 — Khởi tạo repo tự đủ (S)
- **Nội dung:**
  - Repo, `.gitattributes`, `.gitignore`, `.dockerignore`, compose và Dockerfile sao chép từ DM (mục 3), image `pm-custom:v16.26.2`.
  - Hai app rỗng (`bench new-app` chạy trong container rồi đưa ra repo; `pm_construction` có `required_apps = ["erpnext", "project_manager"]`).
  - `.env.example`, `bootstrap.ps1` + `bootstrap.sh` (mục 14).
  - Service `setup-site` gọi `frappe.desk.page.setup_wizard.setup_wizard.setup_complete(args)`; nếu đã cài thì bỏ qua.
  - Company, Fiscal Year, kho gốc, Holiday List từ `.env`.
  - Trang `/pm` trả SPA rỗng.
  - CI: static (gồm lint ranh giới, cấm đường dẫn tuyệt đối), frontend, test, clean-clone, publish GHCR.
- **Test:** `test_bootstrap_defaults` (Company, Fiscal Year, kho tồn tại; setup wizard đã xong).
- **DoD:** `git clone` → `bootstrap` → mở `http://localhost:8890/pm` và `/desk`, đăng nhập được. Chạy được cùng lúc với stack DM. Chạy bootstrap lần hai không lỗi.
- **Rủi ro:** setup wizard ERPNext thay đổi tham số giữa các bản vá → ghim tag, có test.

### M1 — Nền tảng chung (M)
- **Nội dung:**
  - Sao chép `policy` → `project_scope` / `capabilities_in`, bộ điều hợp quyền, Staff Role Profile, Staff Group, PM Access, `permission_matrix`.
  - `PM Project Role`, `PM Project Member`.
  - Hook quyền trên Project, Task và mọi PM DocType.
  - Audit, notify, health, errors, queries, crud/meta/boot/users/permissions/logs/admin.
  - Khung SPA ưu tiên điện thoại; trang quản trị sao chép.
  - **Mixin Task** (mục 4.2) kèm contract test; dừng job overdue.
  - `PM Node Type`, đánh số cây theo dự án.
  - Ghi `PM Activity` (chưa có giao diện).
  - **Bộ sinh dữ liệu 1 triệu task** + `volume_check.py`.
  - **Spike Gantt** (D11): báo cáo so sánh, người dùng chọn thư viện.
- **Test:** test_policy, test_project_scope (gồm truy cập qua `/api/resource`, `frappe.client`, `report_view`), test_task_mixin, test_hook_coverage, test_permission_matrix.
- **DoD:** người ngoài dự án không thấy Project/Task của dự án đó qua bất kỳ đường nào; thêm task trên site 1 triệu dòng < 300 ms; đã chốt thư viện Gantt.
- **Rủi ro:** mixin xung đột với code ERPNext → contract test; thử trên site perf.

### M2 — Dự án, WBS, giao việc rõ trách nhiệm (L) · prompt 4.1, 4.3 (rollup), 4.10 (nhập Excel)
- **Nội dung:**
  - Tạo dự án từ mẫu (nhân bản hàng loạt).
  - Cây WBS (thêm, sửa, di chuyển theo lô, mã WBS).
  - `PM Team`, `PM Task Assignment` (RACI, đúng một A, nhận/từ chối kèm lý do, thu hồi).
  - Lịch sử giao việc và đổi deadline ghi vào `PM Activity`.
  - Mã lý do chậm và khâu gây chậm bắt buộc khi task trễ.
  - `PM Progress Entry`.
  - **Rollup v1 + đối soát**; snapshot hằng ngày bắt đầu chạy.
  - Danh sách, Kanban, Việc của tôi, Ai làm gì.
  - Thông báo đến hạn và quá hạn đơn giản.
  - Nhập WBS từ Excel (có chạy thử).
- **Test:** test_assignment (unique A, từ chối, lịch sử không xóa được), test_rollup (từng phương pháp, đối soát, chạy đồng thời), test_wbs_move, e2e giao việc → nhận → cập nhật → tiến độ cha đổi.
- **DoD:** cập nhật tiến độ một task lá → dự án đổi % trong < 5 s; dự án 2.000 task.

### M3 — Biểu mẫu động (M) · prompt 4.8
- **Nội dung:**
  - `PM Form Template` có phiên bản; trình thiết kế trường.
  - `PM Form Submission` + workflow; in PDF đã chốt; xuất Excel; ảnh và chữ ký.
  - `PM Gate Requirement` mức đóng việc: task bắt buộc biểu mẫu đã duyệt mới đóng được.
  - Gói mẫu chung (checklist).
- **Test:** test_forms (đổi phiên bản không làm hỏng bản đã nộp, validate theo kiểu trường, quyền duyệt), test_gate_close.
- **DoD:** tạo mẫu nghiệm thu → nộp trên điện thoại → duyệt → task đóng được.

### M4 — Lịch trình và tiến độ trực quan (L) · prompt 4.2
- **Nội dung:**
  - `PM Task Dependency` (FS/SS/FF/SF, lag, phát hiện vòng lặp); CPM ở server; xem trước dời lịch.
  - Gantt theo thư viện đã chọn (kéo-thả, đường găng, so với baseline).
  - Lịch thi công.
  - Baseline nhiều phiên bản; đường cong S từ snapshot.
  - Dự báo ngày hoàn thành.
- **Test:** test_cpm (bộ test vector dùng chung server và client), test_baseline, perf Gantt 2.000 task < 2 s.
- **DoD:** chụp baseline → dời một task găng → Gantt hiện chênh lệch, ngày hoàn thành dự án dự báo thay đổi.

### M5 — Trao đổi theo đầu việc, tài liệu, offline nền (M) · prompt 4.7, 3.5
- **Nội dung:**
  - Giao diện dòng thời gian (comment, @mention, ảnh, tệp, tiến độ kèm ghi chú, thay đổi trường).
  - `PM Follow` (theo dõi, đã đọc); realtime qua room tài liệu.
  - `PM Media`: nén ảnh ở client ≤ 1600 px, thumbnail chạy nền, GPS và thời điểm chụp.
  - `PM Document` có phiên bản và duyệt; xem trước, tải qua URL ký.
  - Meilisearch cho trao đổi và tài liệu.
  - **PWA + hàng đợi gửi lại** (service worker, IndexedDB, `client_uuid`, màn hình hàng đợi; trên iOS gửi khi mở lại app).
- **Test:** test_activity (lọc quyền, phân trang keyset, idempotency), test_documents, vitest outbox, e2e điện thoại mất mạng rồi có mạng.
- **DoD:** chụp ảnh khi tắt mạng → bật mạng → ảnh lên đúng task, không bị trùng.

### M6 — Lớp thi công cơ bản (L) · prompt 4.2, 4.8
- **Nội dung:**
  - App `pm_construction`: node type thi công.
  - BOQ (nhập Excel, phiên bản, sinh WBS hạng mục/công tác); tiến độ theo khối lượng và phương pháp `estimate_value`.
  - Nhật ký thi công (offline, ảnh, ký xác nhận).
  - Nghiệm thu (gói mẫu: công việc, giai đoạn, an toàn, bàn giao mặt bằng).
  - Màn hình thi công tích hợp vào SPA qua `spa_modules`.
- **Test:** test_boq_import, test_quantity_rollup, test_site_diary, test_acceptance; **CI chạy test lõi khi không cài `pm_construction`**.
- **DoD:** nhập BOQ mẫu → WBS có khối lượng → nhập khối lượng hằng ngày qua nhật ký → tiến độ dự án tính theo giá trị dự toán.

### M7 — Cảnh báo thông minh, chuyển giai đoạn, sức khỏe (M) · prompt 4.3, 4.6 v1 → **THÍ ĐIỂM**
- **Nội dung:**
  - `PM Alert Rule/Alert` (loại quy tắc, người nhận, leo thang, quiet hours), dự báo trễ, sức khỏe Xanh/Vàng/Đỏ.
  - Tóm tắt ngày và tuần; email (tùy chọn SMTP).
  - Chuyển giai đoạn theo điều kiện; dashboard nhiều dự án v1.
  - Kịch bản demo và tài liệu hướng dẫn thí điểm.
- **Test:** test_alerts (chống trùng, leo thang, quiet hours), test_forecast, test_phase_gate, e2e trọn luồng thí điểm.
- **DoD:** dữ liệu mẫu công trình cho thấy cảnh báo trễ, leo thang sau X ngày, giai đoạn tự chuyển khi nghiệm thu được duyệt.

### M8 — Vật tư, máy, nhân công (L) · prompt 4.5
- **Nội dung:**
  - Kho công trường; đề xuất vật tư (MR có `pm_project` và `pmc_task`) → PO/PR → cấp phát Stock Entry theo công tác → sử dụng thực tế → hoàn trả/hao hụt.
  - So sánh định mức với thực tế; cảnh báo vượt định mức.
  - Máy (`PMC Machine`, điều chuyển tạo Asset Movement, ca máy, bảo dưỡng).
  - Tổ đội, công nhân, chấm công theo task.
  - Chi phí thực tế so với dự toán.
  - Phân quyền theo dự án trên DocType kho và mua hàng.
- **Test:** test_material_flow, test_stock_scope (thủ kho dự án A không thấy kho B), test_machine_shift, test_cost_rollup.
- **DoD:** kỹ sư đề xuất trên điện thoại → thủ kho cấp phát → báo cáo định mức so với thực tế đúng.

### M9 — Hiệu suất, workload, nhiều dự án v2 (M) · prompt 4.4, 4.6
- **Nội dung:**
  - `PM Performance Snapshot` (tỷ lệ đúng hạn, khối lượng, năng suất = khối lượng / công).
  - Workload và năng lực theo tuần; cảnh báo quá tải.
  - Xung đột người và máy giữa các dự án.
  - Portfolio v2; giới hạn ai xem hiệu suất của ai.
- **Test:** test_perf_visibility, test_workload, perf dashboard 50 dự án < 2 s.

### M10 — Báo cáo, nhập/xuất, ngân sách, rủi ro, phát sinh (M) · prompt 4.9, 4.10
- **Nội dung:**
  - Báo cáo tiến độ, hiệu suất, vật tư, chi phí (CSV/XLSX/PDF, gửi theo lịch).
  - Nhập/xuất MS Project XML.
  - Ngân sách/EVM; sổ rủi ro và vấn đề; change request có duyệt.
  - Điểm mở rộng cho cầu nối lưu trữ: sự kiện `project_close_handlers` + API xuất gói hồ sơ dự án (ZIP + manifest).

### M11 — Hardening và triển khai (M)
- **Nội dung:**
  - Volume check đầy đủ (mục 12); load test 200 người cập nhật tiến độ đồng thời.
  - Rà soát bảo mật: liệt kê endpoint theo từng role; XSS (Jinja autoescape, `inline_json`); upload.
  - Triển khai prod qua `prod_compose.py`; diễn tập sao lưu và khôi phục sang máy khác.
  - Tài liệu: README, DEPLOYMENT, HIEU_NANG, hướng dẫn sử dụng.

**Để sau** (ngoài lộ trình): cổng CĐT/TVGS, `pm_archive_bridge` (repo riêng), AI (Claude API), Zalo/SMS.

---

## 11. Kiểm thử và CI

- **Python:** `PMTestCase` (savepoint mỗi test, vô hiệu `frappe.db.commit`, `_forget_caches`, mock `enqueue`/Meilisearch) đặt trong `tests/helpers.py`; dữ liệu tự tạo với tiền tố duy nhất.
- **Vitest** cho `lib/` và component; **Playwright** `.mjs` ở hai kích thước màn hình (máy tính và điện thoại 390×844); **e2e HTTP** liệt kê endpoint theo từng role.
- **Tài khoản e2e** tạo bằng `scripts/e2e/accounts.py up/down`, đọc site từ `.env`.
- **Job CI:**
  1. `static`: ruff, compileall, JSON, `node --check`, `docker compose config`; lint cấm `pm_construction` trong lõi; cấm đường dẫn tuyệt đối và `../`; kiểm `.env.example` đủ biến.
  2. `frontend`: `npm ci`, test, build.
  3. `test-core`: site chỉ có ERPNext + `project_manager`.
  4. `test-full`: site có cả hai app.
  5. `clean-clone`: checkout sạch → `bootstrap.sh --non-interactive --seed-demo` → e2e HTTP smoke → kiểm cấu hình mặc định.
  6. `publish`: GHCR `ghcr.io/<owner>/pm-custom` khi push lên main hoặc tag.
- **Windows** không chạy được container Linux trên GitHub runner, nên `bootstrap.ps1` được kiểm thủ công trên máy Windows trong checklist của mỗi phase.

## 12. Hiệu năng

- **Bộ sinh dữ liệu** (`scripts/perf/volume_check.py`, chỉ chạy trên site có tên bắt đầu `perf`): 50 dự án đang chạy và 450 dự án đã đóng; 1 triệu task (mỗi dự án 2.000–20.000); 5 triệu activity; 2 triệu media (chỉ metadata); 100 nghìn Stock Entry; 500 người dùng; thời gian rải đều.
- **Ngưỡng chấp nhận:**

| Thao tác | Ngưỡng |
|---|---|
| Gantt 2.000 task (API + render) | < 2 s |
| Kanban 500 task | < 1 s |
| Rollup sau cập nhật | < 5 s |
| Dashboard 50 dự án | < 2 s |
| Danh sách phân trang sâu (keyset) | < 1 s |
| Thêm task | < 300 ms |
| Dòng thời gian 50 mục | < 500 ms |
| 200 cập nhật tiến độ đồng thời | Không deadlock, không mất dữ liệu |

Kết quả ghi trong `docs/HIEU_NANG.md`.

## 13. Triển khai

- **Dev:** `bootstrap`, sau đó dùng compose dev (watcher, autoreload, spa-watch).
- **Prod:** image lấy từ GHCR; `.env.prod` (chmod 600) kiểm bằng `validate_prod_env.py`; `prod_compose.py` (tùy chọn overlay MinIO và bind mount); nginx phía trước có TLS.
- **Sao lưu:** `bench backup --with-files` + bucket MinIO (mirror); runbook khôi phục sang máy khác trong `docs/SAO_LUU_KHOI_PHUC.md`.
- **Nâng cấp ERPNext:** chạy contract test của mixin, diff `task.py`/`project.py`/`timesheet.py`/`nestedset.py`, chạy toàn bộ test trên bản sao dữ liệu prod, rồi mới đổi tag.
- **Chạy cùng máy với DM:** khác port, tên compose, tiền tố volume, site (D20); không dùng chung network.

## 14. Repo tự đủ

**Phiên bản ghim:**
- `frappe/erpnext:v16.26.2` (Frappe 16.26.3, Python 3.14.2).
- `node:<LTS cụ thể>-slim` cho stage SPA: chốt ở M0, không dùng Node 20 vì đã hết hỗ trợ.
- `mariadb:11.8.<patch>`, `redis:7.4.<patch>-alpine`, `getmeili/meilisearch:v1.12.<patch>`.
- MinIO build từ nguồn với tag RELEASE ghim (như DM).
- Commit `package-lock.json` (SPA và e2e).

**`.env.example`:**
- **Hạ tầng:** `COMPOSE_PROJECT_NAME=pmdev`, `DATA_VOLUME_PREFIX=pm`, `FRAPPE_SITE_NAME=pm.localhost`, `HTTP_PUBLISH_PORT=8890`, `ERPNEXT_VERSION=v16.26.2`.
- **Secret, để trống và để bootstrap tự sinh:** `ADMIN_PASSWORD`, `MARIADB_ROOT_PASSWORD`, `MEILISEARCH_MASTER_KEY`, `MINIO_ROOT_PASSWORD`, `MINIO_APP_SECRET_KEY`.
- **MinIO:** `MINIO_ROOT_USER`, `MINIO_APP_ACCESS_KEY`, `MINIO_BUCKET=pm-files`.
- **Công ty:** `COMPANY_NAME`, `COMPANY_ABBR`, `COUNTRY=Vietnam`, `CURRENCY=VND`, `TIMEZONE=Asia/Ho_Chi_Minh`, `LANGUAGE=vi`, `FY_START=01-01`.
- **Tùy chọn:** `SMTP_*`, `SEED_DEMO=0`.
- **Gunicorn và nginx:** `GUNICORN_*`, `CLIENT_MAX_BODY_SIZE`.

**Các bước bootstrap** (`bootstrap.ps1` / `bootstrap.sh`, tham số `--seed-demo`, `--non-interactive`):
1. Kiểm Docker 24+ và Compose v2, RAM ≥ 8 GB; báo rõ nếu thiếu.
2. Tạo `docker/.env` từ mẫu nếu chưa có; sinh secret ngẫu nhiên cho các biến trống. Không ghi đè giá trị đã có.
3. `docker compose build`.
4. `up -d` db, redis, meilisearch, minio; chờ healthcheck.
5. `run --rm configurator`; `run --rm create-site` (bỏ qua nếu site đã có; cài `erpnext`, `project_manager`, `pm_construction`).
6. `run --rm setup-site`: setup wizard idempotent, rồi `migrate`.
7. `up -d` toàn bộ; chờ `/api/method/ping` và endpoint health của hệ thống.
8. Tùy chọn: seed dữ liệu công trình mẫu (`scripts/demo/seed_demo.py up`; gỡ bằng `down`).
9. In URL `/pm`, `/desk`, tên tài khoản và chỗ lấy mật khẩu (`docker/.env`). Không in secret ra log CI.

**Cấu hình mặc định bằng code** (`after_install`/`after_migrate` → `seed_all`, idempotent):
- Role và nhóm quyền mặc định, PM Project Role, capabilities.
- Custom field và Property Setter (fixtures), index (patch).
- Workflow (biểu mẫu, nhật ký, nghiệm thu, change request).
- PM Node Type, mã lý do chậm, khâu gây chậm.
- Quy tắc cảnh báo mặc định, mẫu biểu mẫu và mẫu dự án mẫu.
- Dừng job `set_tasks_as_overdue`; PM Settings mặc định.
- Thi công: node type, gói nghiệm thu, Stock Entry Type, Item Group "Vật tư xây dựng".

**Checklist kiểm chứng trên máy khác** (mỗi phase):
- Clone vào thư mục mới trên Windows và trên Linux/macOS.
- Chạy bootstrap, đăng nhập, chạy checklist demo của phase.
- Chạy bootstrap lần hai.
- Không có bước nào ngoài README.

## 15. Rủi ro chính

1. **ERPNext nâng cấp làm vỡ mixin:** ghim tag, contract test, runbook so sánh mã nguồn.
2. **Gantt chậm trên điện thoại:** spike M1; trên điện thoại chỉ đọc và lazy-load; CPM tính ở server.
3. **Ghi dây chuyền, deadlock, mất cập nhật:** mixin, job gộp theo dự án, `set_value`, `retry_on_deadlock`, load test.
4. **Rò quyền qua endpoint chung** (`/api/resource`, `frappe.client`, `report_view`, tệp, tìm kiếm, realtime): hook trên mọi DocType, test kiểm độ phủ hook, e2e liệt kê endpoint.
5. **Dữ liệu lớn** (5 triệu activity, nhiều ảnh): autoincrement, keyset, `capped_count`/`bounded_scan`, nén ảnh, lifecycle rule cho MinIO.
6. **Offline phình phạm vi:** chỉ cho dữ liệu ghi thêm (D12); màn hình hàng đợi; giới hạn của iOS.
7. **Ranh giới lõi/thi công bị xói mòn:** lint, `test-core`, hợp đồng `pm_extensions` có phiên bản.
8. **Kho ERPNext khó với người ở công trường:** điện thoại chỉ tạo đề xuất; thủ kho xác nhận; danh mục vật tư nhập sẵn kèm mã định mức.

## 16. Câu hỏi mở cho người dùng

D1, D11, D12, D15, D16, D18, D19 đã chốt với người dùng. Còn lại, không chặn M0:
1. Thông tin Company mặc định cho bootstrap: tên, viết tắt. Nếu chưa có thì `.env.example` dùng "Công ty Xây dựng Mẫu" / "CTXD", năm tài chính bắt đầu tháng 1, và người dùng sửa trong `.env`.
2. Có mẫu biểu mẫu nghiệm thu hoặc nhật ký thi công thực tế (Excel/Word) để làm gói mẫu ở M3/M6 không?
3. Có file BOQ/dự toán mẫu (từ phần mềm dự toán phổ biến) để thiết kế bộ nhập ở M6 không?
4. Email gửi thông báo dùng SMTP nào (có thể để sau M7)?

---

## Xác minh khi thực hiện

- **Mỗi phase:**
  - Chạy `bench --site pm.localhost run-tests --app project_manager` và `--app pm_construction` trong container; `npm test` trong `frontend/`.
  - Chạy `python scripts/e2e/e2e_http.py http://localhost:8890` và các flow Playwright (`PW_CHANNEL=msedge`).
  - Clone sạch sang thư mục tạm, chạy `bootstrap.ps1` trên Windows, kiểm checklist demo bằng browser pane.
- **Hiệu năng:** M1 và M11 chạy `volume_check.py seed/measure` trên site `perfpm.localhost`; các phase có thay đổi truy vấn nóng thì đo lại.
- **CI:** job `clean-clone`, `test-core`, `test-full` xanh trước khi người dùng yêu cầu commit.
- **Sau khi người dùng duyệt kế hoạch:** bắt đầu M0. Lưu bản kế hoạch này vào `docs/KE_HOACH.md` của repo mới ngay trong M0. Các quyết định ⚙️ được kiểm chứng ở M1 (perf site 1 triệu task); nếu không đạt thì báo lại trước khi đổi hướng.
