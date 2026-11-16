"""What scripts/validate_prod_env.py accepts and refuses (run by CI's static job).

    python -m unittest discover -s scripts/ci -p "test_*.py"
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_prod_env import validate  # noqa: E402

GOOD = {
    "COMPOSE_PROJECT_NAME": "pmprod", "DATA_VOLUME_PREFIX": "pmprod", "DATA_ROOT": "", "PM_IMAGE": "", "PM_IMAGE_TAG": "",
    "ERPNEXT_VERSION": "v16.26.2", "FRAPPE_SITE_NAME": "duan.congty.vn", "PUBLIC_URL": "https://duan.congty.vn",
    "HTTP_PUBLISH_PORT": "127.0.0.1:8890", "ADMIN_PASSWORD": "a" * 48, "MARIADB_ROOT_PASSWORD": "b" * 48,
    "MEILISEARCH_MASTER_KEY": "c" * 48, "MINIO_ROOT_PASSWORD": "d" * 48, "MINIO_APP_SECRET_KEY": "e" * 48,
    "COMPANY_NAME": "Công ty A", "COMPANY_ABBR": "CTA", "COUNTRY": "Vietnam", "CURRENCY": "VND",
    "TIMEZONE": "Asia/Ho_Chi_Minh", "LANGUAGE": "vi", "FY_START": "01-01", "MINIO_ROOT_USER": "pmadmin",
    "MINIO_APP_ACCESS_KEY": "pm-app", "MINIO_BUCKET": "pm-files",
}


class TestValidateProdEnv(unittest.TestCase):
    def check(self, rehearsal=False, dev=None, **changes):
        with tempfile.TemporaryDirectory() as folder:
            docker = Path(folder) / "repo" / "docker"
            docker.mkdir(parents=True)
            path = docker / ".env.prod"
            values = {**GOOD, **changes}
            path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
            if os.name == "posix":
                path.chmod(0o600)
            if dev:
                (docker / ".env").write_text("\n".join(f"{k}={v}" for k, v in dev.items()) + "\n", encoding="utf-8")
            return validate(path, rehearsal=rehearsal)

    def test_a_complete_file_passes(self):
        self.assertEqual(self.check(), [])

    def test_the_site_must_be_real_and_served_over_https(self):
        self.assertTrue(self.check(FRAPPE_SITE_NAME="pm.localhost", PUBLIC_URL="https://pm.localhost"))
        self.assertTrue(self.check(PUBLIC_URL="http://duan.congty.vn"))
        self.assertTrue(self.check(FRAPPE_SITE_NAME="duan.test", PUBLIC_URL="http://duan.test"))
        self.assertEqual(self.check(rehearsal=True, FRAPPE_SITE_NAME="duan.test", PUBLIC_URL="http://duan.test"), [])

    def test_only_the_proxy_reaches_nginx(self):
        self.assertTrue(self.check(HTTP_PUBLISH_PORT="8890"))
        self.assertTrue(self.check(HTTP_PUBLISH_PORT="0.0.0.0:8890"))

    def test_secrets_are_strong_and_different(self):
        self.assertTrue(self.check(ADMIN_PASSWORD=""))
        self.assertTrue(self.check(ADMIN_PASSWORD="short"))
        self.assertTrue(self.check(MINIO_APP_SECRET_KEY="a" * 48))

    def test_not_the_developers_stack(self):
        self.assertTrue(self.check(DATA_VOLUME_PREFIX="pm"))
        self.assertTrue(self.check(COMPOSE_PROJECT_NAME="pmdev"))
        dev = {"DATA_VOLUME_PREFIX": "other", "ADMIN_PASSWORD": "a" * 48}
        self.assertTrue(any("reuse" in issue for issue in self.check(dev=dev)))

    def test_company_and_image(self):
        self.assertTrue(self.check(COMPANY_NAME=""))
        self.assertTrue(self.check(PM_IMAGE_TAG="latest"))
        self.assertEqual(self.check(PM_IMAGE="ghcr.io/x/pm-custom", PM_IMAGE_TAG="latest"), [])

    def test_data_root_outside_the_source(self):
        self.assertTrue(self.check(DATA_ROOT="relative/path"))
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(self.check(DATA_ROOT=outside), [])


if __name__ == "__main__":
    unittest.main()
