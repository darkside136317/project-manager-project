import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class PMChangeRequest(Document):
    """Đề nghị phát sinh (services/control.py): Nháp → Chờ duyệt → Đã duyệt / Từ chối, or Đã hủy."""

    def validate(self):
        seen = set()
        for row in self.tasks:
            if row.task in seen:
                frappe.throw(_("Công việc {0} có hai dòng").format(row.task))
            seen.add(row.task)
            info = frappe.db.get_value("Task", row.task, ["project", "exp_end_date"], as_dict=True)
            if not info or info.project != self.project:
                frappe.throw(_("Dòng {0}: công việc không thuộc dự án này").format(row.idx))
            if not row.old_end and info.exp_end_date:
                row.old_end = getdate(info.exp_end_date)


def on_doctype_update():
    frappe.db.add_index("PM Change Request", ["project", "status"])
