"""Shared test base and factories.

PMTestCase isolates every test: `frappe.db.commit` does nothing and the test runs inside a savepoint that is rolled
back afterwards, with Frappe's permission caches and the policy memo cleared. Data a whole class needs is made in
`setUpClass` (committed) and removed in `tearDownClass`; names carry a random tag so runs never collide.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from project_manager.project_manager import policy

TAG = frappe.generate_hash(length=5).lower()


def forget_caches():
    """Permission rules live in Frappe's caches too: after a rollback they must be read again."""
    frappe.clear_cache()
    frappe.local.role_permissions = {}
    policy.clear_cache()


class PMTestCase(IntegrationTestCase):
    savepoint = "pm_test"

    def setUp(self):
        commit = patch.object(frappe.db, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        frappe.set_user("Administrator")
        frappe.db.savepoint(self.savepoint)
        policy.clear_cache()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point=self.savepoint)
        forget_caches()


class MemoryStore:
    """In-memory stand-in for MinIO (services/object_storage.backend), so tests leave nothing in the bucket."""

    def __init__(self):
        self.objects = {}

    def put(self, path, data, content_type, metadata):
        self.objects[path] = (bytes(data), content_type)

    def get(self, path):
        return self.objects[path][0]

    def open(self, path):
        data, content_type = self.objects[path]
        return iter([data]), content_type, len(data)

    def delete(self, path):
        self.objects.pop(path, None)

    def keys(self, prefix):
        from datetime import datetime, timezone

        return [(path, datetime(2000, 1, 1, tzinfo=timezone.utc)) for path in self.objects if path.startswith(prefix)]

    def ping(self):
        return True


def memory_store(case) -> MemoryStore:
    from project_manager.project_manager.services import object_storage

    store = MemoryStore()
    replaced = patch.object(object_storage, "backend", lambda: store)
    replaced.start()
    case.addCleanup(replaced.stop)
    return store


def make_user(email: str, roles=(), user_type: str = "System User") -> str:
    if frappe.db.exists("User", email):
        frappe.delete_doc("User", email, force=True, ignore_permissions=True)
    doc = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                          "send_welcome_email": 0, "user_type": user_type, "roles": [{"role": r} for r in roles]})
    doc.flags.no_welcome_mail = True
    doc.insert(ignore_permissions=True)
    return email


def drop_user(email: str):
    for name in frappe.get_all("PM Project Member", filters={"user": email}, pluck="name"):
        frappe.delete_doc("PM Project Member", name, force=True, ignore_permissions=True)
    frappe.delete_doc("PM Access", email, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)


def make_project(title: str) -> str:
    company = frappe.defaults.get_global_default("company")
    doc = frappe.get_doc({"doctype": "Project", "project_name": f"{title} {TAG}", "company": company})
    doc.insert(ignore_permissions=True)
    return doc.name


def drop_project(project: str):
    """Delete a project with its tasks (children first) and memberships."""
    for name in frappe.get_all("PM Project Member", filters={"project": project}, pluck="name"):
        frappe.delete_doc("PM Project Member", name, force=True, ignore_permissions=True)
    frappe.db.delete("PM Activity", {"project": project})
    # history: never deleted by the app
    for doctype in ("PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Form Submission", "PM Gate Requirement",
                    "PM Task Dependency", "PM Baseline Task", "PM Baseline Curve", "PM Baseline", "PM Media",
                    "PM Follow", "PM Document Version", "PM Document", "PM Alert"):
        frappe.db.delete(doctype, {"project": project})
    for name in frappe.get_all("Task", filters={"project": project}, pluck="name", order_by="pm_level desc"):
        frappe.delete_doc("Task", name, force=True, ignore_permissions=True)
    frappe.delete_doc("Project", project, force=True, ignore_permissions=True, ignore_missing=True)


def drop_team(team: str):
    frappe.db.delete("PM Task Assignment", {"team": team})
    frappe.delete_doc("PM Team", team, force=True, ignore_permissions=True, ignore_missing=True)


def make_task(project: str | None, subject: str, parent: str | None = None, is_group: int = 0, **values) -> str:
    doc = frappe.get_doc({"doctype": "Task", "subject": subject, "project": project, "parent_task": parent,
                          "is_group": is_group, **values})
    doc.insert(ignore_permissions=True)
    return doc.name


def add_member(project: str, user: str, role: str = "Kỹ sư", **values) -> str:
    doc = frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": user, "project_role": role,
                          **values})
    doc.insert(ignore_permissions=True)
    policy.clear_cache()
    return doc.name
