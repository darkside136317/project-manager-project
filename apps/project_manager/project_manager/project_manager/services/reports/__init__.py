"""Reports: the registry (`base.REPORTS`, filled by services/reports/core.py and by the industry layers through the hook
`pm_reports`: dotted paths of functions returning Report entries), who may run what, running one.

Copied from document_manager (services/reports/__init__.py, see docs/NGUON_GOC.md) and adapted: the staff gate of
this app, a `may_run` function per report, the layers' reports.
"""

import frappe
from frappe import _

from project_manager.project_manager.policy import is_staff
from project_manager.project_manager.services.reports import core  # noqa: F401  (register the core's reports)
from project_manager.project_manager.services.reports.base import REPORTS, Report, page_args, parse_filters

GROUP_ORDER = ("Tiến độ", "Nhân sự", "Tài chính", "Kiểm soát dự án")


def _all() -> dict:
    out = dict(REPORTS)
    for path in frappe.get_hooks("pm_reports") or []:
        for report in frappe.get_attr(path)() or []:
            out.setdefault(report.slug, report)
    return out


def can_run(report: Report, user: str | None = None) -> bool:
    user = user or frappe.session.user
    return is_staff(user) and (report.may_run is None or bool(report.may_run(user)))


def visible() -> list[Report]:
    """The reports the current user may run, in the order of the report hub."""
    mine = [r for r in _all().values() if can_run(r)]
    return sorted(mine, key=lambda r: (GROUP_ORDER.index(r.group) if r.group in GROUP_ORDER else 99, r.order, r.title))


def get(slug: str) -> Report:
    report = _all().get(slug)
    if not report:
        frappe.throw(_("Không có báo cáo {0}").format(slug), frappe.DoesNotExistError)
    if not can_run(report):
        frappe.throw(_("Bạn không có quyền xem báo cáo này"), frappe.PermissionError)
    return report


def run(slug: str, filters=None, page=1, page_size=None) -> dict:
    """Run a report: {slug, title, columns, rows, total, page, page_size, summary, chart, info, filters}."""
    report = get(slug)
    parsed = parse_filters(report, filters)
    for spec in report.filters:
        if spec.get("reqd") and spec["fieldname"] not in parsed:
            frappe.throw(_("Chọn {0}").format(spec["label"].lower()))
    page, size = page_args(page, page_size)
    result = report.run(parsed, page, size)
    return {"slug": report.slug, "title": report.title, "columns": result.get("columns") or report.columns,
            "rows": result["rows"], "total": result["total"], "page": page, "page_size": size,
            "summary": result.get("summary"), "chart": result.get("chart"), "info": result.get("info") or [],
            "filters": parsed, "paged": report.paged, "landscape": report.landscape}
