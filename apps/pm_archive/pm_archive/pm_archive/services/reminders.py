"""Alert type "Hồ sơ chưa nộp lưu": a closed project whose files have been waiting for the archivist longer than the
rule's number of days (90 by default). Told to the project's manager (by the rule) and to the archivists directly."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate
from project_manager.project_manager.policy import users_with_capability
from project_manager.project_manager.services import alerts

from pm_archive.pm_archive import constants as A


def not_filed(rule, today) -> list:
    since = add_days(getdate(today), -max(0, cint(rule.days) if rule.days is not None else 90))
    rows = frappe.db.sql("""select f.project, p.project_name, count(*) as files, min(f.waiting_since) as since
                            from `tabPM Archive File` f join `tabProject` p on p.name = f.project
                            where f.status = %(waiting)s and f.waiting_since is not null and date(f.waiting_since) <= %(since)s
                            group by f.project, p.project_name""", {"waiting": A.WAITING, "since": since}, as_dict=True)
    if not rows:
        return []
    archivists = users_with_capability(A.MANAGE_ALL)
    return [alerts._hit("Project", row.project, row.project, None, getdate(row.since).isoformat(), _(
        "{0}: {1} hồ sơ chờ nộp lưu từ ngày {2}").format(row.project_name, row.files, getdate(row.since).strftime("%d/%m/%Y")),
        direct=archivists) for row in rows]
