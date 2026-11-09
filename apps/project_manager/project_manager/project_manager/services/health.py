"""Live status of the services the application depends on (never raises, never leaks credentials)."""

import frappe

CACHE_KEY = "pm_service_health"
CACHE_OK_SECONDS = 20
CACHE_DOWN_SECONDS = 60  # a probe of a service that is down waits for its timeout: do not repeat it on every refresh


def check_services(fresh: bool = False) -> dict:
    """Every probe; the answer is kept for a few seconds so that a monitor screen refreshing itself does not hammer them."""
    if not fresh:
        cached = frappe.cache.get_value(CACHE_KEY)
        if cached:
            return cached
    result = {"meilisearch": _check_meilisearch(), "minio": _check_minio(), "overdue_job": _check_overdue_job()}
    frappe.cache.set_value(CACHE_KEY, result, expires_in_sec=CACHE_OK_SECONDS if all(s["ok"] for s in result.values()) else CACHE_DOWN_SECONDS)
    return result


def _check_meilisearch() -> dict:
    try:
        import meilisearch

        client = meilisearch.Client(frappe.conf.get("meilisearch_host") or "http://meilisearch:7700",
                                    frappe.conf.get("meilisearch_master_key") or None, timeout=3)
        client.health()
        return {"ok": True, "message": "Kết nối thành công"}
    except Exception as e:
        return {"ok": False, "message": _short(e)}


def _check_minio() -> dict:
    """The object store of photos and documents (services/object_storage.py)."""
    from project_manager.project_manager.services import object_storage

    if not object_storage.configured():
        return {"ok": False, "message": "Chưa cấu hình MinIO (chạy lại scripts/bootstrap)"}
    try:
        object_storage.ping()
        return {"ok": True, "message": "Kết nối thành công"}
    except Exception as e:
        return {"ok": False, "message": _short(e)}


def _check_overdue_job() -> dict:
    """ERPNext's daily job that rewrites Task.status to "Overdue" must stay stopped (setup/install.py stops it)."""
    from project_manager.project_manager.setup.install import ERPNEXT_OVERDUE_JOB

    stopped = frappe.db.get_value("Scheduled Job Type", {"method": ERPNEXT_OVERDUE_JOB}, "stopped")
    if stopped is None or frappe.utils.cint(stopped):
        return {"ok": True, "message": "Đã dừng"}
    return {"ok": False, "message": "Job đổi trạng thái công việc sang Overdue của ERPNext đang chạy lại: chạy migrate để dừng"}


def _short(error: Exception) -> str:
    """One-line error text; anything after a connection-string scheme is dropped (credentials)."""
    text = " ".join(str(error).split())
    for scheme in ("http://", "https://"):
        text = text.split(scheme)[0]
    return (text.strip() or type(error).__name__)[:160]
