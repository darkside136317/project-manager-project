"""Shared constants: permission groups, capabilities, project roles and the screens of the SPA.

Two kinds of rights work together (see policy.py):

* a **permission group** (PM Role Profile = a Frappe Role) gives *global* capabilities, e.g. seeing every project;
* a **project role** (PM Project Role), held through PM Project Member, gives capabilities *inside one project*.

What a role may do with a kind of data (read / create / write / delete) stays Frappe's DocPerm; the project scope
narrows it to the projects of the user (permissions.py).
"""

SPA_HOME = "/pm"

# --- permission groups (global) ------------------------------------------------------------------------------------
ADMIN_ROLE = "PM Admin"
DIRECTOR_ROLE = "PM Director"
STAFF_ROLE = "PM Staff"

# Roles the app may give to a user (never System Manager / Administrator) and how they are described.
ASSIGNABLE_ROLES = (ADMIN_ROLE, DIRECTOR_ROLE, STAFF_ROLE)
ROLE_INFO = {
    ADMIN_ROLE: {"label": "Quản trị hệ thống", "group": "Quản trị",
                 "description": "Quản trị toàn bộ hệ thống: người dùng, nhóm quyền, thiết lập, nhật ký; xem và sửa mọi dự án."},
    DIRECTOR_ROLE: {"label": "Giám đốc", "group": "Quản lý",
                    "description": "Xem mọi dự án, hiệu suất và chi phí của toàn công ty; tạo dự án mới."},
    STAFF_ROLE: {"label": "Nhân viên", "group": "Tác nghiệp",
                 "description": "Làm việc trong các dự án mình tham gia, theo vai trò được giao trong từng dự án."},
}

# Functions that are not "read / write a DocType" and so cannot live in a DocPerm. (code, label, module)
CAPABILITIES = (
    ("portfolio.view_all", "Xem mọi dự án", "Dự án"),
    ("project.create", "Tạo dự án mới", "Dự án"),
    ("master.manage", "Quản lý danh mục dùng chung", "Dự án"),
    ("forms.manage", "Thiết kế mẫu biểu mẫu", "Biểu mẫu"),
    ("perf.view_all", "Xem hiệu suất của mọi người", "Hiệu suất"),
    ("finance.view_all", "Xem chi phí, ngân sách của mọi dự án", "Tài chính"),
    ("logs.view", "Xem, tìm và tải nhật ký hệ thống", "Quản trị"),
    ("logs.purge", "Dọn dẹp nhật ký hệ thống", "Quản trị"),
    ("monitor.view", "Giám sát hệ thống", "Quản trị"),
)
CAPABILITY_CODES = frozenset(code for code, _label, _module in CAPABILITIES)
# Only administrators: never granted through a permission group.
ADMIN_ONLY_CAPABILITIES = frozenset({"users.manage"})
BUILTIN_CAPABILITIES = {
    DIRECTOR_ROLE: ("portfolio.view_all", "project.create", "perf.view_all", "finance.view_all", "logs.view", "monitor.view"),
    STAFF_ROLE: (),
}

# --- project roles (inside one project) ----------------------------------------------------------------------------
# (code, label). A role that holds any of WRITE_PROJECT_CAPABILITIES may change the project's data.
PROJECT_CAPABILITIES = (
    ("project.edit", "Sửa thông tin dự án"),
    ("project.members", "Quản lý thành viên dự án"),
    ("plan.edit", "Lập, sửa kế hoạch (WBS, tiến độ, baseline)"),
    ("task.assign", "Giao việc, đổi người phụ trách và hạn"),
    ("task.update", "Cập nhật tiến độ công việc"),
    ("task.approve", "Duyệt, nghiệm thu công việc"),
    ("perf.view_project", "Xem hiệu suất trong dự án"),
    ("finance.view", "Xem chi phí của dự án"),
)
PROJECT_CAPABILITY_CODES = frozenset(code for code, _label in PROJECT_CAPABILITIES)
WRITE_PROJECT_CAPABILITIES = frozenset({"project.edit", "project.members", "plan.edit", "task.assign", "task.update",
                                        "task.approve"})

VISIBILITY_ALL, VISIBILITY_ASSIGNED = "Tất cả công việc", "Chỉ việc được giao"

# Seeded once (PM Project Role); the administrator may change or add roles afterwards.
DEFAULT_PROJECT_ROLES = (
    {"role_name": "Quản lý dự án", "task_visibility": VISIBILITY_ALL,
     "capabilities": ("project.edit", "project.members", "plan.edit", "task.assign", "task.update", "task.approve",
                      "perf.view_project", "finance.view")},
    {"role_name": "Chỉ huy trưởng", "task_visibility": VISIBILITY_ALL,
     "capabilities": ("plan.edit", "task.assign", "task.update", "task.approve", "perf.view_project")},
    {"role_name": "Kỹ sư", "task_visibility": VISIBILITY_ALL, "capabilities": ("task.update",)},
    {"role_name": "Tổ trưởng", "task_visibility": VISIBILITY_ASSIGNED, "capabilities": ("task.update",)},
    {"role_name": "Thủ kho", "task_visibility": VISIBILITY_ALL, "capabilities": ()},
    {"role_name": "Kế toán dự án", "task_visibility": VISIBILITY_ALL, "capabilities": ("finance.view",)},
    {"role_name": "Khách", "task_visibility": VISIBILITY_ASSIGNED, "capabilities": ()},
)

# --- scope selects (PM Access, PM Group) ---------------------------------------------------------------------------
READ_MEMBER, READ_ALL, READ_CHOSEN = "Chỉ dự án tham gia", "Tất cả dự án", "Dự án tham gia và dự án được chọn"
WRITE_MEMBER, WRITE_SAME, WRITE_CHOSEN = "Theo vai trò trong dự án", "Như phạm vi xem", "Theo vai trò và dự án được chọn"

# --- node types of the WBS (PM Node Type, seeded once) -------------------------------------------------------------
DEFAULT_NODE_TYPES = (
    {"node_type": "Giai đoạn", "is_group": 1, "counts_in_rollup": 1, "sort_order": 10},
    {"node_type": "Nhóm việc", "is_group": 1, "counts_in_rollup": 1, "sort_order": 20},
    {"node_type": "Công việc", "is_group": 0, "counts_in_rollup": 1, "requires_accountable": 1, "sort_order": 30},
    {"node_type": "Việc con", "is_group": 0, "counts_in_rollup": 1, "sort_order": 40},
    {"node_type": "Mốc", "is_group": 0, "counts_in_rollup": 0, "is_milestone": 1, "sort_order": 50},
)

# --- permission matrix -----------------------------------------------------------------------------------------------
DOCTYPE_LABELS = {
    "Project": "Dự án", "Task": "Công việc", "PM Project Member": "Thành viên dự án", "PM Node Type": "Loại nút WBS",
    "PM Project Role": "Vai trò trong dự án", "PM Group": "Nhóm nhân viên", "PM Access": "Phạm vi truy cập",
    "PM Settings": "Thiết lập hệ thống", "PM Audit Log": "Nhật ký hệ thống", "PM Activity": "Dòng thời gian dự án",
}
DOCTYPE_LABELS.update({
    "PM Team": "Đội / tổ", "PM Task Assignment": "Phân công", "PM Delay Reason": "Lý do chậm",
    "PM Delay Source": "Khâu gây chậm", "PM Progress Entry": "Cập nhật tiến độ", "PM Snapshot": "Ảnh chụp tiến độ",
})
DOCTYPE_LABELS.update({
    "PM Form Template": "Mẫu biểu mẫu", "PM Form Submission": "Biểu mẫu đã điền",
    "PM Gate Requirement": "Điều kiện đóng việc",
})
DOCTYPE_LABELS.update({
    "PM Task Dependency": "Phụ thuộc giữa các việc", "PM Baseline": "Baseline", "PM Baseline Task": "Dòng của baseline",
    "PM Baseline Curve": "Đường cong của baseline",
})
ROLE_MATRIX = (
    ("Dự án", ("Project", "Task", "PM Project Member", "PM Task Assignment", "PM Progress Entry", "PM Form Submission",
               "PM Gate Requirement", "PM Task Dependency", "PM Baseline")),
    ("Danh mục", ("PM Node Type", "PM Project Role", "PM Team", "PM Delay Reason", "PM Delay Source", "PM Form Template")),
    ("Quản trị", ("PM Group", "PM Access", "PM Settings", "PM Audit Log")),
)

# DocTypes whose rows belong to one project (field `project`): each one must have the project-scope hooks
# (tests/test_hook_coverage.py). Project itself is scoped on its name. TASK_SCOPED ones follow the task visibility
# too (a member who sees only their assigned tasks sees only those tasks' rows).
PROJECT_SCOPED = ("Task", "PM Project Member", "PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot",
                  "PM Form Submission", "PM Gate Requirement", "PM Task Dependency", "PM Baseline", "PM Baseline Task",
                  "PM Baseline Curve")
TASK_SCOPED = ("Task", "PM Task Assignment", "PM Progress Entry", "PM Form Submission", "PM Gate Requirement",
               "PM Task Dependency", "PM Baseline Task")

# --- responsibility (PM Task Assignment) -----------------------------------------------------------------------------
ACCOUNTABLE, RESPONSIBLE, CONSULTED, INFORMED, REVIEWER = (
    "Chịu trách nhiệm chính", "Thực hiện", "Tham vấn", "Được báo", "Duyệt")
RACI_ROLES = (ACCOUNTABLE, RESPONSIBLE, CONSULTED, INFORMED, REVIEWER)
PENDING, ACCEPTED, DECLINED, REVOKED, DONE = "Chờ nhận", "Đã nhận", "Từ chối", "Thu hồi", "Hoàn thành"
LIVE_STATES = (PENDING, ACCEPTED)  # an active assignment in one of these is someone's current work

# ERPNext Task.status values the app uses ("Overdue" is never written: lateness is pm_is_overdue)
OPEN, WORKING, REVIEW, COMPLETED, CANCELLED = "Open", "Working", "Pending Review", "Completed", "Cancelled"
STATUS_LABELS = {OPEN: "Chưa làm", WORKING: "Đang làm", REVIEW: "Chờ duyệt", COMPLETED: "Xong", CANCELLED: "Hủy"}
CLOSED_STATUSES = (COMPLETED, CANCELLED)

# --- delays (seeded once; industry layers add their own) ------------------------------------------------------------
DEFAULT_DELAY_REASONS = (
    "Chờ đầu vào từ bên khác", "Thay đổi yêu cầu / thiết kế", "Thiếu nhân lực", "Thiếu vật tư, thiết bị",
    "Chờ duyệt, nghiệm thu", "Sự cố kỹ thuật", "Yếu tố bên ngoài (thời tiết, pháp lý...)", "Ước lượng sai khối lượng",
    "Khác",
)
DEFAULT_DELAY_SOURCES = (
    "Đội thực hiện", "Bộ phận khác trong công ty", "Nhà cung cấp", "Khách hàng / chủ đầu tư", "Đơn vị tư vấn",
    "Bên ngoài",
)

# --- dynamic forms (PM Form Template, PM Form Submission) -------------------------------------------------------------
FORM_DRAFT, FORM_ACTIVE, FORM_RETIRED = "Nháp", "Đang dùng", "Ngừng dùng"
SUB_DRAFT, SUB_SUBMITTED, SUB_APPROVED, SUB_RETURNED = "Nháp", "Đã nộp", "Đã duyệt", "Trả lại"
SUB_EDITABLE = (SUB_DRAFT, SUB_RETURNED)
F_TEXT, F_LONG, F_NUMBER, F_DATE, F_SELECT, F_CHECK, F_TABLE, F_IMAGE, F_SIGNATURE, F_SECTION = (
    "Văn bản", "Văn bản dài", "Số", "Ngày", "Chọn", "Hộp kiểm", "Bảng", "Ảnh", "Chữ ký", "Tiêu đề mục")
FORM_FIELD_TYPES = (F_TEXT, F_LONG, F_NUMBER, F_DATE, F_SELECT, F_CHECK, F_TABLE, F_IMAGE, F_SIGNATURE, F_SECTION)
TABLE_COLUMN_TYPES = (F_TEXT, F_NUMBER, F_DATE, F_SELECT, F_CHECK)
GATE_FORM_APPROVED, GATE_BLOCKS_CLOSE = "Biểu mẫu đã duyệt", "Đóng việc"

# --- progress roll-up (Project.pm_rollup_method) ------------------------------------------------------------------
ROLLUP_DURATION, ROLLUP_WEIGHT, ROLLUP_EQUAL = "Theo thời lượng", "Theo trọng số", "Bằng nhau"
ROLLUP_METHODS = (ROLLUP_DURATION, ROLLUP_WEIGHT, ROLLUP_EQUAL)

# --- screens of the SPA on the generic list / form API (api/crud.py, api/meta.py) ---------------------------------
# The generic API refuses every DocType that is not registered here; permissions still decide who may read or change
# what. Optional keys: list_fields, search_fields, hide, readonly, drawer_width (see services/ui.py).
MASTERS = [
    {"doctype": "PM Node Type", "slug": "loai-nut-wbs", "label": "Loại nút WBS", "icon": "list-tree",
     "list_fields": ["node_type", "is_group", "counts_in_rollup", "sort_order"]},
    {"doctype": "PM Project Role", "slug": "vai-tro-du-an", "label": "Vai trò trong dự án", "icon": "id-card",
     "list_fields": ["role_name", "task_visibility", "is_builtin"]},
    {"doctype": "PM Team", "slug": "doi-to", "label": "Đội, tổ", "icon": "users",
     "list_fields": ["team_name", "team_type", "leader", "is_active"]},
    {"doctype": "PM Delay Reason", "slug": "ly-do-cham", "label": "Lý do chậm", "icon": "alert-triangle",
     "list_fields": ["reason", "sort_order", "is_active"]},
    {"doctype": "PM Delay Source", "slug": "khau-gay-cham", "label": "Khâu gây chậm", "icon": "network",
     "list_fields": ["source", "sort_order", "is_active"]},
]
ADMIN_SCREENS = [
    {"doctype": "PM Group", "slug": "nhom-nhan-vien", "label": "Nhóm nhân viên", "icon": "users",
     "list_fields": ["group_name", "apply_scope", "description"]},
    {"doctype": "PM Settings", "slug": "thiet-lap-he-thong", "label": "Thiết lập hệ thống", "icon": "settings"},
]
REGISTRY = {entry["doctype"]: entry for entry in [*MASTERS, *ADMIN_SCREENS]}
