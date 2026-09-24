from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_liveness_does_not_depend_on_database(self):
        with patch("config.health.connection.cursor", side_effect=RuntimeError):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_checks_database_and_redis(self):
        with patch("config.health.check_redis_health", return_value=(True, 0.5, None)):
            response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["checks"],
            {"database": True, "redis": True},
        )

    def test_readiness_returns_503_when_database_is_unavailable(self):
        with (
            patch("config.health.connection.cursor", side_effect=RuntimeError),
            patch("config.health.check_redis_health", return_value=(True, 0.5, None)),
        ):
            response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(
            response.json()["checks"],
            {"database": False, "redis": True},
        )

    def test_readiness_returns_503_when_redis_is_unavailable(self):
        with patch(
            "config.health.check_redis_health",
            return_value=(False, 1.0, "Connection error"),
        ):
            response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(
            response.json()["checks"],
            {"database": True, "redis": False},
        )
