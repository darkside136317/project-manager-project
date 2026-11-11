"""M1: the project scope — who sees and changes which project and task, through every path Frappe offers.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_project_scope
"""

import frappe

from project_manager.project_manager import constants as C
from project_manager.project_manager import policy
from project_manager.project_manager.permissions import has_project_member_permission
from project_manager.project_manager.setup import install
from project_manager.tests.helpers import (
    TAG,
    PMTestCase,
    add_member,
    drop_project,
    drop_user,
    make_project,
    make_task,
    make_user,
)

ADMIN = f"ps.admin.{TAG}@example.com"
DIRECTOR = f"ps.director.{TAG}@example.com"
MANAGER = f"ps.manager.{TAG}@example.com"
ENGINEER = f"ps.engineer.{TAG}@example.com"
LEAD = f"ps.lead.{TAG}@example.com"
OUTSIDER = f"ps.outsider.{TAG}@example.com"
AUDITOR = f"ps.auditor.{TAG}@example.com"
USERS = (ADMIN, DIRECTOR, MANAGER, ENGINEER, LEAD, OUTSIDER, AUDITOR)


def visible(doctype, user, **filters):
    frappe.set_user(user)
    try:
        return set(frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0))
    finally:
        frappe.set_user("Administrator")


def allowed(doctype, name, ptype, user):
    return frappe.has_permission(doctype, ptype, doc=frappe.get_doc(doctype, name), user=user)


class TestProjectScope(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        make_user(ADMIN, [C.ADMIN_ROLE])
        make_user(DIRECTOR, [C.DIRECTOR_ROLE])
        for user in (MANAGER, ENGINEER, LEAD, OUTSIDER, AUDITOR):
            make_user(user, [C.STAFF_ROLE])
        cls.a, cls.b, cls.c = (make_project(f"PS {x}") for x in "ABC")
        cls.tasks = {}
        for project in (cls.a, cls.b, cls.c):
            root = make_task(project, f"Giai đoạn {project}", is_group=1)
            cls.tasks[project] = (root, make_task(project, f"Việc {project}", parent=root))
        add_member(cls.a, MANAGER, "Quản lý dự án")
        add_member(cls.a, ENGINEER, "Kỹ sư")
        add_member(cls.a, LEAD, "Tổ trưởng")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for project in (cls.a, cls.b, cls.c):
            drop_project(project)
        for user in USERS:
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    # --- reading -----------------------------------------------------------------------------------------------

    def test_administrator_sees_everything(self):
        self.assertLessEqual({self.a, self.b, self.c}, visible("Project", ADMIN))
        self.assertLessEqual(set(self.tasks[self.b]), visible("Task", ADMIN))

    def test_member_sees_only_their_projects_and_tasks(self):
        self.assertEqual(visible("Project", ENGINEER), {self.a})
        self.assertEqual(visible("Task", ENGINEER), set(self.tasks[self.a]))
        self.assertFalse(allowed("Task", self.tasks[self.b][1], "read", ENGINEER))
        self.assertTrue(allowed("Task", self.tasks[self.a][1], "read", ENGINEER))

    def test_outsider_sees_nothing(self):
        self.assertEqual(visible("Project", OUTSIDER), set())
        self.assertEqual(visible("Task", OUTSIDER), set())
        self.assertFalse(allowed("Project", self.a, "read", OUTSIDER))

    def test_assigned_only_role_sees_the_project_but_not_all_tasks(self):
        self.assertEqual(visible("Project", LEAD), {self.a})
        self.assertEqual(visible("Task", LEAD), set())  # their assignments come in M2

    def test_director_sees_every_project_but_changes_none(self):
        self.assertLessEqual({self.a, self.b, self.c}, visible("Project", DIRECTOR))
        self.assertLessEqual(set(self.tasks[self.c]), visible("Task", DIRECTOR))
        self.assertFalse(allowed("Project", self.a, "write", DIRECTOR))

    def test_membership_outside_its_dates_gives_nothing(self):
        add_member(self.b, OUTSIDER, "Kỹ sư", valid_to=frappe.utils.add_days(frappe.utils.nowdate(), -1))
        add_member(self.c, OUTSIDER, "Kỹ sư", valid_from=frappe.utils.add_days(frappe.utils.nowdate(), 1))
        self.assertEqual(visible("Project", OUTSIDER), set())
        add_member(self.b, OUTSIDER, "Kế toán dự án")
        self.assertEqual(visible("Project", OUTSIDER), {self.b})

    def test_inactive_membership_gives_nothing(self):
        add_member(self.b, OUTSIDER, "Kỹ sư", is_active=0)
        self.assertEqual(visible("Project", OUTSIDER), set())

    def test_every_list_path_is_scoped(self):
        frappe.set_user(ENGINEER)
        rows = frappe.call("frappe.client.get_list", doctype="Task", fields=["name"], limit_page_length=0)
        self.assertEqual({r["name"] for r in rows}, set(self.tasks[self.a]))
        from frappe.desk.reportview import execute  # what the report view (/desk list, export) runs

        names = {row.name for row in execute("Task", fields=["`tabTask`.`name`"], limit_page_length=0)}
        self.assertEqual(names, set(self.tasks[self.a]))
        with self.assertRaises(frappe.PermissionError):
            frappe.call("frappe.client.get", doctype="Task", name=self.tasks[self.b][1])
        links = frappe.call("frappe.desk.search.search_link", doctype="Project", txt="PS")
        self.assertEqual({r["value"] for r in links}, {self.a})

    # --- changing ----------------------------------------------------------------------------------------------

    def test_engineer_updates_tasks_but_does_not_restructure(self):
        task = self.tasks[self.a][1]
        self.assertTrue(allowed("Task", task, "write", ENGINEER))
        self.assertFalse(allowed("Task", task, "delete", ENGINEER))
        new = frappe.get_doc({"doctype": "Task", "subject": "x", "project": self.a})
        self.assertFalse(frappe.has_permission("Task", "create", doc=new, user=ENGINEER))
        self.assertFalse(allowed("Project", self.a, "write", ENGINEER))

    def test_manager_restructures_their_project_only(self):
        new = frappe.get_doc({"doctype": "Task", "subject": "x", "project": self.a})
        self.assertTrue(frappe.has_permission("Task", "create", doc=new, user=MANAGER))
        self.assertTrue(allowed("Project", self.a, "write", MANAGER))
        other = frappe.get_doc({"doctype": "Task", "subject": "x", "project": self.b})
        self.assertFalse(frappe.has_permission("Task", "create", doc=other, user=MANAGER))

    def test_creating_a_project_needs_the_capability(self):
        new = frappe.get_doc({"doctype": "Project", "project_name": "x"})
        self.assertFalse(frappe.has_permission("Project", "create", doc=new, user=ENGINEER))
        self.assertTrue(frappe.has_permission("Project", "create", doc=new, user=DIRECTOR))

    def test_members_are_managed_by_who_may_manage_them(self):
        member = frappe.get_doc({"doctype": "PM Project Member", "project": self.a, "user": OUTSIDER,
                                 "project_role": "Kỹ sư"})
        self.assertTrue(has_project_member_permission(member, "create", MANAGER))
        self.assertFalse(has_project_member_permission(member, "create", ENGINEER))

    def test_only_administrators_delete_a_project(self):
        self.assertFalse(allowed("Project", self.a, "delete", MANAGER))
        self.assertTrue(allowed("Project", self.a, "delete", ADMIN))

    # --- scopes beyond memberships -----------------------------------------------------------------------------

    def _access(self, read_scope, write_scope=C.WRITE_MEMBER, read=(), write=()):
        frappe.get_doc({"doctype": "PM Access", "user": AUDITOR, "read_scope": read_scope, "write_scope": write_scope,
                        "read_projects": [{"project": p} for p in read],
                        "write_projects": [{"project": p} for p in write]}).insert(ignore_permissions=True)
        policy.clear_cache()

    def test_chosen_projects_are_read_only_by_default(self):
        self._access(C.READ_CHOSEN, read=[self.b])
        self.assertEqual(visible("Project", AUDITOR), {self.b})
        self.assertEqual(visible("Task", AUDITOR), set(self.tasks[self.b]))
        self.assertFalse(allowed("Task", self.tasks[self.b][1], "write", AUDITOR))

    def test_write_as_read_gives_the_working_capabilities(self):
        self._access(C.READ_CHOSEN, C.WRITE_SAME, read=[self.b])
        self.assertTrue(allowed("Task", self.tasks[self.b][1], "write", AUDITOR))
        self.assertIn("plan.edit", policy.capabilities_in(self.b, AUDITOR))
        self.assertNotIn("project.members", policy.capabilities_in(self.b, AUDITOR))

    def test_every_project_scope(self):
        self._access(C.READ_ALL)
        self.assertLessEqual({self.a, self.b, self.c}, visible("Project", AUDITOR))
        self.assertFalse(allowed("Task", self.tasks[self.c][1], "write", AUDITOR))

    def test_written_projects_must_be_read(self):
        with self.assertRaises(frappe.ValidationError):
            self._access(C.READ_CHOSEN, C.WRITE_CHOSEN, read=[self.b], write=[self.c])

    def test_group_scope_adds_up_with_memberships(self):
        frappe.get_doc({"doctype": "PM Group", "group_name": f"PS nhóm {TAG}", "apply_scope": 1,
                        "read_scope": C.READ_CHOSEN, "read_projects": [{"project": self.c}],
                        "members": [{"user": ENGINEER}]}).insert(ignore_permissions=True)
        policy.clear_cache()
        self.assertEqual(visible("Project", ENGINEER), {self.a, self.c})

    # --- capabilities inside a project -------------------------------------------------------------------------

    def test_capabilities_follow_the_project_role(self):
        self.assertIn("project.members", policy.capabilities_in(self.a, MANAGER))
        self.assertEqual(policy.capabilities_in(self.a, ENGINEER), frozenset({"task.update", "material.request"}))
        self.assertEqual(policy.capabilities_in(self.b, ENGINEER), frozenset())
        self.assertEqual(policy.capabilities_in(self.b, ADMIN), C.PROJECT_CAPABILITY_CODES)
        self.assertIn("perf.view_project", policy.capabilities_in(self.b, DIRECTOR))

    def test_membership_grants_the_staff_role(self):
        user = make_user(f"ps.new.{TAG}@example.com")
        add_member(self.a, user, "Kỹ sư")
        self.assertIn(C.STAFF_ROLE, frappe.get_roles(user))
