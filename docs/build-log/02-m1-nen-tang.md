# M1 — Nền tảng chung

## 1. Mục tiêu

Theo [KE_HOACH.md](../KE_HOACH.md), M1 gồm:
- phân quyền theo dự án từ đầu (capabilities toàn cục + vai trò trong từng dự án), áp cả lên Project và Task của ERPNext;
- tắt các hành vi của ERPNext không hợp với quy mô lớn (mixin Task);
- các service và API khung sao chép từ `document_manager`;
- khung SPA ưu tiên điện thoại với các trang quản trị;
- bộ sinh 1 triệu công việc để đo hiệu năng;
- spike chọn thư viện Gantt.

## 2. DocType đã tạo

Tất cả nằm trong module "Project Manager" và đều có tiền tố `PM `, để không trùng tên với `document_manager` nếu sau này cài chung một site.

| DocType | Mục đích | Trường chính |
|---|---|---|
| PM Settings (Single) | Thiết lập hệ thống | `enable_audit_log`, `audit_retention_days` (≥ 7) |
| PM Role Profile (+PM Role Capability) | Nhóm quyền toàn cục = một Frappe Role kèm các chức năng | `role`, `label`, `group_label`, `is_builtin`, `is_admin`, `capabilities` |
| PM Group (+PM Group Member, PM Group Role, PM Access Project) | Nhóm nhân viên: cấp nhóm quyền đồng loạt, có thể cấp phạm vi dự án | `roles`, `members`, `apply_scope`, `read_scope`/`read_projects`, `write_scope`/`write_projects` |
| PM Access (+PM Access Project) | Phạm vi riêng của một người, ngoài các dự án họ tham gia | `user`, `read_scope`, `write_scope`, danh sách dự án |
| PM Project Role | Vai trò trong dự án | `task_visibility` (Tất cả / Chỉ việc được giao), `capabilities`, `required_roles` |
| PM Project Member | Thành viên dự án | `project`, `user`, `project_role`, `is_active`, `valid_from`/`valid_to`; index `(user, is_active)`, `(project, project_role)` |
| PM Node Type | Loại nút WBS | `is_group`, `counts_in_rollup`, `requires_accountable`, `default_gate_mode` |
| PM Activity | Dòng thời gian dự án; không sửa được, chỉ ghi qua `services/activity.py` | `project`, `reference_doctype/name`, `task`, `activity_type`, `actor`, `content`, `data` (JSON), `client_uuid` (unique) |
| PM Audit Log | Nhật ký hệ thống | `activity_type`, `reference_*`, `user`, `ip_address`, `timestamp`, `description` |

**Custom field** (tạo bằng code trong `setup/install.py`):
- Project: `pm_code`, `pm_state`, `pm_manager`.
- Task: `pm_node_type`, `pm_wbs_code`, `pm_path`, `pm_sort`, `pm_level`.
- Index Task: `(project, pm_path)`, `(project, parent_task)`.
- Property Setter: `percent_complete_method` mặc định là `Manual`.

**Dữ liệu mặc định** (idempotent; không ghi đè thứ quản trị viên đã sửa):
- 3 nhóm quyền: Quản trị hệ thống, Giám đốc, Nhân viên.
- 7 vai trò dự án: Quản lý dự án, Chỉ huy trưởng, Kỹ sư, Tổ trưởng, Thủ kho, Kế toán dự án, Khách.
- 5 loại nút WBS.
- Quyền của 3 nhóm trên Project/Task (Custom DocPerm), giữ nguyên quyền gốc của ERPNext.
- Dừng job `set_tasks_as_overdue` của ERPNext.

## 3. File chính

| File | Nội dung |
|---|---|
| `project_manager/policy.py` | Nguồn duy nhất cho quyền (xem mục 4) |
| `project_manager/permissions.py` | `permission_query_conditions` và `has_permission` cho Project, Task, PM Project Member, PM Activity |
| `project_manager/overrides/task.py` | `PMTaskMixin` qua `extend_doctype_class`, kèm danh sách `OVERRIDDEN` |
| `project_manager/services/wbs.py` | Đường dẫn cây theo dự án: `place`, `carry_subtree`, `rebuild` |
| `project_manager/services/` | `errors`, `queries`, `permission_matrix`, `audit`, `notify`, `health`, `ui`, `activity`, `web` |
| `project_manager/api/` | `crud`, `meta`, `boot`, `users`, `permissions`, `logs`, `admin`, `account` |
| `project_manager/setup/install.py` | `seed_all()` gọi từ `after_install`/`after_migrate` |
| `frontend/src/` | Khung SPA (AppShell, SidebarNav, CommandPalette, RecordDrawer, FormRenderer...); trang Tổng quan, Danh mục, Người dùng, Phân quyền, Nhật ký, Giám sát, các màn quản trị dùng form chung; `ProjectPicker` thay `FondsPicker`; màu thương hiệu navy + amber |
| `scripts/perf/volume_check.py` | Sinh và đo 1 triệu công việc |
| `spikes/gantt/` | Spike Gantt (không thuộc app) |

Mã sao chép từ `document_manager` được ghi trong [NGUON_GOC.md](../NGUON_GOC.md).

## 4. Quyết định kỹ thuật

**Phân quyền hai lớp:**
- *Nhóm quyền* (Frappe Role + PM Role Profile) cho chức năng toàn cục, ví dụ `portfolio.view_all`, `project.create`.
- *Vai trò dự án* (PM Project Role, qua PM Project Member) cho chức năng trong từng dự án, ví dụ `plan.edit`, `task.assign`, `task.update`, `project.members`.
- `policy.get_access(user)` trả về các tập dự án được xem, được sửa, và tập dự án được thấy công việc.
- `policy.capabilities_in(project)` trả về chức năng trong một dự án.
- Mọi danh sách, báo cáo, tìm link và `/api/resource` đều đi qua cùng một điều kiện SQL `project IN (...)`.

**Phạm vi mặc định:** một người chỉ thấy các dự án mình tham gia. PM Access hoặc PM Group *cấp thêm*: mọi dự án, hoặc một số dự án chọn sẵn, chỉ xem hay được sửa.

**Đường dẫn cây thay cho nested set** (D4 đã chốt, đổi từ `pm_lft/pm_rgt`):
- Thêm hoặc di chuyển chỉ chạm vào dữ liệu của một dự án.
- Di chuyển một nhánh là một câu UPDATE.
- Đo trên 1 triệu task: thêm mới 9 ms; cập nhật toàn bảng kiểu nested set mất 1,2–1,4 s.

**Mixin Task:** các method bị ghi đè được liệt kê và có contract test với ERPNext. Rollup tiến độ (ghi đè `update_project`) để trống tới M2. ERPNext đặt `percent_complete_method` về Manual nên không còn tự đếm lại tiến độ.

**Timesheet không ghi đè trạng thái:** trong lúc Timesheet được submit hoặc cancel, có cờ bật lên; mixin giữ lại status và progress do đội dự án đặt.

**Tên DocType có tiền tố `PM`:** tránh trùng `Staff Role Profile`, `Business Activity Log`... của `document_manager`.

**Chế độ "Chỉ việc được giao"** (Tổ trưởng, Khách): người có vai trò này thấy dự án nhưng *chưa thấy công việc nào*. Phần này cần `PM Task Assignment`, sẽ làm ở M2. Hiện tại an toàn theo hướng chặn bớt (không lộ dữ liệu).

## 5. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **62/62** |
| Trong đó `test_project_scope` (24) | Gồm truy cập qua `frappe.client.get_list`, `reportview.execute`, `frappe.client.get`, `search_link` |
| `test_task_mixin` (14) | Gồm contract test với ERPNext: mọi method ghi đè vẫn tồn tại |
| `test_admin_api` (10), `test_install` (6), `test_hook_coverage` (3), `test_bootstrap` (10) | Qua |
| `run-tests --app pm_construction` | 2/2 |
| vitest (6 tệp) | **66/66** |
| `vite build` | Qua (JS 258 KB, gzip 83 KB) |
| ruff (F, E9) | Không lỗi |
| `scripts/ci/check_repo.py` | 0 lỗi |

**Kiểm bằng trình duyệt tích hợp (Administrator):**
- Đã mở: Tổng quan, Danh mục loại nút, Người dùng, Phân quyền, Nhật ký, Giám sát, Thiết lập, form Nhóm nhân viên.
- Ở cỡ 390 px: không cuộn ngang.
- Lỗi phát hiện và đã sửa:
  - thanh bên còn mục "trang cũ" (`boot.legacy`) của DM nên lỗi JS (vitest cũng bắt được);
  - ô "Loại" thiếu "Quản lý";
  - mục phạm vi của PM Group hiện khi chưa bật (`depends_on` thiếu `eval:`).

**Hiệu năng:** xem [HIEU_NANG.md](../HIEU_NANG.md). **Spike Gantt:** xem [spikes/GANTT.md](../spikes/GANTT.md).

**Clone sạch:**
- Cách làm:
  - xuất các file git đang theo dõi (`git checkout-index`) sang thư mục mới;
  - tạo `.env` từ `.env.example`, chỉ đổi tên compose, tiền tố volume và port (`pmclone`, 8891) để chạy song song stack dev;
  - để trống secret, chạy `bootstrap.ps1`.
- Kết quả: tự sinh 3 secret, setup wizard xong, smoke HTTP 9/9, test 62 + 2 qua.
- Sau đó gỡ stack clone kèm volume.

## 6. Điểm cần chú ý khi duyệt

- **Gantt (D11): người dùng chọn tự vẽ trên canvas** (2026-11-03). M4 thêm khoảng 2–3 tuần.
- Lỗi phát hiện khi chạy migrate: tên class của controller phải đúng tên DocType bỏ dấu cách (`PMRoleCapability`, không phải `PmRoleCapability`). Script sinh DocType đã sửa.
- `PM Project Member` khi lưu tự cấp role `PM Staff` (và các role mà vai trò dự án yêu cầu) cho người dùng; việc cấp chỉ cộng thêm, không bao giờ thu hồi.
- Trang `/pm` chỉ dành cho người có nhóm quyền của app. Tài khoản ERPNext khác bị chuyển sang `/desk`.

## 7. Việc tiếp theo

**M2 — Dự án, WBS, giao việc rõ trách nhiệm:**
- tạo dự án từ mẫu, cây WBS;
- `PM Team`, `PM Task Assignment` (RACI, đúng một người chịu trách nhiệm chính, chế độ "Chỉ việc được giao");
- lịch sử giao việc và đổi hạn, mã lý do chậm;
- rollup v1 + đối soát;
- Kanban, Việc của tôi, Ai làm gì;
- nhập WBS từ Excel.
