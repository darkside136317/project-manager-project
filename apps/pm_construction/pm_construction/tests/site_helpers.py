"""Shared set-up of the M8 tests: a store keeper, materials, a norm of the test's own on the footing work item."""

import frappe
from frappe.utils import flt
from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.tests.helpers import TAG, add_member, make_project, make_user

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.setup.demo_site import drop_site
from pm_construction.tests.construction_helpers import ConstructionBase

KEEPER = f"xd.keeper.{TAG}@example.com"
FOOTING = "Bê tông móng đá 1x2, mác 250"
NORM = f"T{TAG.upper()}.1"
CEMENT, SAND, STONE = f"XM-{TAG}", f"CAT-{TAG}", f"DA-{TAG}"
MATERIALS = ((CEMENT, "Xi măng PCB40 (thử)", "Kg"), (SAND, "Cát vàng (thử)", "m3"), (STONE, "Đá 1x2 (thử)", "m3"))
# per m3 of footing concrete: cement 350 kg + 1 %, sand 0.5 m3 + 2 %, stone 0.9 m3
NORM_ROWS = ((CEMENT, 350, 1), (SAND, 0.5, 2), (STONE, 0.9, 0))


def ensure_materials():
    from pm_construction.pm_construction.setup import install

    install.ensure_stock_masters()
    for code, name, uom in MATERIALS:
        if not frappe.db.exists("Item", code):
            frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": K.ITEM_GROUP,
                            "stock_uom": uom, "is_stock_item": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("PMC Material Norm", NORM):
        frappe.get_doc({"doctype": "PMC Material Norm", "norm_code": NORM, "description": "Bê tông móng (thử)",
                        "uom": "m3", "materials": [{"item": i, "qty": q, "waste_pct": w} for i, q, w in NORM_ROWS]}).insert(
            ignore_permissions=True)


class SiteBase(ConstructionBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        make_user(KEEPER, [C.STAFF_ROLE])
        add_member(cls.project, KEEPER, "Thủ kho")
        frappe.db.set_value("Project", cls.project, {"pm_state": "Đang thực hiện"})
        ensure_materials()
        cls.other = make_project("XD khác")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_site([cls.project, cls.other])
        from project_manager.tests.helpers import drop_project, drop_user

        drop_project(cls.other)
        frappe.db.delete("Notification Log", {"for_user": KEEPER})
        drop_user(KEEPER)
        frappe.db.delete("PMC Norm Material", {"parent": NORM})
        frappe.db.delete("PMC Material Norm", {"name": NORM})
        for code, _name, _uom in MATERIALS:
            frappe.db.delete("Bin", {"item_code": code})
            frappe.db.delete("Item", {"name": code})
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.tasks = self.approved_sample()
        self.footing = self.tasks[FOOTING]
        frappe.db.set_value("Task", self.footing, "pmc_norm_code", NORM)
        policy.clear_cache()

    def done(self, task, qty):
        frappe.db.set_value("Task", task, "pmc_done_qty", flt(qty))

    def row_of(self, rows, task, item):
        return next((r for r in rows if r.task == task and r.item == item), None)
