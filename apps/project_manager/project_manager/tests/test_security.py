"""M11: the endpoints of the core and of the installed industry layers, enumerated.

* None is open to guests.
* An endpoint that changes data answers POST only (a link or an image tag cannot trigger it).
* A signed-in account that is not on the app's staff (a website user, an ERPNext-only accountant) is refused by every
  endpoint, except the few that only touch the caller's own account (OWN).
* The printed pages escape what users typed.
* Uploads: documents refuse what a browser would run (html, svg, scripts), photos are recognised by their bytes, and
  only PDF and pictures are ever shown inline (everything else downloads, with nosniff).

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_security
"""

import importlib
import inspect
import pkgutil

import frappe

from project_manager.tests.helpers import TAG, PMTestCase, drop_user, make_user

WEBSITE = f"sec.website.{TAG}@example.com"
ERP_ONLY = f"sec.accounts.{TAG}@example.com"
OWN = {"account.change_password", "account.get_notifications", "account.mark_notifications_read"}
READS = {"wbs.import_template"}  # a download of the empty template, though its name starts with a verb
WRITE_VERBS = {"save", "create", "delete", "remove", "update", "approve", "submit", "decide", "cancel", "close", "reopen",
               "book", "record", "assign", "respond", "move", "acknowledge", "mark", "send", "request", "add", "upload",
               "set", "reset", "purge", "import", "issue", "receive", "give", "write", "transfer", "confirm", "pass",
               "capture", "apply", "start", "discard", "attach", "follow", "comment", "edit", "change", "revise",
               "stop", "decline", "accept", "revoke", "duplicate", "copy", "restore", "enable", "disable"}


def apps() -> list[str]:
    """The core and the installed apps that build on it (the industry layers)."""
    return [app for app in frappe.get_installed_apps()
            if app == "project_manager" or "project_manager" in (frappe.get_hooks("required_apps", app_name=app) or [])]


def endpoints() -> list:
    for app in apps():
        try:
            package = importlib.import_module(f"{app}.{app}.api")
        except ImportError:
            continue
        for module in pkgutil.iter_modules(package.__path__):
            importlib.import_module(f"{app}.{app}.api.{module.name}")
    prefixes = tuple(f"{app}." for app in apps())
    return sorted((f for f in frappe.whitelisted if f.__module__.startswith(prefixes)), key=lambda f: (f.__module__, f.__name__))


def label(fn) -> str:
    return f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}"


def dummy_arguments(fn) -> dict:
    return {name: "x" for name, p in inspect.signature(fn).parameters.items()
            if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}


class TestEndpoints(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        make_user(WEBSITE, [], user_type="Website User")
        make_user(ERP_ONLY, ["Accounts User"])
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for user in (WEBSITE, ERP_ONLY):
            drop_user(user)
        frappe.db.commit()
        super().tearDownClass()

    def test_there_are_endpoints_to_check(self):
        self.assertGreater(len(endpoints()), 100)

    def test_none_is_open_to_guests(self):
        prefixes = tuple(f"{app}." for app in apps())
        mine = [f for f in frappe.guest_methods if getattr(f, "__module__", "").startswith(prefixes)]
        self.assertEqual([label(f) for f in mine], [])

    def test_what_changes_data_answers_post_only(self):
        loose = []
        for fn in endpoints():
            verb = fn.__name__.split("_", 1)[0]
            methods = frappe.allowed_http_methods_for_whitelisted_func.get(fn, [])
            if verb in WRITE_VERBS and label(fn) not in READS and methods != ["POST"]:
                loose.append(f"{label(fn)} {methods}")
        self.assertEqual(loose, [])

    def test_non_staff_are_refused(self):
        let_through = []
        for user in (WEBSITE, ERP_ONLY):
            for fn in endpoints():
                if label(fn) in OWN:
                    continue
                frappe.set_user(user)
                try:
                    fn(**dummy_arguments(fn))
                except frappe.PermissionError:
                    continue
                except Exception as e:  # anything else ran before the gate
                    let_through.append(f"{user.split('.')[1]} {label(fn)}: {type(e).__name__} {str(e)[:80]}")
                else:
                    let_through.append(f"{user.split('.')[1]} {label(fn)}: answered")
                finally:
                    frappe.set_user("Administrator")
                    frappe.local.response.pop("filecontent", None)
                    frappe.clear_messages()
        self.assertEqual(let_through, [])


class TestEscaping(PMTestCase):
    def test_printed_report_escapes_what_users_typed(self):
        from project_manager.project_manager.services.reports import output

        result = {"title": "<b>Tiến độ</b>", "columns": [{"fieldname": "a", "label": "Dự án", "fieldtype": "Data"}],
                  "rows": [{"a": "<script>alert(1)</script>"}], "summary": None, "info": [], "landscape": True}
        html = output.render_html(result, [("Lọc", "<img src=x onerror=alert(1)>")])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_inline_json_cannot_close_its_script(self):
        from project_manager.project_manager.services.web import inline_json

        text = inline_json({"name": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", text)


class TestUploads(PMTestCase):
    def test_documents_refuse_what_a_browser_would_run(self):
        from project_manager.project_manager.services import documents

        for name in ("ban-ve.html", "logo.SVG", "x.xhtml", "cai-dat.exe", "a.js"):
            with self.assertRaises(frappe.ValidationError):
                documents._check_file(b"<script>alert(1)</script>", name)
        self.assertEqual(documents._check_file(b"%PDF-1.7", "../../ho-so.pdf"), ("ho-so.pdf", "application/pdf"))

    def test_only_safe_types_open_in_the_browser(self):
        from project_manager.project_manager.services import files

        self.assertFalse({"text/html", "image/svg+xml", "application/xhtml+xml", "text/javascript"} & files.INLINE_TYPES)
        self.assertTrue(files.disposition('a"\r\nb.pdf', False).startswith('attachment; filename="ab.pdf"'))

    def test_photos_are_read_by_their_bytes_not_their_name(self):
        from project_manager.project_manager.services import media

        self.assertIsNone(media.kind_of(b"<svg onload=alert(1)>"))
        self.assertEqual(media.kind_of(b"\x89PNG\r\n\x1a\n" + b"0" * 16)[1], "image/png")
