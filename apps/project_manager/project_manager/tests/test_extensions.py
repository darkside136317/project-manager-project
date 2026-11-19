"""M12: what an industry layer may add to the core through hooks (project_manager/extensions.py): its capabilities
(global and inside a project), its kind of objects in MinIO, its sidebar entries; and the project's data as files
(closing.data_parts), which the dossier and an archive share.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_extensions
"""

from unittest.mock import patch

import frappe

from project_manager.project_manager import constants as C
from project_manager.project_manager import extensions, policy
from project_manager.project_manager.api import boot
from project_manager.project_manager.services import closing, object_storage
from project_manager.tests.helpers import TAG, PMTestCase, make_project, memory_store

HERE = "project_manager.tests.test_extensions."


def layer_capabilities():
    return [{"code": "zz.test", "label": "Chức năng thử", "module": "Thử", "builtin": [C.DIRECTOR_ROLE]}]


def layer_project_capabilities():
    return [{"code": "zz.project", "label": "Chức năng thử trong dự án"}]


def layer_nav(user):
    return [{"group": boot.GROUP_WORK, "label": "Màn thử", "route": "/pm/thu", "icon": "archive"},
            {"group": "Nhóm thử", "label": "Màn thử khác", "route": "/pm/thu-khac", "icon": "box"}]


class TestLayerHooks(PMTestCase):
    def hooks(self, **values):
        """frappe.get_hooks answers `values` for these hooks, the real hooks otherwise."""
        original = frappe.get_hooks

        def answer(hook=None, *args, **kwargs):
            if hook in values:
                return values[hook]
            return original(hook, *args, **kwargs)  # (Frappe's own default means "an empty list")

        replaced = patch("frappe.get_hooks", side_effect=answer)
        replaced.start()
        self.addCleanup(replaced.stop)

    def test_a_layer_capability_can_be_granted(self):
        role = {"doctype": "PM Project Role", "role_name": f"Vai trò thử {TAG}", "task_visibility": C.VISIBILITY_ALL,
                "capabilities": [{"capability": "zz.project"}]}
        with self.assertRaises(frappe.ValidationError):  # unknown before the layer declares it
            frappe.get_doc(dict(role)).insert(ignore_permissions=True)
        self.hooks(pm_capabilities=[HERE + "layer_capabilities"],
                   pm_project_capabilities=[HERE + "layer_project_capabilities"])
        self.assertIn("zz.test", extensions.capability_codes())
        self.assertIn(("zz.test", "Chức năng thử", "Thử"), extensions.capabilities())
        self.assertIn("zz.test", extensions.builtin_capabilities()[C.DIRECTOR_ROLE])
        self.assertIn("zz.project", extensions.project_capability_codes())
        frappe.get_doc(dict(role)).insert(ignore_permissions=True)  # a project role may now hold it
        policy.clear_cache()
        self.assertIn("zz.test", policy.capabilities_of("Administrator"))
        self.assertIn("zz.project", policy.capabilities_in(make_project("Dự án thử quyền"), "Administrator"))

    def test_a_layer_collection_is_allowed_and_its_keys_survive_the_sweep(self):
        store = memory_store(self)
        with self.assertRaises(ValueError):
            object_storage.put(b"x", "a.txt", "text/plain", "zzthu")
        self.hooks(pm_object_stores={"zzthu": [("Note", "title")]})
        kept = object_storage.put(b"giu lai", "a.txt", "text/plain", "zzthu")
        orphan = object_storage.put(b"mo coi", "b.txt", "text/plain", "zzthu")
        self.assertEqual(object_storage.get(kept, "zzthu"), b"giu lai")
        frappe.get_doc({"doctype": "Note", "title": kept, "public": 0}).insert(ignore_permissions=True)
        object_storage.sweep_orphans()
        paths = set(store.objects)
        self.assertIn(kept[len(object_storage.PREFIX):], paths)
        self.assertNotIn(orphan[len(object_storage.PREFIX):], paths)

    def test_a_layer_adds_to_the_sidebar(self):
        self.hooks(pm_nav_items=[HERE + "layer_nav"])
        nav = boot.build_boot()["nav"]
        work = next(g for g in nav if g["group"] == boot.GROUP_WORK)
        self.assertIn("/pm/thu", [item["route"] for item in work["items"]])
        other = next(g for g in nav if g["group"] == "Nhóm thử")
        self.assertEqual([item["route"] for item in other["items"]], ["/pm/thu-khac"])


class TestDataParts(PMTestCase):
    def test_the_projects_data_as_files(self):
        project = make_project("Dự án thử dữ liệu")
        paths = [part["path"] for part in closing.data_parts(project)]
        for path in ("du-an.json", "cong-viec.csv", "thanh-vien.csv"):
            self.assertIn(path, paths)
        self.assertFalse([p for p in paths if p.startswith(("tai-lieu/", "bieu-mau/"))])  # files are the dossier's
        self.assertTrue(all(isinstance(part["content"], bytes | str) and part["source"]
                            for part in closing.data_parts(project)))
