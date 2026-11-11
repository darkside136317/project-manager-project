from frappe.model.document import Document


class PMPerformanceSnapshot(Document):
    """The figures of one week for one subject: a person in a project, a project, a crew in a project
    (services/performance.snapshot_week). Read through the performance service, which applies who may see whom."""


def on_doctype_update():
    import frappe

    frappe.db.add_unique("PM Performance Snapshot", ["week_start", "kind", "subject", "project"],
                         constraint_name="pm_perf_week_subject")
    frappe.db.add_index("PM Performance Snapshot", ["kind", "subject", "week_start"])
    frappe.db.add_index("PM Performance Snapshot", ["project", "week_start"])
