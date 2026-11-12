"""The core's reports: progress of the projects, late work, performance of people and crews, budget and earned value,
risks, issues, change requests. Each keeps to what the user may read (see base.py)."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.services.reports.base import (
    Report,
    col,
    integer,
    link,
    register,
    select,
)

G_PROGRESS, G_PEOPLE, G_FINANCE, G_CONTROL = "Tiến độ", "Nhân sự", "Tài chính", "Kiểm soát dự án"
LIVE = ("Chuẩn bị", "Đang thực hiện", "Tạm dừng")


def _page(rows, page, size):
    return rows[(page - 1) * size: page * size]


def _people(users) -> dict:
    users = [u for u in set(users) if u]
    return dict(frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"], as_list=True)) if users else {}


# --- Tiến độ các dự án -------------------------------------------------------------------------------------------------

def _progress(filters, page, size):
    from project_manager.project_manager.services import portfolio

    view = portfolio.portfolio(filters.get("state"), filters.get("health"))
    rows = [{"project": r.name, "project_name": r.project_name, "pm_code": r.pm_code, "manager_name": r.manager_name,
             "pm_health": r.pm_health, "percent_complete": flt(r.percent_complete, 1),
             "planned_progress": flt(r.planned_progress, 1),
             "variance": flt(flt(r.percent_complete) - flt(r.planned_progress), 1), "pm_spi": flt(r.pm_spi, 2) or None,
             "pm_forecast_end": r.pm_forecast_end, "forecast_slip": r.forecast_slip, "phase": r.phase,
             "late": r.late, "alerts_open": r.alerts_open,
             "on_time_rate": None if r.on_time_rate is None else flt(r.on_time_rate * 100, 1)} for r in view["rows"]]
    totals = view["totals"]
    return {"rows": rows, "total": len(rows),
            "summary": {"project_name": _("Cộng {0} dự án").format(len(rows)), "late": sum(cint(r["late"]) for r in rows),
                        "alerts_open": sum(cint(r["alerts_open"]) for r in rows)},
            "info": [(_("Sức khỏe"), _("Đỏ {0} · Vàng {1} · Xanh {2}").format(totals.get("Đỏ", 0), totals.get("Vàng", 0),
                                                                             totals.get("Xanh", 0)))]}


register(Report(
    slug="tien-do-du-an", title="Tiến độ các dự án", group=G_PROGRESS, icon="folder-kanban", order=10,
    description="Mỗi dự án đang chạy: sức khỏe, tiến độ so với kế hoạch, SPI, ngày xong dự báo, việc quá hạn, cảnh báo.",
    run=_progress,
    filters=[select("state", "Trạng thái", ["", *LIVE]), select("health", "Sức khỏe", ["", "Đỏ", "Vàng", "Xanh"])],
    columns=[col("project_name", "Dự án", link="/du-an/{project}/tong-quan"), col("pm_code", "Mã"),
             col("manager_name", "Quản lý"), col("pm_health", "Sức khỏe"),
             col("percent_complete", "Tiến độ (%)", "Float"), col("planned_progress", "Kế hoạch (%)", "Float"),
             col("variance", "Chênh lệch", "Float"), col("pm_spi", "SPI", "Float"),
             col("pm_forecast_end", "Dự báo xong", "Date"), col("forecast_slip", "Trễ dự báo (ngày)", "Int"),
             col("phase", "Giai đoạn"), col("late", "Việc quá hạn", "Int"), col("alerts_open", "Cảnh báo", "Int"),
             col("on_time_rate", "Đúng hạn 4 tuần (%)", "Float")]))


# --- Công việc trễ -------------------------------------------------------------------------------------------------------

def _late(filters, page, size):
    conditions = {"is_group": 0, "pm_is_overdue": 1, "status": ["not in", [C.COMPLETED, C.CANCELLED]]}
    if filters.get("project"):
        conditions["project"] = filters["project"]
    if filters.get("delay_source"):
        conditions["pm_delay_source"] = filters["delay_source"]
    if filters.get("min_days"):
        conditions["pm_delay_days"] = [">=", filters["min_days"]]
    total = len(frappe.get_list("Task", filters=conditions, pluck="name", limit_page_length=0))
    rows = frappe.get_list("Task", filters=conditions,
                           fields=["name", "project", "subject", "pm_wbs_code", "pm_accountable", "exp_end_date",
                                   "pm_delay_days", "progress", "pm_delay_reason", "pm_delay_source"],
                           order_by="pm_delay_days desc, exp_end_date asc", start=(page - 1) * size,
                           limit_page_length=size)
    names = _people(r.pm_accountable for r in rows)
    projects = dict(frappe.get_all("Project", filters={"name": ["in", list({r.project for r in rows}) or [""]]},
                                   fields=["name", "project_name"], as_list=True))
    out = [{"task": r.name, "project": r.project, "project_name": projects.get(r.project) or r.project,
            "label": f"{r.pm_wbs_code or ''} {r.subject}".strip(), "accountable": names.get(r.pm_accountable) or r.pm_accountable,
            "exp_end_date": getdate(r.exp_end_date) if r.exp_end_date else None, "pm_delay_days": cint(r.pm_delay_days),
            "progress": flt(r.progress, 1), "pm_delay_reason": r.pm_delay_reason, "pm_delay_source": r.pm_delay_source}
           for r in rows]
    return {"rows": out, "total": total}


register(Report(
    slug="cong-viec-tre", title="Công việc trễ", group=G_PROGRESS, icon="alarm-clock", order=20, paged=True,
    description="Công việc quá hạn chưa xong, trễ nhiều nhất trước: người chịu trách nhiệm, lý do và khâu gây chậm.",
    run=_late,
    filters=[link("project", "Dự án", "Project"), link("delay_source", "Khâu gây chậm", "PM Delay Source"),
             integer("min_days", "Trễ từ (ngày)")],
    columns=[col("project_name", "Dự án"), col("label", "Công việc", link="/cong-viec/{task}"),
             col("accountable", "Chịu trách nhiệm"), col("exp_end_date", "Hạn", "Date"),
             col("pm_delay_days", "Trễ (ngày)", "Int"), col("progress", "Tiến độ (%)", "Float"),
             col("pm_delay_reason", "Lý do chậm"), col("pm_delay_source", "Khâu gây chậm")]))


# --- Hiệu suất nhân sự, năng suất tổ đội ------------------------------------------------------------------------------

PERIOD_OPTIONS = ["4 tuần", "Tuần trước", "13 tuần"]
PERIODS = {"4 tuần": "4w", "Tuần trước": "week", "13 tuần": "quarter"}


def _performance(filters, page, size):
    from project_manager.project_manager.services import performance

    view = performance.overview(PERIODS[filters.get("period") or "4 tuần"], project=filters.get("project"),
                                team=filters.get("team"))
    rows = [{**r, "on_time_rate": None if r["on_time_rate"] is None else flt(r["on_time_rate"] * 100, 1)}
            for r in view["people"]]
    total = view["total"]
    return {"rows": _page(rows, page, size), "total": len(rows),
            "summary": {"full_name": _("Cộng"), "done": total["done"], "late_done": total["late_done"],
                        "open_late": total["open_late"], "reports": total["reports"],
                        "on_time_rate": None if total["on_time_rate"] is None else flt(total["on_time_rate"] * 100, 1)},
            "info": [(_("Khoảng"), f"{getdate(view['first']).strftime('%d/%m/%Y')} – {getdate(view['last']).strftime('%d/%m/%Y')}")]}


register(Report(
    slug="hieu-suat-nhan-su", title="Hiệu suất nhân sự", group=G_PEOPLE, icon="trending-up", order=10, paged=True,
    description="Việc xong, tỷ lệ đúng hạn, trễ trung bình, việc đang trễ của từng người (trong phạm vi bạn được xem).",
    run=_performance,
    filters=[select("period", "Khoảng", PERIOD_OPTIONS, default="4 tuần"), link("project", "Dự án", "Project"),
             link("team", "Tổ đội, phòng", "PM Team")],
    columns=[col("full_name", "Người"), col("done", "Xong", "Int"), col("on_time_rate", "Đúng hạn (%)", "Float"),
             col("late_done", "Xong trễ", "Int"), col("avg_delay", "Trễ TB (ngày)", "Float"),
             col("open_late", "Đang trễ", "Int"), col("reports", "Lần báo tiến độ", "Int")]))


def _crews(filters, page, size):
    from project_manager.project_manager.services import performance

    view = performance.overview(PERIODS[filters.get("period") or "4 tuần"], project=filters.get("project"))
    rows = view["crews"]
    return {"rows": _page(rows, page, size), "total": len(rows)}


register(Report(
    slug="nang-suat-to-doi", title="Năng suất tổ đội", group=G_PEOPLE, icon="hard-hat", order=20,
    description="Khối lượng làm được chia cho số công đã xác nhận, theo tổ đội và đơn vị (từ lớp ngành).",
    run=_crews, may_run=lambda user: bool(frappe.get_hooks("pm_productivity")),
    filters=[select("period", "Khoảng", PERIOD_OPTIONS, default="4 tuần"), link("project", "Dự án", "Project")],
    columns=[col("team_name", "Tổ đội"), col("uom", "Đơn vị"), col("qty", "Khối lượng", "Float"),
             col("man_days", "Công", "Float"), col("per_man_day", "Năng suất / công", "Float"),
             col("works", "Công tác", "Int")]))


# --- Ngân sách và giá trị thu được ------------------------------------------------------------------------------------

def _evm(filters, page, size):
    from project_manager.project_manager.services import budget

    conditions = {"pm_is_template": 0, "pm_state": filters.get("state") or ["in", LIVE]}
    projects = frappe.get_list("Project", filters=conditions, fields=["name", "project_name", "pm_code"],
                               order_by="project_name asc", limit_page_length=500)
    rows = []
    for project in projects:
        if not budget.may_read(project.name):
            continue
        figures = budget.evm(project.name)
        rows.append({"project": project.name, "project_name": project.project_name, "pm_code": project.pm_code, **figures})
    keys = ("bac", "pv", "ev", "ac", "eac", "vac")
    summary = {k: sum(flt(r.get(k)) for r in rows) for k in keys}
    summary["project_name"] = _("Cộng {0} dự án").format(len(rows))
    return {"rows": _page(rows, page, size), "total": len(rows), "summary": summary}


register(Report(
    slug="ngan-sach-evm", title="Ngân sách và giá trị thu được (EVM)", group=G_FINANCE, icon="wallet", order=10,
    description="Theo dự án bạn xem được chi phí: ngân sách (BAC), PV, EV, chi phí thực tế (AC), CPI, SPI, dự báo "
                "chi phí hoàn thành (EAC), chênh lệch khi hoàn thành (VAC).",
    run=_evm,
    filters=[select("state", "Trạng thái", ["", *LIVE, "Đóng"])],
    columns=[col("project_name", "Dự án", link="/du-an/{project}/ngan-sach"), col("bac", "BAC", "Currency"),
             col("progress_pct", "Tiến độ (%)", "Float"), col("planned_pct", "Kế hoạch (%)", "Float"),
             col("pv", "PV", "Currency"), col("ev", "EV", "Currency"), col("ac", "AC", "Currency"),
             col("cpi", "CPI", "Float"), col("spi", "SPI", "Float"), col("eac", "EAC", "Currency"),
             col("vac", "VAC", "Currency")]))


# --- Rủi ro, vấn đề, phát sinh -------------------------------------------------------------------------------------------

def _listing(doctype, filters, page, size, fields, order_by, keys):
    conditions = {k: filters[k] for k in keys if filters.get(k)}
    total = len(frappe.get_list(doctype, filters=conditions, pluck="name", limit_page_length=0))
    rows = frappe.get_list(doctype, filters=conditions, fields=["name", "project", *fields], order_by=order_by,
                           start=(page - 1) * size, limit_page_length=size)
    projects = dict(frappe.get_all("Project", filters={"name": ["in", list({r.project for r in rows}) or [""]]},
                                   fields=["name", "project_name"], as_list=True))
    for row in rows:
        row["project_name"] = projects.get(row.project) or row.project
    return rows, total


def _risks(filters, page, size):
    rows, total = _listing("PM Risk", filters, page, size,
                           ["title", "category", "probability", "impact", "score", "level", "owner_user", "response",
                            "due_date", "status"], "score desc, creation desc", ("project", "status", "level"))
    names = _people(r.owner_user for r in rows)
    for row in rows:
        row["owner_name"] = names.get(row.owner_user) or row.owner_user
    return {"rows": rows, "total": total}


register(Report(
    slug="rui-ro", title="Sổ rủi ro", group=G_CONTROL, icon="shield-alert", order=10, paged=True,
    description="Rủi ro của các dự án: khả năng, ảnh hưởng, mức, người phụ trách, cách ứng phó, hạn xử lý.",
    run=_risks,
    filters=[link("project", "Dự án", "Project"), select("status", "Trạng thái", ["", "Mở", "Đang xử lý", "Đã xảy ra", "Đã đóng"]),
             select("level", "Mức", ["", "Cao", "Trung bình", "Thấp"])],
    columns=[col("project_name", "Dự án", link="/du-an/{project}/rui-ro"), col("name", "Mã"), col("title", "Rủi ro"),
             col("category", "Nhóm"), col("probability", "Khả năng", "Int"), col("impact", "Ảnh hưởng", "Int"),
             col("score", "Điểm", "Int"), col("level", "Mức"), col("owner_name", "Phụ trách"),
             col("response", "Ứng phó"), col("due_date", "Hạn", "Date"), col("status", "Trạng thái")]))


def _issues(filters, page, size):
    rows, total = _listing("PM Issue", filters, page, size,
                           ["title", "priority", "owner_user", "due_date", "status", "resolved_on"],
                           "due_date asc, creation desc", ("project", "status", "priority"))
    names = _people(r.owner_user for r in rows)
    today = getdate(nowdate())
    for row in rows:
        row["owner_name"] = names.get(row.owner_user) or row.owner_user
        row["overdue"] = _("Quá hạn") if row.due_date and row.status in ("Mở", "Đang xử lý") and getdate(row.due_date) < today else ""
    return {"rows": rows, "total": total}


register(Report(
    slug="van-de", title="Vấn đề", group=G_CONTROL, icon="circle-alert", order=20, paged=True,
    description="Vấn đề của các dự án: mức ưu tiên, người xử lý, hạn, đã giải quyết hay chưa.",
    run=_issues,
    filters=[link("project", "Dự án", "Project"),
             select("status", "Trạng thái", ["", "Mở", "Đang xử lý", "Đã giải quyết", "Đã đóng"]),
             select("priority", "Ưu tiên", ["", "Khẩn", "Cao", "Trung bình", "Thấp"])],
    columns=[col("project_name", "Dự án", link="/du-an/{project}/rui-ro"), col("name", "Mã"), col("title", "Vấn đề"),
             col("priority", "Ưu tiên"), col("owner_name", "Người xử lý"), col("due_date", "Hạn", "Date"),
             col("overdue", ""), col("status", "Trạng thái"), col("resolved_on", "Giải quyết", "Date")]))


def _changes(filters, page, size):
    rows, total = _listing("PM Change Request", filters, page, size,
                           ["title", "reason", "cost_impact", "days_impact", "status", "requested_by", "decided_by",
                            "decided_on"], "creation desc", ("project", "status"))
    names = _people([*(r.requested_by for r in rows), *(r.decided_by for r in rows)])
    for row in rows:
        row["requested_name"] = names.get(row.requested_by) or row.requested_by
        row["decided_name"] = names.get(row.decided_by) or row.decided_by
        row["decided_on"] = getdate(row.decided_on) if row.decided_on else None
    approved = [r for r in rows if r.status == "Đã duyệt"]
    return {"rows": rows, "total": total,
            "summary": {"title": _("Đã duyệt trên trang này"), "cost_impact": sum(flt(r.cost_impact) for r in approved),
                        "days_impact": sum(cint(r.days_impact) for r in approved)}}


register(Report(
    slug="phat-sinh", title="Phát sinh", group=G_CONTROL, icon="git-pull-request", order=30, paged=True,
    description="Đề nghị phát sinh: nguyên nhân, chi phí, ảnh hưởng tiến độ, ai đề nghị, ai quyết định.",
    run=_changes,
    filters=[link("project", "Dự án", "Project"),
             select("status", "Trạng thái", ["", "Nháp", "Chờ duyệt", "Đã duyệt", "Từ chối", "Đã hủy"])],
    columns=[col("project_name", "Dự án", link="/du-an/{project}/phat-sinh"), col("name", "Mã"), col("title", "Nội dung"),
             col("reason", "Nguyên nhân"), col("cost_impact", "Chi phí", "Currency"),
             col("days_impact", "Tiến độ (ngày)", "Int"), col("status", "Trạng thái"),
             col("requested_name", "Người đề nghị"), col("decided_name", "Người quyết định"),
             col("decided_on", "Ngày quyết định", "Date")]))

