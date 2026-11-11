"""M8: ERPNext's stock and buying documents narrowed to the projects of the app's staff.

A store keeper of project A works with A's site store, A's requests and stock entries, not B's; moving stock between
two stores needs the right on both. People outside the app keep ERPNext's own permissions; holders of
stock.cross_project see everything.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_stock_scope
"""

import frappe

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.tests.helpers import TAG, PMTestCase, add_member, drop_project, drop_user, make_project, make_user

KEEPER = f"st.keeper.{TAG}@example.com"
ENGINEER = f"st.engineer.{TAG}@example.com"
ERP_ONLY = f"st.erp.{TAG}@example.com"
CENTRAL = f"st.central.{TAG}@example.com"
USERS = (KEEPER, ENGINEER, ERP_ONLY, CENTRAL)
CENTRAL_GROUP = f"PM Kho tong {TAG}"


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


class TestStockScope(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        from project_manager.project_manager.setup import install

        install.seed_all()
        cls.company = frappe.defaults.get_global_default("company")
        cls.abbr = frappe.get_cached_value("Company", cls.company, "abbr")
        for user in (KEEPER, ENGINEER, CENTRAL):
            make_user(user, [C.STAFF_ROLE])
        make_user(ERP_ONLY, ["Stock User"])
        cls.a, cls.b = make_project("ST A"), make_project("ST B")
        add_member(cls.a, KEEPER, "Thủ kho")  # gives the Stock User role it needs (required roles of the project role)
        add_member(cls.a, ENGINEER, "Kỹ sư")
        if not frappe.db.exists("Role", CENTRAL_GROUP):
            frappe.get_doc({"doctype": "Role", "role_name": CENTRAL_GROUP, "desk_access": 1}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "PM Role Profile", "role": CENTRAL_GROUP, "label": "Kho tổng",
                        "capabilities": [{"capability": "stock.cross_project"}]}).insert(ignore_permissions=True)
        frappe.get_doc("User", CENTRAL).add_roles(CENTRAL_GROUP, "Stock User")
        cls.item = cls._item()
        # the tree's names follow the site's language ("All Warehouses", "Tất cả Kho"): found by their place
        cls.root = frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 1,
                                                     "parent_warehouse": ["is", "not set"]}, "name")
        cls.store_a, cls.store_b = cls._store("A", cls.a), cls._store("B", cls.b)
        cls.main = frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 0, "pm_project": ["is", "not set"],
                                                     "name": ["not like", f"%{TAG}%"]}, "name")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for doctype in ("Stock Entry", "Material Request"):
            for name in frappe.get_all(doctype, filters={"project" if doctype == "Stock Entry" else "pm_project":
                                                         ["in", [cls.a, cls.b]]}, pluck="name"):
                frappe.db.delete(doctype, {"name": name})
        for store in (cls.store_a, cls.store_b):
            frappe.db.delete("Bin", {"warehouse": store})
            frappe.delete_doc("Warehouse", store, force=True, ignore_permissions=True, ignore_missing=True)
        frappe.delete_doc("Item", cls.item, force=True, ignore_permissions=True, ignore_missing=True)
        frappe.delete_doc("PM Role Profile", CENTRAL_GROUP, force=True, ignore_permissions=True, ignore_missing=True)
        for project in (cls.a, cls.b):
            drop_project(project)
        for user in USERS:
            drop_user(user)
        frappe.delete_doc("Role", CENTRAL_GROUP, force=True, ignore_permissions=True, ignore_missing=True)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    @classmethod
    def _item(cls) -> str:
        code = f"VT-THU-{TAG}"
        if not frappe.db.exists("Item", code):
            group = frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="lft asc")
            frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": "Xi măng thử", "item_group": group,
                            "stock_uom": "Kg", "is_stock_item": 1}).insert(ignore_permissions=True)
        return code

    @classmethod
    def _store(cls, label, project) -> str:
        return frappe.get_doc({"doctype": "Warehouse", "warehouse_name": f"Kho {label} {TAG}", "company": cls.company,
                               "parent_warehouse": cls.root, "pm_project": project}).insert(
            ignore_permissions=True).name

    def receive(self, project, store, qty=10):
        doc = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": self.company,
                              "project": project, "items": [{"item_code": self.item, "qty": qty, "t_warehouse": store,
                                                             "basic_rate": 100_000, "project": project}]})
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def entry(self, project, rows, purpose="Material Issue"):
        return frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": purpose, "company": self.company,
                               "project": project, "items": [{"item_code": self.item, "qty": 1, **row} for row in rows]})

    def test_a_keeper_sees_their_project_only(self):
        self.assertIn("Stock User", frappe.get_roles(KEEPER))
        in_a, in_b = self.receive(self.a, self.store_a), self.receive(self.b, self.store_b)
        stores = as_user(KEEPER, frappe.get_list, "Warehouse", pluck="name", limit_page_length=0)
        self.assertIn(self.store_a, stores)
        self.assertNotIn(self.store_b, stores)
        self.assertNotIn(self.main, stores)  # the main store belongs to no project
        entries = as_user(KEEPER, frappe.get_list, "Stock Entry", pluck="name", limit_page_length=0)
        self.assertIn(in_a.name, entries)
        self.assertNotIn(in_b.name, entries)
        self.assertTrue(as_user(KEEPER, frappe.has_permission, "Stock Entry", "read", doc=in_a))
        self.assertFalse(as_user(KEEPER, frappe.has_permission, "Stock Entry", "read", doc=in_b))

    def test_moving_stock_needs_both_stores(self):
        own = self.entry(self.a, [{"s_warehouse": self.store_a}])
        self.assertTrue(as_user(KEEPER, frappe.has_permission, "Stock Entry", "create", doc=own))
        across = self.entry(self.a, [{"s_warehouse": self.store_a, "t_warehouse": self.store_b}], "Material Transfer")
        self.assertFalse(as_user(KEEPER, frappe.has_permission, "Stock Entry", "create", doc=across))
        from_main = self.entry(self.a, [{"s_warehouse": self.main, "t_warehouse": self.store_a}], "Material Transfer")
        self.assertFalse(as_user(KEEPER, frappe.has_permission, "Stock Entry", "create", doc=from_main))
        other = self.entry(self.b, [{"s_warehouse": self.store_b}])
        self.assertFalse(as_user(KEEPER, frappe.has_permission, "Stock Entry", "create", doc=other))
        self.assertTrue(as_user(CENTRAL, frappe.has_permission, "Stock Entry", "create", doc=from_main))

    def test_material_requests_follow_their_project(self):
        mine = frappe.get_doc({"doctype": "Material Request", "material_request_type": "Material Issue", "company": self.company,
                               "pm_project": self.a, "schedule_date": frappe.utils.nowdate(),
                               "items": [{"item_code": self.item, "qty": 2, "warehouse": self.store_a,
                                          "schedule_date": frappe.utils.nowdate()}]}).insert(ignore_permissions=True)
        self.assertEqual(mine.items[0].project, self.a)  # the request's project goes down to its rows
        theirs = frappe.get_doc({"doctype": "Material Request", "material_request_type": "Material Issue",
                                 "company": self.company, "pm_project": self.b, "schedule_date": frappe.utils.nowdate(),
                                 "items": [{"item_code": self.item, "qty": 2, "warehouse": self.store_b,
                                            "schedule_date": frappe.utils.nowdate()}]}).insert(ignore_permissions=True)
        listed = as_user(KEEPER, frappe.get_list, "Material Request", pluck="name", limit_page_length=0)
        self.assertIn(mine.name, listed)
        self.assertNotIn(theirs.name, listed)
        # an engineer may ask for materials in the app, but has no ERPNext role to open the documents in the desk
        self.assertRaises(frappe.PermissionError, as_user, ENGINEER, frappe.get_list, "Material Request")

    def test_outside_the_app_and_across_projects_nothing_is_narrowed(self):
        self.receive(self.b, self.store_b)
        for user in (ERP_ONLY, CENTRAL):
            stores = as_user(user, frappe.get_list, "Warehouse", pluck="name", limit_page_length=0)
            self.assertTrue({self.store_a, self.store_b, self.main} <= set(stores), user)
        self.assertEqual(as_user(KEEPER, lambda: frappe.get_list("Warehouse", filters={"name": self.store_b})), [])

    def test_the_hooks_cover_every_scoped_doctype(self):
        queries, checks = frappe.get_hooks("permission_query_conditions"), frappe.get_hooks("has_permission")
        for doctype in C.STOCK_SCOPED:
            self.assertTrue(any(p.endswith("stock_query") for p in queries.get(doctype, [])), doctype)
            self.assertTrue(any(p.endswith("has_stock_permission") for p in checks.get(doctype, [])), doctype)
            self.assertTrue(frappe.get_meta(doctype).has_field(C.STOCK_SCOPED[doctype]), doctype)
