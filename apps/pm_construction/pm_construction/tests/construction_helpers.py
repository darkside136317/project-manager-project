"""Shared set-up of the construction layer's tests: a project with a manager, a site commander, an engineer, a crew
lead and an outsider, built on the core's test helpers."""

import frappe
from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.setup import install as core_install
from project_manager.tests.helpers import (
    TAG,
    PMTestCase,
    add_member,
    drop_project,
    drop_user,
    make_project,
    make_user,
)

from pm_construction.pm_construction.services import boq, boq_import

MANAGER = f"xd.manager.{TAG}@example.com"
COMMANDER = f"xd.commander.{TAG}@example.com"
ENGINEER = f"xd.engineer.{TAG}@example.com"
LEAD = f"xd.lead.{TAG}@example.com"
OUTSIDER = f"xd.outsider.{TAG}@example.com"
USERS = (MANAGER, COMMANDER, ENGINEER, LEAD, OUTSIDER)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


def drop_construction(project: str) -> None:
    for doctype in ("PMC Diary Quantity", "PMC Site Diary", "PMC BOQ Item", "PMC BOQ"):
        frappe.db.delete(doctype, {"project": project})


def sheet(rows, header=("STT", "Mã hiệu", "Nội dung công việc", "Đơn vị", "Khối lượng", "Đơn giá", "Thành tiền"),
          above=()) -> bytes:
    """An .xlsx with optional title rows above the header."""
    import io

    from openpyxl import Workbook

    book = Workbook()
    page = book.active
    for row in above:
        page.append(list(row))
    page.append(list(header))
    for row in rows:
        page.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class ConstructionBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        core_install.seed_all()
        for user in USERS:
            make_user(user, [C.STAFF_ROLE])
        cls.project = make_project("XD")
        frappe.db.set_value("Project", cls.project, "pm_manager", MANAGER)
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, COMMANDER, "Chỉ huy trưởng")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, LEAD, "Tổ trưởng")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_construction(cls.project)
        drop_project(cls.project)
        for user in USERS:
            frappe.db.delete("Notification Log", {"for_user": user})
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def approved_sample(self) -> dict:
        """The sample BOQ imported and approved by the manager: {description: task}."""
        version = as_user(MANAGER, boq.import_version, self.project, boq_import.template_file(), "mau.xlsx")
        as_user(MANAGER, boq.approve, version.name)
        return {row.subject: row.name for row in frappe.get_all("Task", filters={"project": self.project},
                                                                fields=["name", "subject"])}
