import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PMBudget(Document):
    """Ngân sách của dự án (services/budget.py): lines by cost category, optionally on a node of the WBS. The approved
    one in use is the BAC of the earned value figures; an approved change request adds a line to it."""

    def validate(self):
        for line in self.lines:
            if flt(line.amount) < 0 and line.category != "Phát sinh":
                frappe.throw(_("Số tiền của dòng {0} không được âm").format(line.idx))
            if line.task and frappe.db.get_value("Task", line.task, "project") != self.project:
                frappe.throw(_("Dòng {0}: công việc không thuộc dự án này").format(line.idx))
        self.total = sum(flt(line.amount) for line in self.lines)


def on_doctype_update():
    frappe.db.add_index("PM Budget", ["project", "status"])
