from frappe.model.document import Document


class PMCCrewAttendance(Document):
    """Chấm công of one crew on one project and day (services/labour.py): who worked on which work item, how many
    man-days. Nháp → Đã nộp → Đã xác nhận; confirmed man-days are the labour cost of the work items."""


def on_doctype_update():
    import frappe

    frappe.db.add_unique("PMC Crew Attendance", ["project", "team", "attendance_date"], constraint_name="pmc_attendance_day")
    frappe.db.add_index("PMC Crew Attendance", ["project", "attendance_date"])
