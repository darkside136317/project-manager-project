"""What the construction layer adds to the archive of a project when the archive layer is installed (hook
pm_archive_categories, read by pm_archive; this layer never imports it).

A group "Hồ sơ hoàn thành công trình" after the list of Nghị định 06/2021/NĐ-CP (hồ sơ hoàn thành công trình): the
acceptance records (the NT-* forms) and the site diaries with the daily quantities and the approved BOQ (this layer's
part of the project's data, under thi-cong/) are filed there on their own; as-built drawings and the hand-over papers
are added by the archivist (scans or moved documents).

Retention: 10 years by default, the longest of the minimums of Nghị định 06/2021 (khoản 4 Điều 26: 10, 7 and 5 years for
projects of group A, B and C). The company checks it against the consolidated text in force and may change it.
"""

from pm_construction.pm_construction import constants as K


def categories() -> list[dict]:
    return [
        {"code": "03", "title": "Hồ sơ hoàn thành công trình", "is_group": 1},
        {"code": "03.01", "parent": "03", "title": "Biên bản nghiệm thu", "retention": "10", "required": 1,
         "form_templates": "\n".join(K.ACCEPTANCE_CODES)},
        {"code": "03.02", "parent": "03", "title": "Nhật ký thi công, khối lượng, bảng khối lượng", "retention": "10",
         "required": 1, "data_paths": "thi-cong/"},
        {"code": "03.03", "parent": "03", "title": "Bản vẽ hoàn công", "retention": "10"},
        {"code": "03.04", "parent": "03", "title": "Hồ sơ bàn giao công trình", "retention": "10"},
    ]
