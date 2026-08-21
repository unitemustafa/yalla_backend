import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BASE_DIR = Path(__file__).resolve().parent.parent


def production_environment(**overrides):
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "production",
            "DEBUG": "False",
            "SECRET_KEY": "production-test-secret-key-with-more-than-fifty-characters-123",
            "DATABASE_URL": "postgresql://user:password@db.invalid:5432/yalla",
            "ALLOWED_HOSTS": "api.example.test",
            "CORS_ALLOWED_ORIGINS": "https://dashboard.example.test",
            "RATE_LIMIT_MODE": "enforce",
            "RATE_LIMIT_REDIS_URL": "rediss://redis.invalid:6379/1",
            "RATE_LIMIT_KEY_SECRET": "independent-rate-limit-secret-for-production-test",
            "RATE_LIMIT_TRUSTED_PROXY_CIDRS": "10.0.0.0/8",
            "AUTH_OTP_INCLUDE_IN_RESPONSE": "False",
        }
    )
    environment.update(overrides)
    environment.pop("DJANGO_SETTINGS_MODULE", None)
    return environment


class ProductionSecuritySettingsTests(SimpleTestCase):
    def _import_settings(self, **overrides):
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=BASE_DIR,
            env=production_environment(**overrides),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_production_settings_accept_secure_otp_configuration(self):
        result = self._import_settings()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_refuses_otp_in_api_responses(self):
        result = self._import_settings(AUTH_OTP_INCLUDE_IN_RESPONSE="True")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "AUTH_OTP_INCLUDE_IN_RESPONSE must be False",
            result.stderr,
        )

    def test_production_refuses_synchronous_push_delivery(self):
        result = self._import_settings(PUSH_DELIVERY_ASYNC="False")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "PUSH_DELIVERY_ASYNC must be True",
            result.stderr,
        )
