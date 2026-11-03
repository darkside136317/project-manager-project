"""M1: the generic API and the administration API — who may call what, and the guard rails.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_admin_api
"""

import frappe

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.api import admin, boot, crud, logs, users
from project_manager.project_manager.api import permissions as groups
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import TAG, PMTestCase, add_member, drop_project, drop_user, make_project, make_user

ADMIN = f"aa.admin.{TAG}@example.com"
STAFF = f"aa.staff.{TAG}@example.com"
OUTSIDE = f"aa.outside.{TAG}@example.com"


class TestAdminApi(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        make_user(ADMIN, [C.ADMIN_ROLE])
        make_user(STAFF, [C.STAFF_ROLE])
        make_user(OUTSIDE, ["Projects User"])  # an ERPNext user outside the app
        cls.project = make_project("AA")
        add_member(cls.project, STAFF, "Kỹ sư")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.project)
        for user in (ADMIN, STAFF, OUTSIDE, f"aa.new.{TAG}@example.com"):
            drop_user(user)
        frappe.db.commit()
        super().tearDownClass()

    def as_user(self, user):
        frappe.set_user(user)
        policy.clear_cache()

    # --- boot --------------------------------------------------------------------------------------------------

    def test_boot_follows_the_user(self):
        self.as_user(ADMIN)
        admin_boot = boot.get_boot()
        routes = {item["route"] for group in admin_boot["nav"] for item in group["items"]}
        self.assertIn("/pm/quan-tri/nguoi-dung", routes)
        self.assertTrue(admin_boot["user"]["all_projects"])
        self.as_user(STAFF)
        staff_boot = boot.get_boot()
        routes = {item["route"] for group in staff_boot["nav"] for item in group["items"]}
        self.assertNotIn("/pm/quan-tri/nguoi-dung", routes)
        self.assertFalse(staff_boot["user"]["all_projects"])
        self.as_user(OUTSIDE)
        self.assertRaises(frappe.PermissionError, boot.get_boot)

    # --- generic screens ---------------------------------------------------------------------------------------

    def test_generic_api_serves_only_registered_doctypes(self):
        self.as_user(STAFF)
        page = crud.get_list("PM Node Type")
        self.assertIn("Giai đoạn", {row.name for row in page["data"]})
        self.assertRaises(frappe.PermissionError, crud.get_list, "User")
        self.assertRaises(frappe.PermissionError, crud.get_list, "PM Audit Log")
        self.as_user(OUTSIDE)
        self.assertRaises(frappe.PermissionError, crud.get_list, "PM Node Type")

    def test_staff_cannot_change_masters(self):
        self.as_user(STAFF)
        self.assertRaises(frappe.PermissionError, crud.save, "PM Node Type", {"node_type": "x"})
        self.as_user(ADMIN)
        saved = crud.save("PM Node Type", {"node_type": f"Nút {TAG}", "is_group": 0, "counts_in_rollup": 1})
        self.assertEqual(saved["name"], f"Nút {TAG}")

    # --- users -------------------------------------------------------------------------------------------------

    def test_users_api_is_for_administrators(self):
        self.as_user(STAFF)
        self.assertRaises(frappe.PermissionError, users.list_users)
        self.as_user(ADMIN)
        names = {row["name"] for row in users.list_users(search="aa.")["data"]}
        self.assertLessEqual({ADMIN, STAFF}, names)

    def test_create_a_user_with_a_project_scope(self):
        self.as_user(ADMIN)
        email = f"aa.new.{TAG}@example.com"
        made = users.save_user({"email": email, "first_name": "Mới", "roles": [C.STAFF_ROLE],
                                "access": {"read_scope": C.READ_CHOSEN, "read_projects": [self.project]}})
        self.assertTrue(made["set_password_path"].startswith("/update-password?key="))
        self.assertEqual(made["roles"], [C.STAFF_ROLE])
        self.assertEqual([r["project"] for r in made["access"]["effective"]["read_projects"]], [self.project])
        self.assertEqual(made["access"]["effective"]["write_projects"], [])

    def test_effective_access_lists_memberships(self):
        self.as_user(ADMIN)
        info = users.get_user(STAFF)
        self.assertEqual(info["access"]["effective"]["memberships"], [{"project": self.project, "roles": ["Kỹ sư"]}])

    def test_an_administrator_cannot_lock_themselves_out(self):
        self.as_user(ADMIN)
        self.assertRaises(frappe.ValidationError, users.save_user, {"roles": [C.STAFF_ROLE]}, ADMIN)
        self.assertRaises(frappe.ValidationError, users.save_user, {"enabled": 0}, ADMIN)
        self.assertRaises(frappe.ValidationError, users.save_user, {"roles": ["System Manager"]}, STAFF)

    # --- permission groups -------------------------------------------------------------------------------------

    def test_groups_copy_and_edit(self):
        self.as_user(ADMIN)
        label = f"Giám sát {TAG}"
        made = groups.create_group(label, copy_from=C.DIRECTOR_ROLE)
        granted = {item["code"] for module in made["capabilities"] for item in module["items"] if item["checked"]}
        self.assertIn("portfolio.view_all", granted)
        changed = groups.save_group(label, {"capabilities": ["portfolio.view_all"],
                                            "matrix": {"Task": {"read": 1, "write": 1}}})
        task = next(r for s in changed["matrix"] for r in s["rows"] if r["doctype"] == "Task")
        self.assertTrue(task["cell"]["write"])
        self.assertRaises(frappe.ValidationError, groups.save_group, C.ADMIN_ROLE, {"capabilities": []})

    # --- log and monitor ---------------------------------------------------------------------------------------

    def test_configuration_changes_are_logged(self):
        frappe.get_doc({"doctype": "PM Group", "group_name": f"AA nhóm {TAG}"}).insert(ignore_permissions=True)
        self.as_user(ADMIN)
        rows = logs.list_logs(reference_doctype="PM Group")["data"]
        self.assertTrue(any(row.get("reference_name") == f"AA nhóm {TAG}" for row in rows))
        self.as_user(STAFF)
        self.assertRaises(frappe.PermissionError, logs.list_logs)

    def test_monitor(self):
        self.as_user(ADMIN)
        data = admin.monitor()
        self.assertIn("meilisearch", data["services"])
        self.assertTrue(data["services"]["overdue_job"]["ok"])
        self.as_user(STAFF)
        self.assertRaises(frappe.PermissionError, admin.monitor)
