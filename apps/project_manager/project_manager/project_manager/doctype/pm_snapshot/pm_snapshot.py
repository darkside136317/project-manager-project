import frappe
from frappe.model.document import Document


class PMSnapshot(Document):
    """Daily progress of a project (task empty) or of one of its phases. Written by services/rollup.take_snapshots."""


def on_doctype_update():
    frappe.db.add_index("PM Snapshot", ["project", "snapshot_date"])
    frappe.db.add_index("PM Snapshot", ["task", "snapshot_date"])
