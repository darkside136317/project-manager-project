"""Volume check: a million tasks on a scratch site, and the timings that matter at that size.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=perfpm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - seed    < ../scripts/perf/volume_check.py
    ... - extra   < ...        (M11: activities, photos, stock entries, people, overdue work on top of the tasks)
    ... - measure < ...        (timings, best of 3; nothing is kept)
    ... - reset   < ...        (removes the generated data)

Only a site whose name starts with "perf" is accepted: the script writes a million rows with plain SQL.
PERF_SCALE (default 1.0) multiplies the volume: 0.01 gives 10 000 tasks for a quick try.

Volume (scale 1): 500 projects (50 running with 6 000 tasks each, 450 closed with ~1 556 each) = 1 000 000 tasks in
trees of phase > group > task > sub-task, dates and `modified` spread over three years. `extra` (M11) adds the rest of
the plan's volume (docs/KE_HOACH.md, section 12): 5 000 000 discussion entries, 2 000 000 photos (metadata only),
100 000 stock entries, 500 people each a member of three running projects, a tenth of the running work overdue.
`measure` then times the thresholds of section 12 (Gantt, Kanban, roll-up, dashboard of 50 projects, deep keyset
pages, adding a task, a timeline page) and a few M7–M10 screens at that size.
"""

import os
import random
import sys
import time
from datetime import datetime, timedelta

import frappe

SITE = os.environ.get("PERF_SITE", "perfpm.localhost")
SCALE = float(os.environ.get("PERF_SCALE", "1"))
PREFIX = "PERF"
RUNNING, CLOSED = 50, 450
RUNNING_TASKS, CLOSED_TASKS = 6000, 1556
CHUNK = 2000
BIG_CHUNK = 5000
ACTIVITIES, PHOTOS, STOCK_ENTRIES, PEOPLE = 5_000_000, 2_000_000, 100_000, 500
PERSON = "perf.person.{:04d}@example.com"
ENGINEER = "perf.engineer@example.com"
DIRECTOR = "perf.director@example.com"
EPOCH = datetime(2023, 11, 1)


def connect():
    if not SITE.startswith("perf"):
        sys.exit(f"Refusing to run on {SITE}: the site name must start with 'perf'")
    frappe.init(SITE)
    frappe.connect()
    frappe.set_user("Administrator")


def seg(n):
    return f"{n:05d}"


def project_names():
    total = max(1, round((RUNNING + CLOSED) * SCALE))
    return [f"{PREFIX}-{i:04d}" for i in range(1, total + 1)]


def task_rows(project, index, count, rng):
    """Rows of one project's tree: 5 phases, groups of ~10 tasks, a sub-task under every fourth task."""
    rows = []
    start = EPOCH + timedelta(days=rng.randint(0, 900))
    phases = 5
    per_phase = max(1, count // phases)
    n = 0

    def add(parent, path, code, level, sort, is_group, subject):
        nonlocal n
        n += 1
        name = f"TASK-{PREFIX}-{index:04d}-{n:05d}"
        begin = start + timedelta(days=rng.randint(0, 600))
        modified = EPOCH + timedelta(seconds=rng.randint(0, 3 * 365 * 86400))
        rows.append((name, subject, project, parent, int(is_group), "Open", path, sort, level, code,
                     begin.date(), (begin + timedelta(days=rng.randint(1, 60))).date(), rng.randint(0, 100),
                     modified, modified))
        return name

    for p in range(1, phases + 1):
        if n >= count:
            break
        phase = add(None, seg(p), str(p), 1, p, 1, f"Giai đoạn {p}")
        budget = per_phase - 1
        g = 0
        while budget > 0 and n < count:
            g += 1
            gpath, gcode = f"{seg(p)}.{seg(g)}", f"{p}.{g}"
            group = add(phase, gpath, gcode, 2, g, 1, f"Hạng mục {p}.{g}")
            budget -= 1
            for t in range(1, 11):
                if budget <= 0 or n >= count:
                    break
                with_sub = t % 4 == 0 and budget > 1
                task = add(group, f"{gpath}.{seg(t)}", f"{gcode}.{t}", 3, t, int(with_sub), f"Công tác {gcode}.{t}")
                budget -= 1
                if with_sub:
                    add(task, f"{gpath}.{seg(t)}.{seg(1)}", f"{gcode}.{t}.1", 4, 1, 0, f"Việc con {gcode}.{t}.1")
                    budget -= 1
    return rows


def insert_tasks(rows):
    columns = ("name", "subject", "project", "parent_task", "is_group", "status", "pm_path", "pm_sort", "pm_level",
               "pm_wbs_code", "exp_start_date", "exp_end_date", "progress", "creation", "modified")
    placeholders = "(" + ", ".join(["%s"] * len(columns)) + ", 'Administrator', 'Administrator', 0, 0, 0, 0, 1, 'Medium')"
    sql = (f"insert into `tabTask` ({', '.join(columns)}, owner, modified_by, docstatus, idx, lft, rgt, "
           f"task_weight, priority) values ")
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        frappe.db.sql(sql + ", ".join([placeholders] * len(chunk)), [v for row in chunk for v in row])


def seed():
    connect()
    from project_manager.project_manager.setup.install import seed_all

    seed_all()
    company = frappe.defaults.get_global_default("company")
    rng = random.Random(42)
    names = project_names()
    running = set(names[:max(1, round(RUNNING * SCALE))])
    started = time.time()
    total = 0
    for index, project in enumerate(names, 1):
        if frappe.db.exists("Project", project):
            continue
        frappe.db.sql(
            """insert into `tabProject` (name, project_name, status, company, percent_complete_method, pm_state,
               creation, modified, owner, modified_by, docstatus, idx, is_active)
               values (%s, %s, %s, %s, 'Manual', %s, %s, %s, 'Administrator', 'Administrator', 0, 0, 'Yes')""",
            (project, f"Công trình {index:04d}", "Open" if project in running else "Completed", company,
             "Đang thực hiện" if project in running else "Đóng", EPOCH, EPOCH))
        rows = task_rows(project, index, RUNNING_TASKS if project in running else CLOSED_TASKS, rng)
        insert_tasks(rows)
        total += len(rows)
        frappe.db.commit()
        if index % 25 == 0:
            print(f"{index} projects, {total} tasks, {time.time() - started:.0f}s", flush=True)
    for email, roles in ((ENGINEER, ["PM Staff"]), (DIRECTOR, ["PM Director"])):
        if not frappe.db.exists("User", email):
            user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                                   "send_welcome_email": 0, "roles": [{"role": r} for r in roles]})
            user.flags.no_welcome_mail = True
            user.insert(ignore_permissions=True)
    for project in sorted(running)[:3]:
        if not frappe.db.exists("PM Project Member", {"project": project, "user": ENGINEER}):
            frappe.get_doc({"doctype": "PM Project Member", "project": project, "user": ENGINEER,
                            "project_role": "Kỹ sư"}).insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"seeded: {frappe.db.count('Project')} projects, {frappe.db.count('Task')} tasks, {time.time() - started:.0f}s")


def _count(n):
    return max(1, round(n * SCALE))


def _sequence(doctype, last):
    frappe.db.sql(f"select setval(`{frappe.scrub(doctype + '_id_seq')}`, %s)", last)


def _next_id(doctype):
    return (frappe.db.sql(f"select ifnull(max(name), 0) from `tab{doctype}`")[0][0] or 0) + 1


def _bulk(table, columns, rows):
    sql = f"insert into `{table}` ({', '.join(columns)}) values "
    holder = "(" + ", ".join(["%s"] * len(columns)) + ")"
    for i in range(0, len(rows), BIG_CHUNK):
        chunk = rows[i:i + BIG_CHUNK]
        frappe.db.sql(sql + ", ".join([holder] * len(chunk)), [v for row in chunk for v in row])


def extra():
    """M11: the rest of the plan's volume, on top of the tasks of `seed`."""
    connect()
    company = frappe.defaults.get_global_default("company")
    rng = random.Random(11)
    started = time.time()
    names = project_names()
    running = names[:max(1, round(RUNNING * SCALE))]
    # people: each a member of three running projects
    people = [PERSON.format(n) for n in range(1, _count(PEOPLE) + 1)]
    frappe.flags.in_import = True  # Frappe throttles the creation of many users an hour
    for email in people:
        if not frappe.db.exists("User", email):
            user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                                   "send_welcome_email": 0, "roles": [{"role": "PM Staff"}]})
            user.flags.no_welcome_mail = True
            user.insert(ignore_permissions=True)
    frappe.flags.in_import = False
    if not frappe.db.exists("PM Project Member", {"user": people[0]}):
        first = _next_id("PM Project Member")
        rows = [(first + i, project, user, "Kỹ sư", 1, EPOCH, EPOCH, "Administrator", "Administrator", 0)
                for i, (user, project) in enumerate((u, running[(n * 7 + k) % len(running)])
                                                     for n, u in enumerate(people) for k in range(3))]
        _bulk("tabPM Project Member", ("name", "project", "user", "project_role", "is_active", "creation", "modified",
                                       "owner", "modified_by", "docstatus"), rows)
        _sequence("PM Project Member", first + len(rows) - 1)
    frappe.db.commit()
    print(f"people: {len(people)}, {time.time() - started:.0f}s", flush=True)
    # overdue work: a tenth of the running projects' leaves
    frappe.db.sql("""update `tabTask` set pm_is_overdue = 1, pm_delay_days = 1 + mod(pm_sort, 20)
                      where project in %(running)s and is_group = 0 and mod(crc32(name), 10) = 0""",
                  {"running": tuple(running)})
    frappe.db.commit()
    # tasks of each project, to point activities and photos at
    leaves = {}
    for project, task in frappe.db.sql(f"select project, name from `tabTask` where name like 'TASK-{PREFIX}-%%' "
                                       "and is_group = 0 and mod(crc32(name), 7) = 0"):
        leaves.setdefault(project, []).append(task)
    weights = [(p, 60 if p in running else 4.4) for p in names if leaves.get(p)]
    total_weight = sum(w for _p, w in weights)
    kinds = ("Bình luận", "Tiến độ", "Thay đổi", "Giao việc", "Đổi hạn", "Trạng thái", "Tệp")
    for doctype, total, build in (
            ("PM Activity", _count(ACTIVITIES), lambda i, project, task, when: (
                i, project, "Task", task, task, kinds[i % len(kinds)], people[i % len(people)],
                f"Cập nhật hiện trường số {i}", when, when, "Administrator", "Administrator", 0, 0, 0)),
            ("PM Media", _count(PHOTOS), lambda i, project, task, when: (
                i, project, "Task", task, task, f"anh-{i}.jpg", "image/jpeg", 350_000, 1600, 1200, when,
                people[i % len(people)], f"perf/{i}.jpg", f"perf/{i}-thumb.jpg", when, when, "Administrator",
                "Administrator", 0, 0, 0))):
        if frappe.db.sql(f"select count(*) from `tab{doctype}` where content like 'Cập nhật hiện trường số %%'" if doctype == "PM Activity"
                         else f"select count(*) from `tab{doctype}` where object_key like 'perf/%%'")[0][0]:
            continue
        columns = (("name", "project", "reference_doctype", "reference_name", "task", "activity_type", "actor", "content",
                    "creation", "modified", "owner", "modified_by", "docstatus", "idx", "is_deleted")
                   if doctype == "PM Activity" else
                   ("name", "project", "reference_doctype", "reference_name", "task", "file_name", "content_type",
                    "size_bytes", "width", "height", "taken_at", "uploaded_by", "object_key", "thumb_key", "creation",
                    "modified", "owner", "modified_by", "docstatus", "idx", "is_deleted"))
        first, made, batch = _next_id(doctype), 0, []
        for project, weight in weights:
            share = round(total * weight / total_weight)
            tasks = leaves[project]
            for _k in range(share):
                when = EPOCH + timedelta(seconds=rng.randint(0, 3 * 365 * 86400))
                batch.append(build(first + made, project, tasks[made % len(tasks)], when))
                made += 1
                if len(batch) >= 100_000:
                    _bulk(f"tab{doctype}", columns, batch)
                    frappe.db.commit()
                    batch = []
            if made >= total:
                break
        if batch:
            _bulk(f"tab{doctype}", columns, batch)
        _sequence(doctype, first + made - 1)
        frappe.db.commit()
        print(f"{doctype}: {made}, {time.time() - started:.0f}s", flush=True)
    # stock entries of the projects (rows only: the stock ledger is not the point here)
    if not frappe.db.exists("Stock Entry", f"{PREFIX}-SE-0000001"):
        rows = []
        for i in range(1, _count(STOCK_ENTRIES) + 1):
            when = EPOCH + timedelta(seconds=rng.randint(0, 3 * 365 * 86400))
            rows.append((f"{PREFIX}-SE-{i:07d}", company, "Material Issue", "Material Issue", names[i % len(names)],
                         "Cấp phát" if i % 3 else "Nhập kho", when.date(), when, when, "Administrator", "Administrator", 1, 0))
        _bulk("tabStock Entry", ("name", "company", "purpose", "stock_entry_type", "project", "pmc_kind", "posting_date",
                                 "creation", "modified", "owner", "modified_by", "docstatus", "idx"), rows)
        frappe.db.commit()
    print(f"extra done: {frappe.db.count('PM Activity')} activities, {frappe.db.count('PM Media')} photos, "
          f"{frappe.db.count('Stock Entry')} stock entries, {time.time() - started:.0f}s")


def best_of(label, operation, runs=3, rollback=True):
    timings = []
    for _ in range(runs):
        frappe.db.savepoint("perf")
        started = time.perf_counter()
        operation()
        timings.append((time.perf_counter() - started) * 1000)
        if rollback:
            frappe.db.rollback(save_point="perf")
    best = min(timings)
    print(f"{label:<62} {best:9.1f} ms   (runs: {', '.join(f'{t:.0f}' for t in timings)})")
    return best


def as_user(user, operation):
    from project_manager.project_manager.policy import clear_cache

    def run():
        frappe.set_user(user)
        clear_cache()
        try:
            return operation()
        finally:
            frappe.set_user("Administrator")
    return run


def measure():
    connect()
    print(f"site {SITE}: {frappe.db.count('Project')} projects, {frappe.db.count('Task')} tasks")
    first = project_names()[0]
    group = frappe.db.get_value("Task", {"project": first, "pm_level": 2}, "name", order_by="pm_path asc")
    leaf_group = frappe.db.get_value("Task", {"project": first, "pm_level": 2}, "name", order_by="pm_path desc")
    other_phase = frappe.db.get_value("Task", {"project": first, "pm_level": 1}, "name", order_by="pm_path desc")

    def new_task(project, parent):
        return lambda: frappe.get_doc({"doctype": "Task", "subject": "Đo hiệu năng", "project": project,
                                       "parent_task": parent}).insert(ignore_permissions=True)

    best_of("insert a task under a group of the OLDEST project", new_task(first, group))
    best_of("insert a root task in the oldest project", new_task(first, None))
    best_of("move a group (with its tasks) to another phase", lambda: _move(leaf_group, other_phase))
    best_of("[ERPNext nested set] UPDATE every Task row once (rgt + 0)",
            lambda: frappe.db.sql("update `tabTask` set rgt = rgt + 0 where creation > '2000-01-01'"))
    best_of("engineer (3 projects): Task list, page 1, newest first",
            as_user(ENGINEER, lambda: frappe.get_list("Task", fields=["name", "subject", "status"],
                                                       order_by="modified desc", page_length=20)), rollback=False)
    best_of("engineer: one project's WBS in tree order (first 2 000)",
            as_user(ENGINEER, lambda: frappe.get_list("Task", filters={"project": project_names()[0]},
                                                       fields=["name", "pm_wbs_code", "subject"],
                                                       order_by="pm_path asc", page_length=2000)), rollback=False)
    best_of("director (all projects): Task list, page 1, newest first",
            as_user(DIRECTOR, lambda: frappe.get_list("Task", fields=["name", "subject"], order_by="modified desc",
                                                       page_length=20)), rollback=False)
    best_of("director: project list, page 1",
            as_user(DIRECTOR, lambda: frappe.get_list("Project", fields=["name", "project_name"],
                                                       order_by="modified desc", page_length=20)), rollback=False)
    best_of("engineer: count of their tasks",
            as_user(ENGINEER, lambda: frappe.db.count("Task") and frappe.get_list(
                "Task", fields=[{"COUNT": "name", "as": "c"}])), rollback=False)
    if frappe.db.exists("User", PERSON.format(1)):
        measure_m11(first)


def measure_m11(first):
    """The thresholds of the plan (section 12) and a few later screens, at full volume."""
    from project_manager.project_manager.services import (
        portfolio,
        progress,
        rollup,
        schedule,
        timeline,
        work,
        workload,
    )
    from project_manager.project_manager.services import reports as report_service

    person = PERSON.format(1)
    mine = frappe.db.get_value("PM Project Member", {"user": person}, "project")
    leaf = frappe.db.get_value("Task", {"project": mine, "is_group": 0, "pm_level": 3}, "name", order_by="pm_path asc")
    busy = frappe.db.sql("select reference_name from `tabPM Activity` where reference_doctype = 'Task' and project = %s "
                         "group by reference_name order by count(*) desc limit 1", mine)[0][0]
    deep = frappe.db.sql("select name from `tabPM Activity` where project = %s order by name desc limit 1 offset 40000",
                         mine)
    size = frappe.db.count("Task", {"project": mine})
    storekeeper = PERSON.format(2)  # sees the stock entries of their 3 projects (ERPNext asks for Stock User)
    if "Stock User" not in frappe.get_roles(storekeeper):
        frappe.get_doc("User", storekeeper).add_roles("Stock User")
        frappe.db.commit()
    print(f"--- M11 (section 12), {frappe.db.count('PM Activity')} activities, {frappe.db.count('PM Media')} photos")
    best_of("Gantt of a running project (first 2 000 rows), member", as_user(person, lambda: schedule.gantt(mine)),
            rollback=False)
    best_of("Kanban of a running project, member", as_user(person, lambda: work.kanban(mine)), rollback=False)
    best_of("my tasks, member of 3 projects", as_user(person, lambda: work.my_tasks()), rollback=False)
    reason = frappe.db.get_value("PM Delay Reason", {}, "name")
    source = frappe.db.get_value("PM Delay Source", {}, "name")  # the seeded work is in the past: it is late
    best_of("report progress on a task, member", as_user(person, lambda: progress.report(leaf, 55, "đo", reason, source)))
    parent = frappe.db.get_value("Task", leaf, "parent_task")
    best_of(f"roll-up after a report (its branch up to the project, {size} tasks)", lambda: (frappe.db.set_value(
        "Task", leaf, "progress", 60), rollup.recompute(mine, {parent})))
    best_of(f"reconcile the whole project ({size} tasks, nightly)", lambda: rollup.reconcile(mine))

    def cold_dashboard():
        frappe.cache.delete_value("pmc_cost_totals")  # the layer's cost totals (kept 10 minutes)
        frappe.local.pm_calendars = {}
        return portfolio.portfolio()

    best_of("dashboard of the running projects, director, cold caches", as_user(DIRECTOR, cold_dashboard),
            rollback=False)
    best_of("dashboard of the running projects, director", as_user(DIRECTOR, lambda: portfolio.portfolio()),
            rollback=False)
    best_of("timeline of a busy task, first page", as_user(person, lambda: timeline.feed("Task", busy)), rollback=False)
    best_of("timeline of a project, first page", as_user(person, lambda: timeline.feed("Project", mine)), rollback=False)
    if deep:
        best_of("timeline of a project, a page 40 000 entries back (keyset)",
                as_user(person, lambda: timeline.feed("Project", mine, before=deep[0][0])), rollback=False)
    best_of("task list, page 1 000 of 20 (keyset on pm_path), member", as_user(person, lambda: frappe.get_list(
        "Task", filters={"project": mine, "pm_path": [">", "00003"]}, fields=["name", "subject"], order_by="pm_path asc",
        page_length=20)), rollback=False)
    best_of("stock entries of my projects, page 1, storekeeper", as_user(storekeeper, lambda: frappe.get_list(
        "Stock Entry", fields=["name", "posting_date"], order_by="modified desc", page_length=20)), rollback=False)
    best_of("report: late work, page 1, director", as_user(DIRECTOR, lambda: report_service.run("cong-viec-tre", {})),
            rollback=False)
    best_of("report: project progress (running), director", as_user(DIRECTOR, lambda: report_service.run(
        "tien-do-du-an", {})), rollback=False)
    best_of("workload of a member (6 weeks)", as_user(person, lambda: workload.overview(None, 6)), rollback=False)
    best_of(f"insert a task in a {size}-task project (member's)", lambda: frappe.get_doc(
        {"doctype": "Task", "subject": "Đo", "project": mine, "parent_task": frappe.db.get_value(
            "Task", {"project": mine, "pm_level": 2}, "name")}).insert(ignore_permissions=True))


def _move(task, new_parent):
    doc = frappe.get_doc("Task", task)
    doc.parent_task = new_parent
    doc.save(ignore_permissions=True)


def reset():
    connect()
    for table, where in (("tabPM Activity", "content like 'Cập nhật hiện trường số %%'"),
                         ("tabPM Media", "object_key like 'perf/%%'"), ("tabStock Entry", f"name like '{PREFIX}-SE-%%'")):
        while frappe.db.sql(f"delete from `{table}` where {where} limit 200000") and frappe.db.sql(
                f"select 1 from `{table}` where {where} limit 1"):
            frappe.db.commit()
        frappe.db.commit()
    people = frappe.get_all("User", filters={"name": ["like", "perf.person.%"]}, pluck="name")
    frappe.db.delete("PM Project Member", {"user": ["in", people or [""]]})
    for email in people:
        frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
    for name in frappe.get_all("PM Project Member", filters={"user": ["in", [ENGINEER, DIRECTOR]]}, pluck="name"):
        frappe.delete_doc("PM Project Member", name, force=True, ignore_permissions=True)
    frappe.db.sql(f"delete from `tabTask` where name like 'TASK-{PREFIX}-%%'")
    frappe.db.sql(f"delete from `tabProject` where name like '{PREFIX}-%%'")
    for email in (ENGINEER, DIRECTOR):
        frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
    frappe.db.commit()
    print("perf data removed")


if __name__ == "__main__":
    {"seed": seed, "extra": extra, "measure": measure, "reset": reset}[sys.argv[1] if len(sys.argv) > 1 else "measure"]()
