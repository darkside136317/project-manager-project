"""Host page of the single-page application (/pm and every /pm/... route).

The SPA is built by Vite into `public/spa` (see frontend/). This page only
  * keeps guests out (to the login page, back here afterwards) and website users out,
  * hands the SPA its boot data (user, company, CSRF token) as inline JSON,
  * links the hashed JS/CSS files listed in Vite's manifest.
"""

import json
import os

import frappe

from project_manager import __version__
from project_manager.project_manager.services.web import current_route, inline_json, login_redirect, redirect

SPA_BUILD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "spa")
ASSET_BASE = "/assets/project_manager/spa/"


def entry_assets() -> tuple[list[str], list[str]]:
    """(js, css) URLs of the SPA entry from Vite's manifest; ([], []) when it has not been built."""
    try:
        with open(os.path.join(SPA_BUILD, ".vite", "manifest.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
        return [], []
    entry = next((chunk for chunk in manifest.values() if chunk.get("isEntry")), None)
    if not entry:
        return [], []
    return [ASSET_BASE + entry["file"]], [ASSET_BASE + css for css in entry.get("css", [])]


def build_boot() -> dict:
    user = frappe.session.user
    return {
        "user": user,
        "full_name": frappe.utils.get_fullname(user),
        "company": frappe.defaults.get_user_default("company") or frappe.defaults.get_global_default("company"),
        "lang": frappe.local.lang,
        "version": __version__,
        "csrf_token": frappe.sessions.get_csrf_token(),
    }


def get_context(context):
    context.no_cache = 1
    if frappe.session.user == "Guest":
        login_redirect(current_route())
    if frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
        redirect("/me")

    boot = build_boot()
    context.boot_json = inline_json(boot)
    context.pm_js, context.pm_css = entry_assets()
    context.title = f"{boot['company'] or 'Quản lý dự án'} — Quản lý dự án"
    return context
