"""Smoke test of a running stack over HTTP (standard library only).

    python scripts/e2e/smoke_http.py [base_url]

The base URL defaults to http://localhost:<HTTP_PUBLISH_PORT from docker/.env>. The Administrator
password is read from docker/.env (ADMIN_PASSWORD). The exit code is the number of failed checks.
"""

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / "docker" / ".env"


def env_values() -> dict:
    values = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value
    return values


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main() -> int:
    env = env_values()
    base = (sys.argv[1] if len(sys.argv) > 1 else f"http://localhost:{env.get('HTTP_PUBLISH_PORT') or 8890}").rstrip("/")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    failures = 0

    def request(path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            with opener.open(urllib.request.Request(base + path, data=body), timeout=60) as response:
                return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read().decode("utf-8", "replace")

    def check(name, ok, detail=""):
        nonlocal failures
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" — {detail}"))
        failures += 0 if ok else 1

    status, _, body = request("/api/method/ping")
    check("ping", status == 200 and json.loads(body).get("message") == "pong", f"{status} {body[:200]}")

    status, headers, _ = request("/pm/du-an")
    location = headers.get("Location", "")
    check("guest /pm goes to login", status == 302 and "/login?redirect-to=" in location, f"{status} {location}")

    status, _, body = request("/api/method/login", {"usr": "Administrator", "pwd": env.get("ADMIN_PASSWORD", "")})
    check("login as Administrator", status == 200, f"{status} {body[:200]}")

    status, _, body = request("/api/method/frappe.auth.get_logged_user")
    check("session user", status == 200 and json.loads(body).get("message") == "Administrator", f"{status} {body[:200]}")

    status, _, page = request("/pm")
    check("/pm renders the SPA host", status == 200 and "window.__PM_BOOT__" in page, f"{status} {page[:200]}")
    scripts = re.findall(r'src="(/assets/project_manager/spa/[^"]+\.js)"', page)
    check("/pm links the built bundle", bool(scripts), "no /assets/project_manager/spa/*.js in the page")
    for src in scripts:
        status, _, _ = request(src)
        check(f"bundle served: {src}", status == 200, str(status))

    status, _, _ = request("/pm/du-an/abc")
    check("deep SPA route renders", status == 200, str(status))

    status, _, _ = request("/desk")  # Frappe v16 Desk; /app only redirects here
    check("/desk (ERPNext Desk)", status == 200, str(status))

    print(f"{failures} failure(s)")
    return failures


if __name__ == "__main__":
    sys.exit(main())
