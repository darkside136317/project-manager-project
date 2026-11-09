"""Sending a stored object (photo, document) to the browser, after the caller has checked the permission.

The object is streamed from MinIO in chunks (a 100 MB drawing never sits in the worker's memory). Only types a
browser shows safely are sent inline; everything else is a download, and `nosniff` stops the browser from guessing.
"""

from urllib.parse import quote

from werkzeug.wrappers import Response

from project_manager.project_manager.services import object_storage

INLINE_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif"})


def disposition(filename: str, inline: bool) -> str:
    safe = (filename or "tep").replace('"', "").replace("\r", "").replace("\n", "")
    ascii_name = safe.encode("ascii", "ignore").decode() or "tep"
    return f"{'inline' if inline else 'attachment'}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(safe)}"


def stream(key: str, collection: str, content_type: str | None, filename: str, inline: bool = False,
           immutable: bool = False) -> Response:
    chunks, stored_type, length = object_storage.open_stream(key, collection)
    content_type = content_type or stored_type or "application/octet-stream"
    headers = {
        "Content-Disposition": disposition(filename, inline and content_type in INLINE_TYPES),
        "X-Content-Type-Options": "nosniff",
        # an object never changes under its key, so a photo can be kept by the browser for good
        "Cache-Control": "private, max-age=31536000, immutable" if immutable else "private, no-cache",
    }
    if length:
        headers["Content-Length"] = str(length)
    return Response(chunks, status=200, content_type=content_type, headers=headers, direct_passthrough=True)
