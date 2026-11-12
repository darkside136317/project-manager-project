import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

# score = probability x impact, on a 5 x 5 matrix
LEVELS = ((12, "Cao"), (5, "Trung bình"), (0, "Thấp"))


class PMRisk(Document):
    """A risk of the project (services/control.py): how likely, how bad, who handles it and how."""

    def validate(self):
        for field, label in (("probability", _("Khả năng xảy ra")), ("impact", _("Mức ảnh hưởng"))):
            if not 1 <= cint(self.get(field)) <= 5:
                frappe.throw(_("{0} phải từ 1 đến 5").format(label))
        self.score = cint(self.probability) * cint(self.impact)
        self.level = next(label for floor, label in LEVELS if self.score >= floor)


def on_doctype_update():
    frappe.db.add_index("PM Risk", ["project", "status"])
