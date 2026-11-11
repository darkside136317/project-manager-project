import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PMCMaterialNorm(Document):
    """Định mức vật tư of one norm code (mã hiệu định mức): the materials one unit of work consumes, with their waste.
    A work item of the BOQ with this code gets its material plan from it (services/materials.plan_from_norms)."""

    def validate(self):
        self.norm_code = (self.norm_code or "").strip().upper()
        seen = set()
        for row in self.materials or []:
            if flt(row.qty) <= 0:
                frappe.throw(_("Hao phí của {0} phải lớn hơn 0").format(row.item))
            if not 0 <= flt(row.waste_pct) < 100:
                frappe.throw(_("Hao hụt của {0} phải từ 0 đến dưới 100%").format(row.item))
            if row.item in seen:
                frappe.throw(_("{0} có hai dòng trong định mức").format(row.item))
            seen.add(row.item)
