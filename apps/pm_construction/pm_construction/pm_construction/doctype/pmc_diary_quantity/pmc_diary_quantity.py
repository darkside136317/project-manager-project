import frappe
from frappe.model.document import Document


class PMCDiaryQuantity(Document):
    """A quantity done on one work item, as written in a site diary. A task's done quantity is the sum of the
    rows of its submitted or confirmed diaries (services/diary.py)."""


def on_doctype_update():
    frappe.db.add_index("PMC Diary Quantity", ["task", "entry_date"])
    frappe.db.add_index("PMC Diary Quantity", ["diary"])
