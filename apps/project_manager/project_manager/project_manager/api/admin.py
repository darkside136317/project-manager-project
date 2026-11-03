"""System administration API (PM Admin / System Manager only): service health and the monitor of the whole system."""

import os
import shutil

import frappe
from frappe.utils import add_days, now_datetime

from project_manager.project_manager.policy import assert_capability
from project_manager.project_manager.services.errors import log_exception



@frappe.whitelist()
def get_service_health():
    """Status of the services the application depends on (search, scheduled jobs)."""
    assert_capability("monitor.view")
    from project_manager.project_manager.services.health import check_services

    return check_services(fresh=True)


def _queues() -> list[dict]:
    """Jobs waiting in each queue (empty when the queues cannot be read)."""
    try:
        from frappe.utils.background_jobs import get_queues

        return [{"name": q.name.split(":")[-1], "jobs": q.count} for q in get_queues()]
    except Exception:
        log_exception("Monitor", "Could not read the job queues")
        return []


def _workers() -> int | None:
    try:
        from frappe.utils.background_jobs import get_workers

        return len(get_workers())
    except Exception:
        return None


FILES_SIZE_KEY = "pm_private_files_bytes"


def measure_private_files() -> int:
    """Total size of the uploaded files. Walking a folder of a million files takes a while: this runs as a background job."""
    total = 0
    private = frappe.get_site_path("private", "files")
    if os.path.isdir(private):
        for entry in os.scandir(private):
            try:
                total += entry.stat().st_size if entry.is_file() else 0
            except OSError:
                pass
    frappe.cache.set_value(FILES_SIZE_KEY, total, expires_in_sec=6 * 3600)
    return total


def private_files_bytes() -> int | None:
    """The last measured size of the uploaded files; None while the first measurement is still running."""
    size = frappe.cache.get_value(FILES_SIZE_KEY)
    if size is None:
        frappe.enqueue("project_manager.project_manager.api.admin.measure_private_files", queue="short", timeout=600,
                       job_id="pm_measure_private_files", deduplicate=True, enqueue_after_commit=False)
    return size


@frappe.whitelist()
def monitor():
    """Everything the monitoring screen shows in one call: services, jobs, storage, users, log, data volume."""
    assert_capability("monitor.view")
    from project_manager.project_manager.services.health import check_services

    day_ago = add_days(now_datetime(), -1)
    week_ago = add_days(now_datetime(), -7)
    try:
        usage = shutil.disk_usage(frappe.get_site_path())
        disk = {"free_gb": round(usage.free / 1024 ** 3, 1), "total_gb": round(usage.total / 1024 ** 3, 1),
                "used_percent": round((usage.total - usage.free) * 100 / usage.total)}
    except OSError:
        disk = None
    files_size = private_files_bytes()
    return {
        "services": check_services(),
        "data": {"projects": frappe.db.count("Project"), "tasks": frappe.db.count("Task"),
                 "activity": frappe.db.count("PM Activity")},
        "jobs": {"queues": _queues(), "workers": _workers(),
                 "errors_24h": frappe.db.count("Error Log", {"creation": [">", day_ago]}),
                 "failed_7d": frappe.db.count("Scheduled Job Log", {"status": "Failed", "creation": [">", week_ago]})},
        "storage": {"disk": disk, "private_files_mb": None if files_size is None else round(files_size / (1024 * 1024), 1)},
        "users": {"staff": frappe.db.count("User", {"user_type": "System User", "enabled": 1,
                                                    "name": ["not in", ["Administrator", "Guest"]]})},
        "log": {"rows": frappe.db.count("PM Audit Log"),
                "last_24h": frappe.db.count("PM Audit Log", {"timestamp": [">", day_ago]})},
        "site": frappe.local.site, "checked_at": str(now_datetime()),
    }
