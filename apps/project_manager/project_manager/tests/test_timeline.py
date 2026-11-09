"""M5: the discussion of a task — comments sent once, @mentions, followers, pages, who sees what; photos sent before
their comment (and only once), thumbnails; project documents with versions and approval; search within the scope.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_timeline
"""

import io
import uuid
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager import permissions, policy
from project_manager.project_manager.services import (
    activity,
    assignments,
    documents,
    media,
    search_index,
    timeline,
    tree,
)
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
    memory_store,
)

ADMIN = f"tl.admin.{TAG}@example.com"
MANAGER = f"tl.manager.{TAG}@example.com"
ENGINEER = f"tl.engineer.{TAG}@example.com"
LEAD = f"tl.lead.{TAG}@example.com"
OUTSIDER = f"tl.outsider.{TAG}@example.com"
USERS = (ADMIN, MANAGER, ENGINEER, LEAD, OUTSIDER)


def as_user(user, fn, /, *args, **kwargs):
    frappe.set_user(user)
    policy.clear_cache()
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.set_user("Administrator")
        policy.clear_cache()


def picture(kind="JPEG", size=(64, 48), color=(200, 80, 40)) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, kind)
    return out.getvalue()


def mention(user) -> str:
    return f"@[{user.split('@')[0]}]({user})"


class TimelineBase(PMTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        install.seed_all()
        make_user(ADMIN, [C.ADMIN_ROLE])
        for user in USERS[1:]:
            make_user(user, [C.STAFF_ROLE])
        cls.project = make_project("TL")
        add_member(cls.project, MANAGER, "Quản lý dự án")
        add_member(cls.project, ENGINEER, "Kỹ sư")
        add_member(cls.project, LEAD, "Tổ trưởng")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        drop_project(cls.project)
        for user in USERS:
            frappe.db.delete("Notification Log", {"for_user": user})
            drop_user(user)
        frappe.db.commit()
        policy.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.store = memory_store(self)
        self.mine = make_task(self.project, "Cốp pha tầng 2", exp_end_date=add_days(nowdate(), 5))
        self.other = make_task(self.project, "Thép tầng 2", exp_end_date=add_days(nowdate(), 5))
        assignments.assign(self.mine, C.ACCOUNTABLE, user=LEAD)
        policy.clear_cache()

    def comment(self, user, task, text="Đã kiểm tra cốp pha", **kwargs):
        return as_user(user, timeline.post, "Task", task, text, **kwargs)

    def notices(self, user) -> list[str]:
        return frappe.get_all("Notification Log", filters={"for_user": user}, pluck="subject", order_by="creation asc")


class TestComments(TimelineBase):
    def test_a_comment_mentions_and_follows(self):
        entry = self.comment(ENGINEER, self.other, f"Nhờ {mention(MANAGER)} xem giúp")
        self.assertEqual(entry["type"], timeline.COMMENT)
        self.assertEqual(entry["mentions"], [MANAGER])
        page = as_user(MANAGER, timeline.feed, "Task", self.other)
        self.assertEqual(page["entries"][0]["name"], entry["name"])
        self.assertEqual(page["entries"][0]["actor_name"], ENGINEER.split("@")[0])
        self.assertTrue(any("nhắc bạn" in text for text in self.notices(MANAGER)))
        self.assertTrue(page["following"])  # mentioned people follow
        self.assertTrue(as_user(ENGINEER, timeline.feed, "Task", self.other)["following"])  # so does the writer

    def test_a_comment_sent_twice_is_kept_once(self):
        key = str(uuid.uuid4())
        first = self.comment(ENGINEER, self.other, client_uuid=key)
        again = self.comment(ENGINEER, self.other, "nội dung khác", client_uuid=key)
        self.assertEqual(first["name"], again["name"])
        self.assertEqual(frappe.db.count("PM Activity", {"client_uuid": key}), 1)
        with self.assertRaises(frappe.PermissionError):
            self.comment(MANAGER, self.other, client_uuid=key)  # another person's key

    def test_nothing_to_say_or_too_much(self):
        with self.assertRaises(frappe.ValidationError):
            self.comment(ENGINEER, self.other, "   ")
        with self.assertRaises(frappe.ValidationError):
            self.comment(ENGINEER, self.other, "x" * (timeline.MAX_TEXT + 1))

    def test_a_mention_of_someone_who_cannot_see_the_task_stays_text(self):
        entry = self.comment(ENGINEER, self.other, f"{mention(LEAD)} {mention(OUTSIDER)} chú ý")
        self.assertEqual(entry["mentions"], [])
        self.assertFalse([text for text in self.notices(LEAD) if "nhắc bạn" in text])
        self.assertFalse(self.notices(OUTSIDER))

    def test_followers_hear_of_new_comments(self):
        frappe.db.delete("Notification Log", {"for_user": ["in", [LEAD, ENGINEER]]})
        self.comment(ENGINEER, self.mine, "Thiếu gông cột trục 3")
        self.assertTrue(any("bình luận" in text for text in self.notices(LEAD)))  # assigned, so following
        self.assertFalse(self.notices(ENGINEER))  # never about one's own comment
        as_user(LEAD, timeline.follow, "Task", self.mine, False)
        frappe.db.delete("Notification Log", {"for_user": LEAD})
        self.comment(ENGINEER, self.mine, "Đã bổ sung")
        self.assertFalse(self.notices(LEAD))

    def test_pages_do_not_overlap(self):
        for number in range(35):
            activity.record("Task", self.other, "Thay đổi", f"thay đổi {number}")
        first = as_user(ENGINEER, timeline.feed, "Task", self.other, None, 30)
        self.assertTrue(first["more"])
        self.assertEqual(len(first["entries"]), 30)
        second = as_user(ENGINEER, timeline.feed, "Task", self.other, first["next"], 30)
        names = [e["name"] for e in first["entries"]] + [e["name"] for e in second["entries"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names, sorted(names, reverse=True))
        only = as_user(ENGINEER, timeline.feed, "Task", self.other, kind="comment")
        self.assertFalse(only["entries"])

    def test_only_the_writer_takes_a_comment_back(self):
        entry = self.comment(ENGINEER, self.other, "Ghi nhầm")
        with self.assertRaises(frappe.PermissionError):
            as_user(MANAGER, timeline.hide, entry["name"])
        as_user(ENGINEER, timeline.hide, entry["name"])
        self.assertNotIn(entry["name"], [e["name"] for e in as_user(ENGINEER, timeline.feed, "Task", self.other)["entries"]])
        self.assertEqual(frappe.db.get_value("PM Activity", entry["name"], "is_deleted"), 1)  # kept, hidden

    def test_unread_until_read(self):
        as_user(MANAGER, timeline.follow, "Task", self.other, True)
        entry = self.comment(ENGINEER, self.other, "Đã đổ xong")
        self.assertEqual(as_user(MANAGER, timeline.feed, "Task", self.other)["unread"], 1)
        as_user(MANAGER, timeline.mark_read, "Task", self.other, entry["name"])
        self.assertEqual(as_user(MANAGER, timeline.feed, "Task", self.other)["unread"], 0)
        as_user(MANAGER, timeline.mark_read, "Task", self.other, 1)  # never backwards
        self.assertEqual(frappe.db.get_value("PM Follow", {"user": MANAGER, "reference_name": self.other},
                                             "last_read_id"), entry["name"])

    def test_people_to_mention(self):
        everyone = {p["user"] for p in as_user(ENGINEER, timeline.people, "Task", self.other)}
        self.assertIn(MANAGER, everyone)
        self.assertNotIn(LEAD, everyone)  # does not see that task
        self.assertIn(LEAD, {p["user"] for p in as_user(ENGINEER, timeline.people, "Task", self.mine)})


class TestScope(TimelineBase):
    def test_a_lead_reads_only_the_tasks_given_to_them(self):
        self.comment(ENGINEER, self.mine, "việc của tổ")
        self.comment(ENGINEER, self.other, "việc khác")
        project_note = as_user(MANAGER, timeline.post, "Project", self.project, "Họp giao ban 7h")
        self.assertTrue(as_user(LEAD, timeline.feed, "Task", self.mine)["entries"])
        with self.assertRaises(frappe.PermissionError):
            as_user(LEAD, timeline.feed, "Task", self.other)
        seen = as_user(LEAD, timeline.feed, "Project", self.project)["entries"]
        self.assertTrue({self.mine} >= {e["task"] for e in seen if e["task"]})
        self.assertIn(project_note["name"], [e["name"] for e in seen])
        listed = as_user(LEAD, frappe.get_list, "PM Activity", filters={"project": self.project},
                         fields=["task"], limit_page_length=0)
        self.assertFalse([row for row in listed if row.task == self.other])

    def test_an_outsider_reads_nothing(self):
        self.comment(ENGINEER, self.other)
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, timeline.feed, "Project", self.project)
        self.assertFalse(as_user(OUTSIDER, frappe.get_list, "PM Activity", filters={"project": self.project}))
        with self.assertRaises(frappe.PermissionError):
            as_user(OUTSIDER, timeline.post, "Task", self.other, "xin chào")

    def test_the_api_only_reads(self):
        entry = self.comment(ENGINEER, self.other)
        doc = frappe.get_doc("PM Activity", entry["name"])
        self.assertFalse(permissions.has_activity_permission(doc, "write", MANAGER))
        self.assertTrue(permissions.has_activity_permission(doc, "read", MANAGER))
        self.assertFalse(permissions.has_activity_permission(doc, "read", LEAD))
        follow = frappe.get_doc("PM Follow", {"user": ENGINEER, "reference_name": self.other})
        self.assertFalse(permissions.has_follow_permission(follow, "read", MANAGER))


class TestPhotos(TimelineBase):
    def upload(self, user=ENGINEER, task=None, key=None, raw=None, **kwargs):
        return as_user(user, media.upload, "Task", task or self.other, key or str(uuid.uuid4()), raw or picture(),
                       "anh.jpg", **kwargs)

    def test_photos_then_the_comment_that_carries_them(self):
        keys = [str(uuid.uuid4()), str(uuid.uuid4())]
        for key in keys:
            self.upload(key=key)
        entry = self.comment(ENGINEER, self.other, "Ảnh hiện trường", media=keys)
        self.assertEqual(len(entry["photos"]), 2)
        self.assertEqual(set(frappe.get_all("PM Media", filters={"client_uuid": ["in", keys]}, pluck="activity_id")),
                         {entry["name"]})
        self.assertEqual(len(self.store.objects), 2)

    def test_a_photo_sent_twice_is_kept_once(self):
        key = str(uuid.uuid4())
        first = self.upload(key=key)
        again = self.upload(key=key, raw=picture(color=(0, 0, 0)))
        self.assertEqual(first["name"], again["name"])
        self.assertEqual(frappe.db.count("PM Media", {"client_uuid": key}), 1)
        self.assertEqual(len(self.store.objects), 1)
        with self.assertRaises(frappe.PermissionError):
            self.upload(user=MANAGER, key=key)

    def test_a_comment_waits_for_its_photos(self):
        with self.assertRaises(frappe.ValidationError):
            self.comment(ENGINEER, self.other, "Ảnh", media=[str(uuid.uuid4())])
        key = str(uuid.uuid4())
        self.upload(user=MANAGER, key=key)
        with self.assertRaises(frappe.PermissionError):
            self.comment(ENGINEER, self.other, "Ảnh của người khác", media=[key])

    def test_the_api_carries_photos_and_comment(self):
        from project_manager.project_manager.api import activity as activity_api

        key = str(uuid.uuid4())
        self.upload(key=key)
        unattached = self.upload()
        entry = as_user(ENGINEER, activity_api.post, "Task", self.other, "Qua API", [key], str(uuid.uuid4()))
        self.assertEqual(len(entry["photos"]), 1)
        photos = [p["name"] for p in as_user(ENGINEER, media.gallery, self.project)["photos"]]
        self.assertNotIn(unattached["name"], photos)  # a photo not (yet) sent with a comment is not on the wall

    def test_only_pictures(self):
        with self.assertRaises(frappe.ValidationError):
            self.upload(raw=b"<html>not a picture</html>")
        self.assertTrue(self.upload(raw=picture("PNG"))["name"])
        with patch.object(media, "MAX_BYTES", 10):
            with self.assertRaises(frappe.ValidationError):
                self.upload()

    def test_when_and_where(self):
        taken = (now_datetime() - timedelta(hours=3)).replace(microsecond=0)
        row = self.upload(taken_at=str(taken), lat="10.7769", lng="106.7009")
        self.assertEqual(str(row["taken_at"]), str(taken))
        self.assertAlmostEqual(row["lat"], 10.7769)
        nonsense = self.upload(taken_at=str(now_datetime() + timedelta(days=30)), lat="123", lng="abc")
        self.assertIsNone(nonsense["taken_at"])
        self.assertIsNone(nonsense["lat"])
        self.assertIsNone(nonsense["lng"])

    def test_a_thumbnail_is_made_after_the_upload(self):
        from PIL import Image

        row = self.upload(raw=picture(size=(1600, 1200)))
        self.assertFalse(row["thumb"])
        media.make_thumbnail(row["name"])
        key = frappe.db.get_value("PM Media", row["name"], "thumb_key")
        self.assertTrue(key.startswith("minio:"))
        thumb = self.store.get(key[len("minio:"):])
        with Image.open(io.BytesIO(thumb)) as small:
            self.assertLessEqual(max(small.size), media.THUMB_SIDE)

    def test_who_may_look_at_a_photo(self):
        key = str(uuid.uuid4())
        row = self.upload(key=key)
        self.comment(ENGINEER, self.other, "", media=[key])
        response = as_user(MANAGER, media.serve, row["name"], "full")
        self.assertEqual(b"".join(response.response), picture())
        self.assertIn("immutable", response.headers["Cache-Control"])
        with self.assertRaises(frappe.DoesNotExistError):
            as_user(LEAD, media.serve, row["name"])
        photos = as_user(MANAGER, media.gallery, self.project)["photos"]
        self.assertEqual([p["name"] for p in photos], [row["name"]])
        self.assertFalse(as_user(LEAD, media.gallery, self.project)["photos"])

    def test_a_task_with_photos_is_cancelled_not_deleted(self):
        fresh = make_task(self.project, "Việc nhập nhầm")
        self.upload(task=fresh)
        with self.assertRaises(frappe.ValidationError):
            tree.delete(fresh)


class TestDocuments(TimelineBase):
    def create(self, user=MANAGER, raw=b"%PDF-1.4 ban ve", filename="mat-bang.pdf", task=None):
        return as_user(user, documents.create, self.project, "Mặt bằng tầng 2", raw, filename, "Bản vẽ", task)

    def test_versions_and_approval(self):
        doc = self.create()
        self.assertEqual((doc.current_version, doc.status), (1, documents.DRAFT))
        doc = as_user(MANAGER, documents.add_version, doc.name, b"%PDF-1.4 ban ve sua", "mat-bang-v2.pdf", "Sửa trục")
        self.assertEqual(doc.current_version, 2)
        doc = as_user(MANAGER, documents.approve, doc.name, 1)
        self.assertEqual((doc.approved_version, doc.status), (1, documents.DRAFT))  # newest still a draft
        doc = as_user(MANAGER, documents.approve, doc.name, 2)
        self.assertEqual((doc.approved_version, doc.status), (2, documents.APPROVED))
        states = {v.version_no: v.status for v in doc.versions}
        self.assertEqual(states, {1: documents.REPLACED, 2: documents.APPROVED})
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, documents.approve, doc.name, 1)
        history = frappe.get_all("PM Activity", filters={"project": self.project, "activity_type": "Tệp"}, pluck="content")
        self.assertEqual(len(history), 4)

    def test_an_older_draft_is_superseded(self):
        doc = self.create()
        as_user(MANAGER, documents.add_version, doc.name, b"%PDF-1.4 ban 2", "v2.pdf")
        doc = as_user(MANAGER, documents.approve, doc.name, 2)
        self.assertEqual({v.version_no: v.status for v in doc.versions}, {1: documents.REPLACED, 2: documents.APPROVED})

    def test_files_that_are_refused(self):
        doc = self.create()
        with self.assertRaises(frappe.ValidationError):
            as_user(MANAGER, documents.add_version, doc.name, b"%PDF-1.4 ban ve", "mat-bang.pdf")  # same file
        with self.assertRaises(frappe.ValidationError):
            self.create(filename="cai-dat.exe")
        with self.assertRaises(frappe.ValidationError):
            self.create(filename="trang.html")
        with patch.object(documents, "MAX_BYTES", 4):
            with self.assertRaises(frappe.ValidationError):
                self.create()

    def test_who_uploads_and_who_approves(self):
        doc = self.create(user=ENGINEER)  # any project role that may change data
        with self.assertRaises(frappe.PermissionError):
            as_user(ENGINEER, documents.approve, doc.name, 1)
        with self.assertRaises(frappe.PermissionError):
            self.create(user=OUTSIDER)

    def test_a_document_of_a_task_follows_the_task(self):
        general = self.create()
        of_other = self.create(task=self.other, filename="thep.pdf", raw=b"%PDF thep")
        self.assertTrue(as_user(LEAD, documents.detail, general.name))
        with self.assertRaises(frappe.DoesNotExistError):
            as_user(LEAD, documents.detail, of_other.name)
        listed = [d.name for d in as_user(LEAD, documents.listing, self.project)["documents"]]
        self.assertEqual(listed, [general.name])

    def test_download(self):
        doc = self.create(raw=b"%PDF-1.4 noi dung", filename="Mặt bằng.pdf")
        response = as_user(LEAD, documents.download, doc.name, None, 1)
        self.assertEqual(b"".join(response.response), b"%PDF-1.4 noi dung")
        self.assertTrue(response.headers["Content-Disposition"].startswith("inline"))
        self.assertIn("filename*=UTF-8''M%E1%BA%B7t", response.headers["Content-Disposition"])
        drawing = self.create(raw=b"AC1027 dwg", filename="ket-cau.dwg")
        response = as_user(MANAGER, documents.download, drawing.name, 1, 1)
        self.assertTrue(response.headers["Content-Disposition"].startswith("attachment"))
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")


class TestSearch(TimelineBase):
    def setUp(self):
        super().setUp()
        frappe.flags.pm_search_index = f"pm_test_{TAG}"

    def tearDown(self):
        try:
            client = search_index._client()
            client.wait_for_task(client.delete_index(frappe.flags.pm_search_index).task_uid, timeout_in_ms=10000)
        except Exception:
            pass
        search_index._ready.pop(frappe.flags.pm_search_index, None)
        frappe.flags.pm_search_index = None
        super().tearDown()

    def index(self, *names, document=None):
        client = search_index._client()
        for name in names:
            client.wait_for_task(search_index.index_activity(name).task_uid, timeout_in_ms=10000)
        if document:
            client.wait_for_task(search_index.index_document(document).task_uid, timeout_in_ms=10000)

    def test_results_stay_within_what_the_user_sees(self):
        word = f"gongcot{TAG}"
        own = self.comment(ENGINEER, self.mine, f"Thiếu {word} trục 3")
        other = self.comment(ENGINEER, self.other, f"Đã có {word} trục 5")
        doc = as_user(MANAGER, documents.create, self.project, f"Biện pháp {word}", b"%PDF bp", "bp.pdf", "Khác")
        self.index(own["name"], other["name"], document=doc.name)
        everything = {h["id"] for h in as_user(ENGINEER, search_index.search, word)["hits"]}
        self.assertEqual(everything, {f"act-{own['name']}", f"act-{other['name']}", f"doc-{doc.name}"})
        for_lead = {h["id"] for h in as_user(LEAD, search_index.search, word)["hits"]}
        self.assertEqual(for_lead, {f"act-{own['name']}", f"doc-{doc.name}"})
        self.assertFalse(as_user(OUTSIDER, search_index.search, word)["hits"])
        hit = as_user(ENGINEER, search_index.search, word, kind="document")["hits"][0]
        self.assertIn(search_index.MARK_START, hit["title"])  # the word is marked for the screen

    def test_a_hidden_comment_leaves_the_index(self):
        word = f"rutlai{TAG}"
        entry = self.comment(ENGINEER, self.other, f"Ghi {word}")
        self.index(entry["name"])
        as_user(ENGINEER, timeline.hide, entry["name"])
        self.index(entry["name"])  # indexing a hidden comment removes it
        self.assertFalse(as_user(ENGINEER, search_index.search, word)["hits"])
