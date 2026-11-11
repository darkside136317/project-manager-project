from frappe.model.document import Document


class PMCMachineTransfer(Document):
    """A machine moved from one project to another (services/machines.transfer): a history, never changed."""


def on_doctype_update():
    import frappe

    frappe.db.add_index("PMC Machine Transfer", ["machine", "transfer_date"])
    frappe.db.add_index("PMC Machine Transfer", ["project"])
    frappe.db.add_index("PMC Machine Transfer", ["from_project"])
