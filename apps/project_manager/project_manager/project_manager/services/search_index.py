"""Full-text search over comments and project documents (Meilisearch).

One index per site (`pm_<site hash>`). A comment or a document is (re)indexed in the background right after the
transaction that wrote it commits; a failure is logged and the nightly reconcile rebuilds the index when its count
no longer matches the database. Search results are filtered by project in Meilisearch, then by task visibility here
(a member who sees only their assigned tasks never gets another task's comment).

Adapted from document_manager's services/search_index.py (docs/NGUON_GOC.md).
"""

import calendar
import hashlib

import frappe
from frappe import _
from frappe.utils import cint

from project_manager.project_manager.policy import can_see_task, get_access, project_in

_clients = {}
_ready = {}
BATCH = 1000
MARK_START, MARK_END = "", ""  # highlight marks: the screen turns them into <mark> without HTML
SETTINGS = {
    "searchableAttributes": ["title", "text", "who", "project_name"],
    "filterableAttributes": ["project", "kind", "task"],
    "sortableAttributes": ["ts"],
    "displayedAttributes": ["id", "kind", "ref", "project", "project_name", "task", "task_label", "title", "text",
                            "who", "ts"],
}


class SearchUnavailable(Exception):
    pass


def index_uid() -> str:
    return frappe.flags.pm_search_index or f"pm_{hashlib.sha256(frappe.local.site.encode()).hexdigest()[:16]}"


def _client():
    import meilisearch

    host = frappe.conf.get("meilisearch_host") or "http://meilisearch:7700"
    key = frappe.conf.get("meilisearch_master_key") or None
    cache = (host, key)
    if cache not in _clients:
        _clients[cache] = meilisearch.Client(host, key, timeout=5)
    return _clients[cache]


def _wait(client, task, timeout=30000):
    result = client.wait_for_task(task.task_uid, timeout_in_ms=timeout, interval_in_ms=100)
    if result.status != "succeeded":
        raise SearchUnavailable(str(result.error))
    return result


def _index(uid: str | None = None):
    """The index, created and configured the first time it is used in this process."""
    client = _client()
    uid = uid or index_uid()
    if _ready.get(uid) is not client:
        try:
            client.get_index(uid)
        except Exception:
            _wait(client, client.create_index(uid, {"primaryKey": "id"}))
        _wait(client, client.index(uid).update_settings(SETTINGS))
        _ready[uid] = client
    return client.index(uid)


# --- what goes into the index -------------------------------------------------------------------------------------------

def _ts(value) -> int:
    return calendar.timegm(value.timetuple()) if value else 0


def _labels(rows) -> tuple[dict, dict, dict]:
    projects = {row.project for row in rows if row.project}
    tasks = {row.task for row in rows if row.get("task")}
    users = {row.get("actor") or row.get("owner") for row in rows}
    project_names = dict(frappe.get_all("Project", filters={"name": ["in", list(projects)]},
                                        fields=["name", "project_name"], as_list=True)) if projects else {}
    task_labels = {t.name: f"{t.pm_wbs_code or ''} {t.subject}".strip()
                   for t in frappe.get_all("Task", filters={"name": ["in", list(tasks)]},
                                           fields=["name", "subject", "pm_wbs_code"])} if tasks else {}
    user_names = dict(frappe.get_all("User", filters={"name": ["in", [u for u in users if u]]},
                                     fields=["name", "full_name"], as_list=True)) if users else {}
    return project_names, task_labels, user_names


def comment_documents(rows) -> list[dict]:
    from project_manager.project_manager.services.timeline import plain

    projects, tasks, users = _labels(rows)
    return [{
        "id": f"act-{row.name}", "kind": "comment", "ref": str(row.name), "project": row.project or "",
        "project_name": projects.get(row.project, ""), "task": row.task or "", "task_label": tasks.get(row.task, ""),
        "title": tasks.get(row.task) or projects.get(row.project, ""), "text": plain(row.content)[:20000],
        "who": users.get(row.actor) or row.actor or "", "ts": _ts(row.creation),
    } for row in rows]


def document_documents(rows) -> list[dict]:
    projects, tasks, users = _labels(rows)
    files = {}
    for version in frappe.get_all("PM Document Version", filters={"document": ["in", [r.name for r in rows]]},
                                  fields=["document", "file_name", "note"]):
        files.setdefault(version.document, []).append(" ".join(filter(None, (version.file_name, version.note))))
    return [{
        "id": f"doc-{row.name}", "kind": "document", "ref": row.name, "project": row.project or "",
        "project_name": projects.get(row.project, ""), "task": row.task or "", "task_label": tasks.get(row.task, ""),
        "title": row.title or "", "text": " ".join(filter(None, [row.category, row.description, *files.get(row.name, [])])),
        "who": users.get(row.owner) or row.owner or "", "ts": _ts(row.updated_on or row.creation),
    } for row in rows]


COMMENT_FIELDS = ["name", "project", "task", "actor", "content", "creation", "is_deleted", "activity_type"]
DOCUMENT_FIELDS = ["name", "project", "task", "title", "category", "description", "owner", "updated_on", "creation"]


# --- writing (background) -----------------------------------------------------------------------------------------------

def _enqueue(method: str, **kwargs) -> None:
    if not frappe.conf.get("meilisearch_host"):
        return
    frappe.enqueue(f"project_manager.project_manager.services.search_index.{method}", queue="pm",
                   enqueue_after_commit=True, **kwargs)


def enqueue_activity(name) -> None:
    _enqueue("index_activity", name=cint(name))


def enqueue_document(name) -> None:
    _enqueue("index_document", name=name)


def enqueue_remove(doc_id: str) -> None:
    _enqueue("remove", doc_id=doc_id)


def index_activity(name):
    row = frappe.db.get_value("PM Activity", cint(name), COMMENT_FIELDS, as_dict=True)
    if not row or row.is_deleted or row.activity_type != "Bình luận":
        return remove(f"act-{cint(name)}")
    return _index().add_documents(comment_documents([row]))


def index_document(name):
    row = frappe.db.get_value("PM Document", name, DOCUMENT_FIELDS, as_dict=True)
    if not row:
        return remove(f"doc-{name}")
    return _index().add_documents(document_documents([row]))


def remove(doc_id: str):
    return _index().delete_document(doc_id)


# --- searching ----------------------------------------------------------------------------------------------------------

def _quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def search(query: str, project: str | None = None, kind: str | None = None, limit: int = 20) -> dict:
    query = (query or "").strip()[:200]
    limit = max(1, min(cint(limit) or 20, 50))
    if len(query) < 2:
        return {"hits": [], "query": query}
    access = get_access()
    filters = []
    if project:
        if not project_in(access.read, project):
            raise frappe.PermissionError(_("Bạn không xem được dự án này"))
        filters.append(f"project = {_quote(project)}")
    elif access.read is not None:
        if not access.read:
            return {"hits": [], "query": query}
        filters.append(f"project IN [{', '.join(_quote(p) for p in sorted(access.read))}]")
    if kind in ("comment", "document"):
        filters.append(f"kind = {_quote(kind)}")
    try:
        options = {"limit": limit * 3 if access.assigned_only else limit, "attributesToCrop": ["text"],
                   "cropLength": 32, "attributesToHighlight": ["title", "text"], "highlightPreTag": MARK_START,
                   "highlightPostTag": MARK_END}
        if filters:
            options["filter"] = " AND ".join(filters)
        result = _index().search(query, options)
    except Exception as error:
        frappe.log_error("Tìm kiếm", frappe.get_traceback())
        raise SearchUnavailable(_("Tìm kiếm tạm thời không dùng được")) from error
    hits = []
    for hit in result.get("hits", []):
        if hit.get("task") and access.kind != "admin" and not can_see_task(hit["task"], hit.get("project"), access.user):
            continue
        shown = hit.get("_formatted") or hit
        hits.append({"id": hit["id"], "kind": hit["kind"], "ref": hit["ref"], "project": hit.get("project"),
                     "project_name": hit.get("project_name"), "task": hit.get("task") or None,
                     "task_label": hit.get("task_label") or None, "title": shown.get("title") or "",
                     "text": shown.get("text") or "", "who": hit.get("who") or "", "ts": hit.get("ts")})
        if len(hits) >= limit:
            break
    return {"hits": hits, "query": query}


# --- reconcile ----------------------------------------------------------------------------------------------------------

def _expected() -> int:
    comments = frappe.db.count("PM Activity", {"activity_type": "Bình luận", "is_deleted": 0})
    return comments + frappe.db.count("PM Document")


def reconcile() -> dict:
    """Nightly: rebuild the index when it does not hold as many entries as the database (a lost background job)."""
    if not frappe.conf.get("meilisearch_host"):
        return {"skipped": True}
    expected = _expected()
    try:
        stats = _index().get_stats()
        held = getattr(stats, "number_of_documents", None)
        if held is None:
            held = stats.get("numberOfDocuments") if isinstance(stats, dict) else 0
    except Exception:
        held = -1
    if held == expected:
        return {"expected": expected, "held": held, "rebuilt": False}
    return {"expected": expected, "held": held, "rebuilt": True, "indexed": rebuild()}


def rebuild() -> int:
    """Fill a fresh index from the database, then swap it in (searches keep working meanwhile)."""
    client, uid = _client(), index_uid()
    _index(uid)
    temporary = f"{uid}_new"
    try:
        client.delete_index(temporary)
    except Exception:
        pass
    target = _index(temporary)
    count, last = 0, 0
    while True:
        rows = frappe.get_all("PM Activity", filters={"activity_type": "Bình luận", "is_deleted": 0,
                                                      "name": [">", last]},
                              fields=COMMENT_FIELDS, order_by="name asc", limit_page_length=BATCH)
        if not rows:
            break
        _wait(client, target.add_documents(comment_documents(rows)), timeout=120000)
        count += len(rows)
        last = rows[-1].name
    start = 0
    while True:
        rows = frappe.get_all("PM Document", fields=DOCUMENT_FIELDS, order_by="name asc", start=start,
                              limit_page_length=BATCH)
        if not rows:
            break
        _wait(client, target.add_documents(document_documents(rows)), timeout=120000)
        count += len(rows)
        start += BATCH
    _wait(client, client.swap_indexes([{"indexes": [uid, temporary]}]))
    _wait(client, client.delete_index(temporary))
    _ready.pop(temporary, None)
    return count
