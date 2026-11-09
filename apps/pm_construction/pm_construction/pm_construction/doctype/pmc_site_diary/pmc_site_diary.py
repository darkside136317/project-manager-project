import frappe
from frappe.model.document import Document


class PMCSiteDiary(Document):
    """The site diary of one project for one day (nhật ký thi công), named {project}-ND-{date}: a phone that is
    offline knows the name of the diary it writes. Written only by services/diary.py."""

    def autoname(self):
        self.name = f"{self.project}-ND-{self.diary_date}"


def on_doctype_update():
    frappe.db.add_unique("PMC Site Diary", ["project", "diary_date"], constraint_name="pmc_diary_day")
