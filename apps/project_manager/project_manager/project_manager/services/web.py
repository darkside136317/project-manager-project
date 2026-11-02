"""Small helpers shared by the server-rendered pages (the SPA host)."""

import json
from urllib.parse import quote

import frappe

# Escapes, not the characters themselves: "<" in a normal string literal is just "<".
_SCRIPT_ESCAPES = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", " ": "\\u2028", " ": "\\u2029"}


def inline_json(data) -> str:
    """JSON that is safe inside a <script> element (no way to close the tag or open a comment)."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    for char, escape in _SCRIPT_ESCAPES.items():
        text = text.replace(char, escape)
    return text


def current_route() -> str:
    """Path and query string of the page being rendered, to come back to after signing in."""
    request = getattr(frappe.local, "request", None)
    if not request:
        return "/"
    query = request.query_string.decode("utf-8", "ignore") if request.query_string else ""
    return request.path + (f"?{query}" if query else "")


def redirect(location: str):
    frappe.local.flags.redirect_location = location
    raise frappe.Redirect(302)  # depends on the session: never a cacheable 301


def login_redirect(route: str):
    """Send a guest to the sign-in page, which returns them to `route` afterwards."""
    redirect(f"/login?redirect-to={quote(route, safe='/')}")
