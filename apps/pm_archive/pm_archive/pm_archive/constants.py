"""Constants of the archive layer (pm_archive): keeping the records of the projects (lưu trữ hồ sơ dự án).

* A project's records are gathered into archive files (hồ sơ) by category (danh mục hồ sơ); each file lists its items
  (tài liệu): document versions, approved forms, photos, the project's data, discussions, scans.
* The project manager builds them while the project runs; when it closes they wait for the company's archivist, who
  files them (nộp lưu): from then on a file is read-only, its items' SHA-256 are kept and checked every week.
"""

from project_manager.project_manager import constants as C

MODULE = "PM Archive"

# --- capabilities (core hooks pm_capabilities / pm_project_capabilities) ------------------------------------------------
MANAGE_ALL, VIEW_ALL = "archive.manage_all", "archive.view_all"
VIEW, MANAGE = "archive.view", "archive.manage"
CAPABILITIES = (
    {"code": MANAGE_ALL, "label": "Quản lý lưu trữ hồ sơ của mọi dự án (nộp lưu, kho, gói nộp lưu, kiểm toàn vẹn)",
     "module": "Lưu trữ"},
    {"code": VIEW_ALL, "label": "Xem hồ sơ lưu trữ của mọi dự án", "module": "Lưu trữ", "builtin": [C.DIRECTOR_ROLE]},
)
PROJECT_CAPABILITIES = (
    {"code": VIEW, "label": "Xem hồ sơ lưu trữ của dự án"},
    {"code": MANAGE, "label": "Lập hồ sơ lưu trữ của dự án (trước khi nộp lưu)"},
)
# Added once to the built-in project roles (the administrator may change the roles afterwards).
ROLE_GRANTS = {"Quản lý dự án": (VIEW, MANAGE), "Chỉ huy trưởng": (VIEW,), "Kế toán dự án": (VIEW,)}

# The company's archivist: a permission group of its own (a Frappe role and its PM Role Profile).
ARCHIVIST_ROLE = "PM Archivist"
ARCHIVIST_PROFILE = {
    "role": ARCHIVIST_ROLE, "label": "Lưu trữ", "group_label": "Tác nghiệp",
    "description": "Văn thư lưu trữ của công ty: xem và quản lý hồ sơ lưu trữ của mọi dự án, kể cả dự án đã đóng; "
                   "nộp lưu, kho lưu trữ, gói nộp lưu, kiểm tra toàn vẹn.",
    "capabilities": (MANAGE_ALL, VIEW_ALL),
}

# --- archive files and their items ------------------------------------------------------------------------------------
DRAFT, WAITING, FILED = "Đang lập", "Chờ nộp lưu", "Đã nộp lưu"
FILE_STATES = (DRAFT, WAITING, FILED)
INTERNAL, RESTRICTED = "Nội bộ dự án", "Hạn chế"
PERMANENT = "Vĩnh viễn"

DOCUMENT, FORM, PHOTO, DISCUSSION, DATA, UPLOAD = "Tài liệu", "Biểu mẫu", "Ảnh", "Trao đổi", "Dữ liệu", "Tệp tải lên"
ITEM_KINDS = (DOCUMENT, FORM, PHOTO, DISCUSSION, DATA, UPLOAD)
# What a category gathers on its own besides document categories and form templates.
SOURCE_KINDS = (PHOTO, DISCUSSION, DATA)

COLLECTION = "archive"  # MinIO objects made by this layer (core hook pm_object_stores)
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

STORAGE_KINDS = ("Kho", "Phòng", "Giá", "Hộp")

# --- alerts (core hooks pm_alert_types / pm_alert_rules) --------------------------------------------------------------
NOT_FILED = "Hồ sơ chưa nộp lưu"
INTEGRITY = "Hồ sơ lưu trữ lỗi toàn vẹn"

PROJECT_SCOPED = ("PM Archive File", "PM Archive Item")

# --- default categories (danh mục hồ sơ): proposals the company confirms ------------------------------------------------
# One line per category, the rules that file a project's records into it:
# * document_categories: values of PM Document.category (its approved version, else the newest);
# * form_templates: codes of PM Form Template, approved submissions (all_forms: every approved form left over);
# * kinds: Ảnh (the project's photos), Trao đổi (the discussions, exported when the project closes), Dữ liệu (the
#   project's data files, closing.data_parts, also when it closes);
# * data_paths: prefixes of data files that go here instead of the plain data category (an industry layer's part).
# retention: "Vĩnh viễn" or a number of years. Industry layers add theirs (hook pm_archive_categories, same keys,
# "parent" naming a group's code).
DEFAULT_CATEGORIES = (
    {"code": "01", "title": "Hồ sơ quản lý dự án", "is_group": 1},
    {"code": "01.01", "parent": "01", "title": "Hồ sơ pháp lý, hợp đồng", "retention": "20", "required": 1,
     "document_categories": "Pháp lý\nHợp đồng"},
    {"code": "01.02", "parent": "01", "title": "Hồ sơ kỹ thuật, bản vẽ", "retention": "20",
     "document_categories": "Bản vẽ\nHồ sơ kỹ thuật"},
    {"code": "01.03", "parent": "01", "title": "Biên bản, báo cáo", "retention": "10",
     "document_categories": "Biên bản\nThuyết minh, báo cáo"},
    {"code": "01.04", "parent": "01", "title": "Biểu mẫu đã duyệt", "retention": "10", "all_forms": 1},
    {"code": "01.05", "parent": "01", "title": "Tài liệu khác", "retention": "10", "document_categories": "Khác"},
    {"code": "02", "title": "Tư liệu dự án", "is_group": 1},
    {"code": "02.01", "parent": "02", "title": "Ảnh hiện trường", "retention": "10", "kinds": PHOTO},
    {"code": "02.02", "parent": "02", "title": "Trao đổi theo công việc", "retention": "10", "kinds": DISCUSSION},
    {"code": "02.03", "parent": "02", "title": "Dữ liệu dự án", "retention": "20", "required": 1, "kinds": DATA,
     "access_mode": RESTRICTED},  # it holds the budget
)

MASTERS = (
    {"doctype": "PM Archive Category", "slug": "danh-muc-ho-so", "label": "Danh mục hồ sơ", "icon": "folder-tree",
     "list_fields": ["code", "title", "retention", "required", "access_mode"]},
    {"doctype": "PM Archive Storage", "slug": "kho-luu-tru", "label": "Kho lưu trữ", "icon": "warehouse",
     "list_fields": ["code", "title", "kind", "parent_storage"]},
)

ALERT_RULES = (
    {"rule_name": NOT_FILED, "rule_type": NOT_FILED, "days": 90, "to_accountable": 0, "to_manager": 1,
     "description": "Dự án đã đóng quá N ngày mà còn hồ sơ chưa nộp lưu (người lưu trữ cũng được báo)."},
    {"rule_name": INTEGRITY, "rule_type": INTEGRITY, "to_accountable": 0, "to_manager": 0,
     "description": "Lần kiểm tra toàn vẹn gần nhất thấy tài liệu lưu trữ bị đổi hoặc bị mất (báo người lưu trữ)."},
)
