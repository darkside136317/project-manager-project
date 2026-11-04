import frappe
from frappe.model.document import Document


class PMActivity(Document):
    """Dòng thời gian dự án: one immutable entry (comment, progress update, field change, assignment...).

    Written only by services/activity.py; read through the API with the project scope (permissions.py).
    """

    def on_update(self):
        if not self.flags.in_insert and not self.flags.pm_hide:
            frappe.throw(frappe._("Dòng thời gian không sửa được"))


def on_doctype_update():
    frappe.db.add_index("PM Activity", ["reference_doctype", "reference_name", "name"])
    frappe.db.add_index("PM Activity", ["project", "name"])
    frappe.db.add_index("PM Activity", ["actor", "name"])
    frappe.db.add_index("PM Activity", ["task", "name"])  # the timeline of a task
