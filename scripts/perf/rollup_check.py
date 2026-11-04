"""Roll-up check (M2): one progress report on a 2 000-task project must show in the project's % within 5 s.

Runs inside the backend container, from the sites folder, script on stdin; it builds its own scratch project
(code PERF-ROLLUP), measures, and deletes it again, so it may run on a development site:

    docker compose exec -T -e PERF_SITE=pm.localhost -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - < ../scripts/perf/rollup_check.py

The end-to-end figure goes through the real path: save → after commit → Redis set + job on the "pm" queue → worker
→ Project.percent_complete. The queue-pm worker must be running.
"""

import os
import statistics
import time

import frappe
from frappe.utils import add_days, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
CODE = "PERF-ROLLUP"
PHASES, GROUPS, LEAVES = 5, 8, 50  # 5 × 8 × 50 = 2 000 leaves (+ 45 groups)


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return (time.perf_counter() - start) * 1000, result


def build():
    from project_manager.project_manager.services import tree

    project = frappe.get_doc({"doctype": "Project", "project_name": "Perf roll-up 2000", "pm_code": CODE,
                              "company": frappe.defaults.get_global_default("company"), "pm_state": "Đang thực hiện",
                              "expected_start_date": add_days(nowdate(), -30), "expected_end_date": add_days(nowdate(), 300),
                              "percent_complete_method": "Manual"})
    project.insert(ignore_permissions=True)
    nodes = []
    day = 0
    for p in range(1, PHASES + 1):
        nodes.append({"key": f"{p}", "parent_key": None, "subject": f"Giai đoạn {p}", "is_group": 1})
        for g in range(1, GROUPS + 1):
            nodes.append({"key": f"{p}.{g}", "parent_key": f"{p}", "subject": f"Nhóm {p}.{g}", "is_group": 1})
            for t in range(1, LEAVES + 1):
                day += 1
                nodes.append({"key": f"{p}.{g}.{t}", "parent_key": f"{p}.{g}", "subject": f"Việc {p}.{g}.{t}",
                              "is_group": 0, "exp_start_date": add_days(nowdate(), day % 280 - 30),
                              "exp_end_date": add_days(nowdate(), day % 280 - 30 + 1 + day % 9)})
    ms, names = timed(tree.bulk_insert, project.name, nodes)
    frappe.db.commit()
    return project.name, len(names), ms


def leaves(project, count):
    """Leaves not due yet (late work would need a delay reason, which is not what is measured here)."""
    return frappe.get_all("Task", filters={"project": project, "is_group": 0, "exp_end_date": [">=", nowdate()]},
                          pluck="name", order_by="pm_path", limit_page_length=count)


def end_to_end(project, task, progress):
    """Report through the service, commit, and wait for the worker to move the project's %."""
    from project_manager.project_manager.services import progress as service

    before = frappe.db.get_value("Project", project, "percent_complete")
    start = time.perf_counter()
    service.report(task, progress, "perf")
    frappe.db.commit()
    while time.perf_counter() - start < 30:
        frappe.db.rollback()  # a fresh snapshot (REPEATABLE READ would keep showing the old value)
        if frappe.db.get_value("Project", project, "percent_complete") != before:
            return (time.perf_counter() - start) * 1000
        time.sleep(0.05)
    return None


def main():
    frappe.init(SITE)
    frappe.connect()
    frappe.set_user("Administrator")
    from project_manager.project_manager.services import projects, rollup, tree, work

    if frappe.db.exists("Project", {"pm_code": CODE}):
        cleanup()
    project, count, insert_ms = build()
    print(f"site {SITE}: project {project}, {count} tasks inserted in {insert_ms:.0f} ms")
    try:
        ms, fixed = timed(rollup.reconcile, project)
        frappe.db.commit()
        print(f"reconcile (whole project, from the leaves up): {ms:.0f} ms, {fixed} values written")
        ms, fixed = timed(rollup.reconcile, project)
        print(f"reconcile again (nothing to fix): {ms:.0f} ms, {fixed} values written")

        sample = leaves(project, 2000)[::150]
        waits = [end_to_end(project, task, 50) for task in sample[:5]]
        good = [w for w in waits if w is not None]
        print(f"report → project % (worker on queue pm), {len(good)}/{len(waits)} seen: "
              f"median {statistics.median(good):.0f} ms, max {max(good):.0f} ms" if good else "worker did not answer")

        # the job itself, without the queue: one dirty parent and twenty at once
        task = sample[-1]
        frappe.db.set_value("Task", task, "progress", 80)
        parent = frappe.db.get_value("Task", task, "parent_task")
        ms, written = timed(rollup.recompute, project, {parent})
        print(f"recompute one branch (3 levels + project): {ms:.1f} ms, {written} rows written")
        parents = {frappe.db.get_value("Task", t, "parent_task") for t in leaves(project, 2000)[::100]}
        for t in leaves(project, 2000)[::100]:
            frappe.db.set_value("Task", t, "progress", 30)
        ms, written = timed(rollup.recompute, project, parents)
        print(f"recompute {len(parents)} branches at once: {ms:.1f} ms, {written} rows written")
        frappe.db.commit()

        for label, fn, args in (
                ("WBS: one level (roots)", tree.children, (project,)),
                ("Kanban (500 cards)", work.kanban, (project,)),
                ("Who does what", work.who_does_what, (project,)),
                ("Project overview", projects.overview, (project,)),
                ("Project list", projects.list_projects, ()),
        ):
            runs = [timed(fn, *args)[0] for _ in range(3)]
            print(f"{label}: best {min(runs):.0f} ms")
    finally:
        cleanup()


def cleanup():
    for project in frappe.get_all("Project", filters={"pm_code": CODE}, pluck="name"):
        for doctype in ("PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
        frappe.cache.delete_value(f"pm_rollup:{project}")
    frappe.db.commit()
    print("scratch project removed")


main()
