"""The report screens: the catalogue, running a report, its CSV / Excel / print / PDF output, the scheduled sending.

Copied from document_manager (api/reports.py, see docs/NGUON_GOC.md) and adapted: who may run what is decided in
services/reports; every endpoint goes through it. Subscriptions: services/reports/schedule.py.
"""

import frappe
from frappe import _
from frappe.utils import nowdate

from project_manager.project_manager.services import reports
from project_manager.project_manager.services.audit import log_activity
from project_manager.project_manager.services.reports import output, schedule
from project_manager.project_manager.services.ui import assert_staff

FORMATS = ("xlsx", "csv")


@frappe.whitelist()
def list_reports():
    """[{group, reports: [{slug, title, description, icon}]}] of the reports the user may run."""
    assert_staff()
    groups = {}
    for report in reports.visible():
        groups.setdefault(report.group, []).append(
            {"slug": report.slug, "title": report.title, "description": report.description, "icon": report.icon})
    return [{"group": group, "reports": items} for group, items in groups.items()]


@frappe.whitelist()
def get_report(slug):
    assert_staff()
    return reports.get(slug).describe()


@frappe.whitelist()
def run_report(slug, filters=None, page=1, page_size=None):
    assert_staff()
    return reports.run(slug, filters, page, page_size)


def _file_name(slug: str, extension: str) -> str:
    return f"bao-cao-{slug}-{nowdate()}.{extension}"


@frappe.whitelist()
def download_report(slug, filters=None, format="xlsx"):
    """The whole result (up to 50.000 rows) as an Excel or CSV file."""
    assert_staff()
    if format not in FORMATS:
        frappe.throw(_("Định dạng {0} không được hỗ trợ").format(format))
    result, applied = output.prepare(slug, filters, output.MAX_EXPORT_ROWS)
    if format == "csv":
        content, mime = output.to_csv(result), "text/csv; charset=utf-8"
    else:
        content, mime = output.to_xlsx(result, applied), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    log_activity("Tải xuống", "Report", slug, f"Xuất báo cáo “{result['title']}” ({format.upper()}, {len(result['rows'])} dòng)")
    frappe.local.response.update({"type": "download", "filename": _file_name(slug, format), "filecontent": content,
                                  "content_type": mime})


@frappe.whitelist()
def print_report(slug, filters=None, format="html"):
    """The printable report with the company's header: a page to view (format html) or a PDF."""
    assert_staff()
    if format not in ("html", "pdf"):
        frappe.throw(_("Định dạng {0} không được hỗ trợ").format(format))
    result, applied = output.prepare(slug, filters, output.MAX_PRINT_ROWS)
    log_activity("Tải xuống", "Report", slug, f"In báo cáo “{result['title']}” ({format.upper()})")
    if format == "pdf":
        frappe.local.response.update({"type": "pdf", "filename": _file_name(slug, "pdf"),
                                      "filecontent": output.to_pdf(result, applied)})
        return
    html = output.render_html(result, applied)
    frappe.local.response.update({"type": "download", "filename": _file_name(slug, "html"), "filecontent": html.encode("utf-8"),
                                  "content_type": "text/html; charset=utf-8", "display_content_as": "inline"})


# --- scheduled sending --------------------------------------------------------------------------------------------------
@frappe.whitelist()
def subscriptions(report=None):
    assert_staff()
    return schedule.mine(report or None)


@frappe.whitelist(methods=["POST"])
def save_subscription(report, values, recipients, filters=None, name=None):
    assert_staff()
    return schedule.save(report, values, recipients, filters, name or None)


@frappe.whitelist(methods=["POST"])
def delete_subscription(name):
    assert_staff()
    return schedule.remove(name)


@frappe.whitelist(methods=["POST"])
def send_subscription_now(name):
    """Send one subscription at once (its author or an administrator), to try it."""
    assert_staff()
    doc = frappe.get_doc("PM Report Subscription", name)
    schedule._assert_mine(doc)
    return schedule.send(doc.name)


@frappe.whitelist()
def recipients(txt=""):
    assert_staff()
    return schedule.candidates(txt)
