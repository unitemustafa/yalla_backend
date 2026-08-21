from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_liveness_does_not_depend_on_database(self):
        with patch("config.health.connection.cursor", side_effect=RuntimeError):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_checks_database(self):
        response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"], {"database": True})

    def test_readiness_returns_503_when_database_is_unavailable(self):
        with patch("config.health.connection.cursor", side_effect=RuntimeError):
            response = self.client.get(reverse("readyz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(response.json()["checks"], {"database": False})
