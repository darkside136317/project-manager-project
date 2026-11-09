"""The service worker of the installable app (PWA), served at /pm/sw.js so that it may control every /pm page.

Vite copies frontend/public/sw.js into the build untouched; here its build marker is replaced by the name of the
current entry bundle, so a new build changes the worker's bytes: the browser installs it and the worker drops the
caches of the previous build. `Service-Worker-Allowed` lets it control /pm itself, not only /pm/...
"""

import os

from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

SW_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "spa", "sw.js")
ROUTE = "pm-sw"  # hooks.website_route_rules maps /pm/sw.js here


def worker_source() -> str:
    from project_manager.www.pm import entry_assets

    try:
        with open(SW_FILE, encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return "// the app has not been built yet\n"
    scripts, _styles = entry_assets()
    build = os.path.basename(scripts[0]).replace(".js", "") if scripts else "dev"
    return source.replace("__PM_BUILD__", build)


class ServiceWorkerPage(BaseRenderer):
    def can_render(self):
        return self.path == ROUTE

    def render(self):
        return Response(worker_source(), status=200, content_type="application/javascript; charset=utf-8", headers={
            "Cache-Control": "no-cache", "Service-Worker-Allowed": "/pm", "X-Content-Type-Options": "nosniff"})
