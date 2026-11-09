import frappe
from frappe.model.document import Document
from frappe.utils import cint


class PMCBOQ(Document):
    """One imported version of a project's bill of quantities, named {project}-BOQ01, BOQ02...
    Its lines (PMC BOQ Item) are written in bulk by services/boq.py; once approved, the version drives the WBS."""

    def autoname(self):
        self.name = f"{self.project}-BOQ{cint(self.version_no):02d}"

    def on_update(self):
        if not self.flags.in_insert and not self.flags.pm_service:
            frappe.throw(frappe._("BOQ đã nhập không sửa được: nhập phiên bản mới"))


def on_doctype_update():
    frappe.db.add_unique("PMC BOQ", ["project", "version_no"], constraint_name="pmc_boq_version")
