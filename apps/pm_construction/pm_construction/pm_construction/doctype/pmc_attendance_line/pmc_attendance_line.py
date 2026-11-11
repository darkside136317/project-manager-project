from frappe.model.document import Document


class PMCAttendanceLine(Document):
    pass


def on_doctype_update():
    import frappe

    frappe.db.add_index("PMC Attendance Line", ["task"])
    frappe.db.add_index("PMC Attendance Line", ["worker"])
