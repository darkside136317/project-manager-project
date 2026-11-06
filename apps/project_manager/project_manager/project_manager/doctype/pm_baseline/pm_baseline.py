import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class PMBaseline(Document):
    """Baseline: a frozen copy of a project's plan, named {project}-BL01, BL02... Written only by services/baseline.py.
    Its rows (PM Baseline Task, PM Baseline Curve) are separate tables written in bulk: a project may have 20 000 tasks."""

    def autoname(self):
        self.name = f"{self.project}-BL{cint(self.baseline_no):02d}"

    def validate(self):
        if not self.is_new():
            frappe.throw(_("Baseline đã chụp không sửa được"))

    def on_trash(self):
        if self.flags.pm_cleanup or frappe.flags.in_uninstall:
            return
        if self.is_primary:
            frappe.throw(_("Không xóa được baseline chính: hãy chọn baseline chính khác trước"))


def on_doctype_update():
    frappe.db.add_unique("PM Baseline", ["project", "baseline_no"], constraint_name="pm_baseline_number")
