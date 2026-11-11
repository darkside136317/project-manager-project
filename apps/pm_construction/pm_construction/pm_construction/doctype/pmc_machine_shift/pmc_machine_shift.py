from frappe.model.document import Document


class PMCMachineShift(Document):
    """Ca máy: shifts one machine worked on one work item on one day (services/machines.record_shift); its cost is the
    shifts times the machine's shift rate on that day."""


def on_doctype_update():
    import frappe

    frappe.db.add_index("PMC Machine Shift", ["project", "shift_date"])
    frappe.db.add_index("PMC Machine Shift", ["machine", "shift_date"])
    frappe.db.add_index("PMC Machine Shift", ["task"])
