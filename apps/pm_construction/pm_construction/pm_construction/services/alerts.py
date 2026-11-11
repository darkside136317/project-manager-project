"""Alert types of the construction layer (core hook pm_alert_types; services/alerts.py of the core runs them).

* Thiếu nhật ký thi công: a project under way with an approved BOQ has no submitted (or confirmed) site diary for its
  last working day before today. One episode per missing day; it closes when the diary comes in or the next day.
"""

import frappe
from frappe import _
from frappe.utils import getdate
from project_manager.project_manager.services import alerts, workdays

from pm_construction.pm_construction import constants as K


def last_working_day(project: str, today):
    calendar = workdays.calendar_of(project)
    return calendar.date_at(calendar.index(getdate(today), forward=True) - 1)


def missing_diary(rule, today):
    projects = frappe.db.sql("""select distinct p.name, p.project_name, p.expected_start_date
                                from `tabPMC BOQ` b join `tabProject` p on p.name = b.project
                                where b.status = %(approved)s and p.pm_is_template = 0 and p.pm_state = 'Đang thực hiện'""",
                             {"approved": K.BOQ_APPROVED}, as_dict=True)
    hits = []
    for project in projects:
        day = last_working_day(project.name, today)
        if project.expected_start_date and getdate(project.expected_start_date) > day:
            continue
        if frappe.db.exists("PMC Site Diary", {"project": project.name, "diary_date": day,
                                               "status": ["in", K.DIARY_COUNTED]}):
            continue
        hits.append(alerts._hit("Project", project.name, project.name, None, day.isoformat(),
                                _("Chưa có nhật ký thi công ngày {0}: {1}").format(day.strftime("%d/%m/%Y"),
                                                                                  project.project_name)))
    return hits
