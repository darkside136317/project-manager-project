"""Fail before a production deploy if docker/.env.prod is incomplete or unsafe.

    python3 scripts/validate_prod_env.py [docker/.env.prod]

Copied from document_manager (scripts/validate_prod_env.py, see docs/NGUON_GOC.md) and adapted: MinIO always runs
inside the stack here; the site, company and image of this project. PM_REHEARSAL=1 (an environment variable, for a
rehearsal on a test machine) accepts a *.test site served over plain http.
"""

from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path

DOMAIN = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*$")
PORT = re.compile(r"^127\.0\.0\.1:([1-9][0-9]{0,4})$")
SECRETS = ("ADMIN_PASSWORD", "MARIADB_ROOT_PASSWORD", "MEILISEARCH_MASTER_KEY", "MINIO_ROOT_PASSWORD",
           "MINIO_APP_SECRET_KEY")
REQUIRED = ("ERPNEXT_VERSION", "COMPANY_NAME", "COMPANY_ABBR", "COUNTRY", "CURRENCY", "TIMEZONE", "LANGUAGE", "FY_START",
            "MINIO_ROOT_USER", "MINIO_APP_ACCESS_KEY", "MINIO_BUCKET")
DEVELOPMENT_NAMES = ("pm", "pmdev", "pmclone", "docker")
BUCKET = re.compile(r"^(?=.{3,63}$)[a-z0-9][a-z0-9.-]*[a-z0-9]$")
TEST_DOMAINS = (".example.com", ".example.net", ".example.org", ".local", ".localhost", ".test", ".invalid")


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Line {number} has no '='")
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError(f"Duplicate variable: {key}")
        values[key] = value
    return values


def validate(path: Path, rehearsal: bool | None = None) -> list[str]:
    rehearsal = os.environ.get("PM_REHEARSAL") == "1" if rehearsal is None else rehearsal
    issues = []
    if not path.is_file():
        return [f"Missing {path}; copy docker/.env.prod.example first"]
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        issues.append("The environment file must be readable by its owner only (chmod 600)")
    try:
        values = read_env(path)
    except ValueError as exc:
        return issues + [str(exc)]

    domain = values.get("FRAPPE_SITE_NAME", "").lower()
    is_test = domain.endswith(".test")
    if not DOMAIN.fullmatch(domain) or domain in ("example.com", "example.net", "example.org") or (
            domain.endswith(TEST_DOMAINS) and not (rehearsal and is_test)):
        issues.append("FRAPPE_SITE_NAME must be the real DNS name of the site")
    scheme = "http" if rehearsal and is_test else "https"
    if values.get("PUBLIC_URL") != f"{scheme}://{domain}":
        issues.append(f"PUBLIC_URL must be {scheme}:// followed by FRAPPE_SITE_NAME")

    prefix, project = values.get("DATA_VOLUME_PREFIX", ""), values.get("COMPOSE_PROJECT_NAME", "")
    if not IDENTIFIER.fullmatch(prefix) or prefix in DEVELOPMENT_NAMES:
        issues.append("DATA_VOLUME_PREFIX must name this deployment (not the developers' pm/pmdev)")
    if not IDENTIFIER.fullmatch(project) or project in DEVELOPMENT_NAMES:
        issues.append("COMPOSE_PROJECT_NAME must name this deployment (not the developers' pm/pmdev)")

    data_root = values.get("DATA_ROOT", "")
    if data_root:
        root_path = Path(data_root)
        source = path.resolve().parents[1]
        if not root_path.is_absolute() or root_path == Path(root_path.anchor) or ".." in root_path.parts:
            issues.append("DATA_ROOT must be an absolute folder of the host, outside the source tree")
        elif source in (root_path.resolve(), *root_path.resolve().parents):
            issues.append("DATA_ROOT must be outside the source tree")

    match = PORT.fullmatch(values.get("HTTP_PUBLISH_PORT", ""))
    if not match or int(match.group(1)) > 65535:
        issues.append("HTTP_PUBLISH_PORT must be 127.0.0.1:<port> (the reverse proxy is the only way in)")

    for key in REQUIRED:
        if not values.get(key, "").strip():
            issues.append(f"{key} is empty")
    if values.get("MINIO_BUCKET") and not BUCKET.fullmatch(values["MINIO_BUCKET"]):
        issues.append("MINIO_BUCKET is not a valid bucket name")
    if values.get("PM_IMAGE_TAG") and not values.get("PM_IMAGE"):
        issues.append("PM_IMAGE_TAG is set without PM_IMAGE")

    secrets = [values.get(key, "") for key in SECRETS]
    weak = [key for key, value in zip(SECRETS, secrets) if len(value) < 24 or "REPLACE" in value or "change_me" in value]
    if weak:
        issues.append(f"Weak or empty secrets: {', '.join(weak)} (scripts/deploy_prod.sh generates them)")
    if len(set(secrets)) != len(secrets):
        issues.append("All secrets must be different")

    dev_path = path.with_name(".env")
    if dev_path.exists():
        try:
            dev = read_env(dev_path)
        except ValueError:
            dev = {}
        if dev.get("DATA_VOLUME_PREFIX") == prefix:
            issues.append("Production and development must use different DATA_VOLUME_PREFIX")
        if any(dev.get(key) and dev.get(key) == values.get(key) for key in SECRETS):
            issues.append("Production must not reuse development secrets")
    return issues


if __name__ == "__main__":
    env_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docker/.env.prod")
    problems = validate(env_path)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        sys.exit(1)
    print(f"Production environment is ready: {env_path}")
