"""Private object storage (MinIO, S3 API) for photos and documents.

Only the backend talks to MinIO: files reach the browser through the app's own download endpoints, which check the
user's permission every time. An object key is `minio:<site>/<collection>/<32 hex>`: a key of another site or another
collection is refused, so a stored value can never be used to read something else.

Configuration (common_site_config.json, written by the `configurator` service):
pm_minio_endpoint, pm_minio_bucket, pm_minio_access_key, pm_minio_secret_key.

Adapted from document_manager's services/object_storage.py (docs/NGUON_GOC.md).
"""

import hashlib
import re
import uuid
from urllib.parse import quote

import frappe

PREFIX = "minio:"
COLLECTIONS = frozenset({"media", "thumbs", "documents"})
CHUNK = 256 * 1024
_clients = {}


class StorageError(Exception):
    """The object store cannot be reached or refused the request."""


def configured() -> bool:
    return bool(frappe.conf.get("pm_minio_endpoint"))


def _settings() -> tuple[str, str, str, str]:
    conf = frappe.conf
    endpoint, bucket = conf.get("pm_minio_endpoint"), conf.get("pm_minio_bucket") or "pm-files"
    access, secret = conf.get("pm_minio_access_key"), conf.get("pm_minio_secret_key")
    if not (endpoint and access and secret):
        raise StorageError("MinIO chưa được cấu hình (pm_minio_* trong common_site_config.json)")
    return endpoint, bucket, access, secret


def _site_prefix() -> str:
    return hashlib.sha256(frappe.local.site.encode()).hexdigest()[:16]


def _check_key(key: str, collection: str) -> str:
    if collection not in COLLECTIONS:
        raise ValueError(f"Unknown object collection {collection}")
    if not key or not key.startswith(PREFIX):
        raise ValueError("Not an object key")
    path = key[len(PREFIX):]
    if not re.fullmatch(rf"{_site_prefix()}/{collection}/[0-9a-f]{{32}}", path):
        raise ValueError("The object key does not belong to this site and collection")
    return path


class S3Backend:
    """The real store."""

    def __init__(self):
        import boto3
        from botocore.config import Config

        endpoint, self.bucket, access, secret = _settings()
        cache_key = (endpoint, access, secret)
        if cache_key not in _clients:
            _clients[cache_key] = boto3.client(
                "s3", endpoint_url=endpoint, aws_access_key_id=access, aws_secret_access_key=secret,
                region_name="us-east-1",
                config=Config(s3={"addressing_style": "path"}, connect_timeout=3, read_timeout=30,
                              retries={"max_attempts": 2, "mode": "standard"}))
        self.client = _clients[cache_key]

    def put(self, path, data, content_type, metadata):
        self.client.put_object(Bucket=self.bucket, Key=path, Body=data, ContentType=content_type, Metadata=metadata)

    def get(self, path) -> bytes:
        body = self.client.get_object(Bucket=self.bucket, Key=path)["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def open(self, path):
        """(chunks, content_type, length) for streaming a large object to the browser."""
        response = self.client.get_object(Bucket=self.bucket, Key=path)
        body = response["Body"]

        def chunks():
            try:
                yield from body.iter_chunks(CHUNK)
            finally:
                body.close()

        return chunks(), response.get("ContentType"), response.get("ContentLength")

    def delete(self, path):
        self.client.delete_object(Bucket=self.bucket, Key=path)

    def keys(self, prefix):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                yield item["Key"], item["LastModified"]

    def ping(self):
        self.client.head_bucket(Bucket=self.bucket)


def backend():
    """The store in use. Tests replace this function with an in-memory store."""
    return S3Backend()


def _call(action, *args):
    try:
        return action(*args)
    except (ValueError, StorageError):
        raise
    except Exception as error:
        frappe.log_error("Kho tệp MinIO", frappe.get_traceback())
        raise StorageError(str(error)[:200]) from error


def put(data: bytes, filename: str, content_type: str, collection: str) -> str:
    """Store `data` and return its key."""
    if collection not in COLLECTIONS:
        raise ValueError(f"Unknown object collection {collection}")
    path = f"{_site_prefix()}/{collection}/{uuid.uuid4().hex}"
    metadata = {"filename": quote(filename or "", safe=""), "sha256": hashlib.sha256(data).hexdigest()}
    store = backend()
    _call(store.put, path, data, content_type or "application/octet-stream", metadata)
    return PREFIX + path


def get(key: str, collection: str) -> bytes:
    path = _check_key(key, collection)
    store = backend()
    return _call(store.get, path)


def open_stream(key: str, collection: str):
    path = _check_key(key, collection)
    store = backend()
    return _call(store.open, path)


def delete_many(keys, collection: str) -> list[str]:
    """Delete objects; returns the keys that could not be deleted (logged)."""
    failed = []
    keys = [key for key in keys or [] if key]
    if not keys:
        return failed
    store = backend()
    for key in keys:
        try:
            store.delete(_check_key(key, collection))
        except Exception:
            frappe.log_error("Kho tệp MinIO", f"Không xóa được {key}\n{frappe.get_traceback()}")
            failed.append(key)
    return failed


def enqueue_delete(keys, collection: str) -> None:
    """Delete the objects once the transaction that dropped their rows has committed."""
    keys = [key for key in keys or [] if key]
    if keys:
        frappe.enqueue("project_manager.project_manager.services.object_storage.delete_many", keys=keys,
                       collection=collection, queue="short", enqueue_after_commit=True)


def ping() -> None:
    _call(backend().ping)


def sweep_orphans(older_than_hours: int = 24) -> int:
    """Objects that no row points to (an upload whose transaction rolled back): delete them after a day.

    Runs daily. Keys are listed per collection and compared with the rows that hold keys."""
    from datetime import datetime, timedelta, timezone

    if not configured():
        return 0
    held = set()
    for doctype, fields in (("PM Media", ("object_key", "thumb_key")), ("PM Document Version", ("object_key",))):
        for field in fields:
            held.update(frappe.get_all(doctype, filters={field: ["is", "set"]}, pluck=field))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    store, removed = backend(), 0
    for collection in sorted(COLLECTIONS):
        for path, modified in store.keys(f"{_site_prefix()}/{collection}/"):
            if PREFIX + path not in held and modified < cutoff:
                store.delete(path)
                removed += 1
    return removed
