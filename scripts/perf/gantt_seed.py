"""A scratch project for measuring the Gantt, and the timings of the schedule on it.

Runs inside the backend container, from the sites folder, script on stdin:

    docker compose exec -T -e PERF_SITE=pm.localhost -e PERF_TASKS=2000 -w /home/frappe/frappe-bench/sites backend \\
        /home/frappe/frappe-bench/env/bin/python - seed  < ../scripts/perf/gantt_seed.py     (prints the project's name)
    ... - reset < ../scripts/perf/gantt_seed.py                                              (removes it)

The project is built in phases of groups of tasks, each task following the one before it (a long critical path) and every
fifth task also tied to one in the next group, so the network has real work in it. Its code is PERF-GANTT; run
scripts/e2e/ui/gantt_perf.mjs against it.
"""

import os
import sys
import time

import frappe
from frappe.utils import add_days, getdate, nowdate

SITE = os.environ.get("PERF_SITE", "pm.localhost")
SIZE = int(os.environ.get("PERF_TASKS", "2000"))
CODE = "PERF-GANTT"


def timed(label, fn, *args):
    started = time.perf_counter()
    result = fn(*args)
    print(f"{label}: {(time.perf_counter() - started) * 1000:.0f} ms")
    return result


def reset():
    for project in frappe.get_all("Project", filters={"pm_code": CODE}, pluck="name"):
        for doctype in ("PM Activity", "PM Task Assignment", "PM Progress Entry", "PM Snapshot", "PM Project Member", "PM Task Dependency",
                        "PM Baseline Task", "PM Baseline Curve", "PM Baseline"):
            frappe.db.delete(doctype, {"project": project})
        frappe.db.delete("Task", {"project": project})
        frappe.delete_doc("Project", project, force=True, ignore_permissions=True)
        frappe.cache.delete_value(f"pm_rollup:{project}")
        frappe.cache.srem("pm_cpm_dirty", project)
    frappe.db.commit()


def seed():
    from project_manager.project_manager.services import baseline, schedule, tree
    from project_manager.project_manager.services.queries import reserve_ids

    reset()
    today = getdate(nowdate())
    project = frappe.get_doc({"doctype": "Project", "project_name": f"Đo Gantt {SIZE} việc", "pm_code": CODE, "pm_state": "Đang thực hiện",
                              "company": frappe.defaults.get_global_default("company"), "expected_start_date": add_days(today, -30),
                              "percent_complete_method": "Manual"})
    project.insert(ignore_permissions=True)
    per_group, per_phase = 25, 8
    nodes, order = [], []
    day = -30
    phase = group = 0
    while len(order) < SIZE:
        phase += 1
        nodes.append({"key": f"{phase}", "parent_key": None, "subject": f"Giai đoạn {phase}", "is_group": 1})
        for g in range(1, per_phase + 1):
            group += 1
            key = f"{phase}.{g}"
            nodes.append({"key": key, "parent_key": f"{phase}", "subject": f"Nhóm {key}", "is_group": 1})
            for t in range(1, per_group + 1):
                if len(order) >= SIZE:
                    break
                length = 1 + t % 4
                leaf = f"{key}.{t}"
                nodes.append({"key": leaf, "parent_key": key, "subject": f"Công việc {leaf}", "is_group": 0,
                              "exp_start_date": add_days(today, day), "exp_end_date": add_days(today, day + length - 1)})
                order.append(leaf)
                day += length if t % 3 else 0  # every third one overlaps the next
    names = dict(zip((n["key"] for n in nodes), timed("chèn hàng loạt", tree.bulk_insert, project.name, nodes)))
    pairs = [(names[a], names[b]) for a, b in zip(order, order[1:])]
    pairs += [(names[order[i]], names[order[i + per_group]]) for i in range(0, len(order) - per_group, 5)]
    now, user = frappe.utils.now_datetime(), frappe.session.user
    rows = [(number, project.name, a, b, "FS", 0, user, user, now, now, 0, 0)
            for number, (a, b) in zip(reserve_ids("PM Task Dependency", len(pairs)), sorted(set(pairs)))]
    frappe.db.bulk_insert("PM Task Dependency", ("name", "project", "predecessor", "successor", "dep_type", "lag_days", "owner", "modified_by",
                                                 "creation", "modified", "docstatus", "idx"), rows, chunk_size=500)
    frappe.db.commit()
    print(f"{len(order)} tasks, {len(rows)} links")
    timed("tính đường găng và dự báo (lần đầu, ghi mọi việc)", schedule.refresh, project.name)
    frappe.db.commit()
    timed("tính lại (không có gì đổi)", schedule.refresh, project.name)
    timed("chụp baseline", baseline.capture, project.name, "Đo")
    frappe.db.commit()
    timed("dữ liệu Gantt", schedule.gantt, project.name)
    middle = names[order[len(order) // 2]]
    result = timed("xem trước dời một việc giữa dự án", schedule.preview, middle, str(add_days(today, 60)))
    print(f"việc bị đẩy theo: {result['total']}")
    timed("áp dụng", schedule.apply, middle, str(add_days(today, 60)))
    frappe.db.rollback()
    print(f"PROJECT={project.name}")


frappe.init(SITE)
frappe.connect()
frappe.set_user("Administrator")
(seed if (sys.argv[1:] or ["seed"])[0] == "seed" else reset)()
