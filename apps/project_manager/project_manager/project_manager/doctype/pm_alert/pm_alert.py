import frappe
from frappe.model.document import Document


class PMAlert(Document):
    """One alert: a rule that holds for one task (or form, assignment, project) in one episode. Written only by
    services/alerts.py; the same rule, reference and episode never make a second alert."""

    def on_update(self):
        if not self.flags.in_insert and not self.flags.pm_service:
            frappe.throw(frappe._("Cảnh báo không sửa được"))


def on_doctype_update():
    frappe.db.add_unique("PM Alert", ["rule", "reference_doctype", "reference_name", "episode"],
                         constraint_name="pm_alert_episode")
    frappe.db.add_index("PM Alert", ["project", "state"])
    frappe.db.add_index("PM Alert", ["state", "rule"])
    frappe.db.add_index("PM Alert", ["task"])
