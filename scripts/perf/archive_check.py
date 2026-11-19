"""Timings of M12 (the project archive, pm_archive) on scratch data.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=pm.localhost -e PERF_PHOTOS=2000 -e PERF_FILES=15000 -e PERF_ITEMS=1500000 \\
        -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - seed < ../scripts/perf/archive_check.py
    ... - reset < ../scripts/perf/archive_check.py        (removes what it made; seed removes it at the end too)

1. A project (PERF-AR-01) with PERF_PHOTOS photos (real objects in MinIO, about 50 KB each) and 300 approved documents:
   filing them (compile), filing approval of the photo file (SHA-256 of every object), the integrity check of that file.
2. PERF_FILES archive files over 500 scratch projects (PERF-AR-RRR) with PERF_ITEMS items in all, inserted by SQL: the
   register (/pm/luu-tru) as the archivist, filtered, a text search, a project's tab, a page of a file of 5 000 items.
"""

import os
import sys
import time
from datetime import date

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
PHOTOS = int(os.environ.get("PERF_PHOTOS", "2000"))
FILES = int(os.environ.get("PERF_FILES", "15000"))
ITEMS = int(os.environ.get("PERF_ITEMS", "1500000"))
CODE = "PERF-AR-"
ARCHIVIST = "perf.archivist@example.com"
BATCH = 5000


def timed(label, fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms", flush=True)
    return result


def connect():
    frappe.init(site=SITE, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")


def reset():
    from project_manager.project_manager.services import object_storage

    projects = frappe.get_all("Project", filters={"pm_code": ["like", f"{CODE}%"]}, pluck="name")
    if projects and object_storage.configured():
        for collection, doctype, field in (("media", "PM Media", "object_key"), ("documents", "PM Document Version", "object_key"),
                                           ("archive", "PM Archive Item", "object_key")):
            keys = frappe.get_all(doctype, filters={"project": ["in", projects], field: ["like", "minio:%"]}, pluck=field,
                                  limit_page_length=0)
            if collection == "archive":
                keys = [k for k in keys if "/archive/" in k]
            object_storage.delete_many(keys, collection)
    while projects:
        chunk, projects = projects[:50], projects[50:]
        for table in ("PM Archive Item", "PM Archive File", "PM Media", "PM Document Version", "PM Document", "PM Activity",
                      "PM Project Member"):
            frappe.db.sql(f"delete from `tab{table}` where project in %(p)s", {"p": tuple(chunk)})
        frappe.db.sql("delete from `tabTask` where project in %(p)s", {"p": tuple(chunk)})
        frappe.db.sql("delete from `tabProject` where name in %(p)s", {"p": tuple(chunk)})
        frappe.db.commit()
    frappe.db.delete("PM Archive Check", {"started_by": ARCHIVIST})
    frappe.delete_doc("User", ARCHIVIST, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()


def _archivist():
    if not frappe.db.exists("User", ARCHIVIST):
        user = frappe.get_doc({"doctype": "User", "email": ARCHIVIST, "first_name": "Perf archivist", "send_welcome_email": 0,
                               "enabled": 1, "user_type": "System User",
                               "roles": [{"role": "PM Staff"}, {"role": "PM Archivist"}]})
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)


def _project(code, title, closed=False):
    doc = frappe.get_doc({"doctype": "Project", "project_name": title, "pm_code": code,
                          "pm_state": "Đóng" if closed else "Đang thực hiện",
                          "company": frappe.defaults.get_global_default("company"), "percent_complete_method": "Manual",
                          "expected_start_date": add_days(nowdate(), -300), "expected_end_date": add_days(nowdate(), -10)})
    doc.insert(ignore_permissions=True)
    return doc.name


def part_one():
    """A real project: photos in MinIO, documents, filed, checked."""
    from project_manager.project_manager.services import documents, object_storage
    from project_manager.project_manager.services.queries import reserve_ids

    from pm_archive.pm_archive.services import filing, integrity, locking

    project = _project(f"{CODE}01", "Đo lưu trữ: dự án thật")
    blob = os.urandom(50 * 1024)
    rows, now = [], now_datetime()
    started = time.perf_counter()
    for number, name in enumerate(reserve_ids("PM Media", PHOTOS)):
        key = object_storage.put(blob + number.to_bytes(4, "big"), f"anh-{number}.jpg", "image/jpeg", "media")
        rows.append((name, project, "Project", project, f"anh-{number}.jpg", "image/jpeg", len(blob) + 4, key,
                     f"perf-ar-{project}-{number}", 0, add_days(nowdate(), -number % 200), "Administrator",
                     "Administrator", "Administrator", now, now, 0, 0))
    frappe.db.bulk_insert("PM Media", ("name", "project", "reference_doctype", "reference_name", "file_name",
                                       "content_type", "size_bytes", "object_key", "client_uuid", "is_deleted", "taken_at",
                                       "uploaded_by", "owner", "modified_by", "creation", "modified", "docstatus", "idx"),
                          rows, chunk_size=1000)
    print(f"{PHOTOS} photos into MinIO: {(time.perf_counter() - started):.1f} s", flush=True)
    for number in range(300):
        name = documents.create(project, f"Tài liệu {number}", os.urandom(20 * 1024), f"tai-lieu-{number}.pdf",
                                ("Hợp đồng", "Biên bản", "Bản vẽ", "Khác")[number % 4])["name"]
        documents.approve(name, 1)
    frappe.db.commit()
    result = timed(f"compile: {PHOTOS} photos + 300 documents into files", filing.compile, project)
    print(f"  added {result['added']} items in {len(result['files'])} files")
    timed("compile again (nothing new)", filing.compile, project)
    frappe.db.commit()
    photos = frappe.db.get_value("PM Archive File", {"project": project, "category": "02.01"}, "name")
    started = time.perf_counter()
    ok = locking.run(photos, ARCHIVIST)
    seconds = time.perf_counter() - started
    megabytes = PHOTOS * len(blob) / 1024 / 1024
    print(f"filing approval of {PHOTOS} photos (SHA-256 of each object): {seconds:.1f} s, "
          f"{megabytes / seconds:.0f} MB/s, {PHOTOS / seconds:.0f} items/s, ok={ok}", flush=True)
    started = time.perf_counter()
    check = integrity.run(trigger="Thủ công", file=photos)
    seconds = time.perf_counter() - started
    print(f"integrity check of that file: {seconds:.1f} s, status {frappe.db.get_value('PM Archive Check', check, 'status')}",
          flush=True)


def part_two():
    """Volume: many files and items, inserted by SQL."""
    from project_manager.project_manager.services.queries import reserve_ids

    from pm_archive.pm_archive import permissions
    from pm_archive.pm_archive.services import register

    projects = [_project(f"{CODE}{number:03d}", f"Đo lưu trữ {number:03d}", closed=number % 3 == 0)
                for number in range(100, 600)]
    frappe.db.commit()
    categories = frappe.get_all("PM Archive Category", filters={"is_group": 0}, pluck="name")
    states = ("Đang lập", "Chờ nộp lưu", "Đã nộp lưu")
    now, per_project = now_datetime(), max(1, FILES // len(projects))
    started = time.perf_counter()
    rows, files = [], []
    for index, project in enumerate(projects):
        for number in range(per_project):
            name = f"HSLT-P{index:03d}{number:03d}"
            end = add_days(nowdate(), -(index * 7 + number) % 2000)
            rows.append((name, project, categories[number % len(categories)], f"{CODE}{index:03d}-{number:02d}",
                         f"Hồ sơ {number} của dự án {index}", states[number % 3], "Nội bộ dự án", "10", add_days(end, -90),
                         end, date(getdate(end).year + 10, 12, 31), 0, 0, "Administrator", "Administrator",
                         now, now, 0, 0))
            files.append((name, project))
    frappe.db.bulk_insert("PM Archive File", ("name", "project", "category", "file_number", "title", "status", "access_mode",
                                              "retention", "start_date", "end_date", "expires_on", "item_count",
                                              "page_count", "owner", "modified_by", "creation", "modified", "docstatus", "idx"),
                          rows, chunk_size=1000)
    frappe.db.commit()
    per_file = max(1, ITEMS // len(files))
    fields = ("name", "archive_file", "project", "seq", "kind", "title", "doc_date", "page_count", "size_bytes",
              "excluded", "source_doctype", "source_name", "file_name", "owner", "modified_by", "creation", "modified",
              "docstatus", "idx")
    buffer = []
    big = files[0][0]
    for file, project in files:
        count = 5000 if file == big else per_file
        for seq in range(1, count + 1):
            buffer.append((None, file, project, seq, "Ảnh", f"Ảnh hiện trường {seq} của {file}", nowdate(), 0, 0, 0,
                           "PM Media", f"perf-{file}-{seq}", f"anh-{seq}.jpg", "Administrator", "Administrator", now, now,
                           0, 0))
            if len(buffer) >= BATCH:
                ids = reserve_ids("PM Archive Item", len(buffer))
                frappe.db.bulk_insert("PM Archive Item", fields, [(i, *row[1:]) for i, row in zip(ids, buffer, strict=True)],
                                      chunk_size=BATCH)
                frappe.db.commit()
                buffer = []
    if buffer:
        ids = reserve_ids("PM Archive Item", len(buffer))
        frappe.db.bulk_insert("PM Archive Item", fields, [(i, *row[1:]) for i, row in zip(ids, buffer, strict=True)],
                              chunk_size=BATCH)
        frappe.db.commit()
    print(f"{len(files)} files, {frappe.db.count('PM Archive Item')} items in all: {(time.perf_counter() - started):.0f} s",
          flush=True)

    frappe.set_user(ARCHIVIST)
    permissions.sees_everything()
    timed("register, page 1 (archivist, every project)", register.listing, {})
    first = register.listing({})
    timed("register, page 2 (keyset)", register.listing, {}, first["next"])
    timed("register, waiting files only", register.listing, {"status": "Chờ nộp lưu"})
    timed("register, year filter", register.listing, {"year": getdate(nowdate()).year})
    timed("register, text search (titles of files and items)", register.listing, {"search": "dự án 42"})
    timed("a project's tab (30 files)", register.overview, projects[1])
    timed("a file of 5 000 items, first page of 500", register.detail, big)
    from project_manager.project_manager.services import reports

    timed("catalogue of files, one project", reports.run, "muc-luc-ho-so", {"project": projects[1]})
    timed("catalogue of files, every project, page 1", reports.run, "muc-luc-ho-so", {})
    timed("catalogue of items of the 5 000-item file, page 1", reports.run, "muc-luc-van-ban", {"archive_file": big})
    frappe.set_user("Administrator")


def wait_for_jobs(limit=50, timeout=900):
    """Each document created queues jobs (search index, thumbnails): a run right after another waits for them, or Frappe
    refuses new jobs past 500 (QueueOverloaded)."""
    from frappe.utils.background_jobs import get_queue

    end = time.time() + timeout
    while time.time() < end:
        waiting = {name: len(get_queue(name)) for name in ("default", "short", "pm", "long")}
        if max(waiting.values()) <= limit:
            return
        print(f"waiting for queued jobs: {waiting}", flush=True)
        time.sleep(15)


def seed():
    connect()
    wait_for_jobs()
    reset()
    _archivist()
    frappe.db.commit()
    try:
        part_one()
        part_two()
    finally:
        frappe.set_user("Administrator")
        reset()
        print("scratch data removed")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if command == "reset":
        connect()
        reset()
        print("scratch data removed")
    else:
        seed()
