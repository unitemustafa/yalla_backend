"""Keep self-service email ownership and password-reset attempt limits intact."""

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import OneTimePassword, User


class AccountReleaseTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="release-client",
            email="release-client@example.com",
            phone="+201000000071",
            password="InitialStrongPass123!",
            role=User.Role.CLIENT,
            is_active=True,
            is_verified=True,
        )

    def test_self_service_email_change_requires_new_email_verification(self):
        self.client.force_authenticate(self.user)
        for endpoint in ("/api/v1/auth/me/", "/api/v1/auth/client/profile/"):
            response = self.client.patch(
                endpoint, {"email": "new-owner@example.com"}, format="json"
            )
            self.assertEqual(response.status_code, 400, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "release-client@example.com")
        self.assertTrue(self.user.is_verified)
        unchanged = self.client.patch(
            "/api/v1/auth/me/", {"email": self.user.email.upper()}, format="json"
        )
        self.assertEqual(unchanged.status_code, 200, unchanged.data)

    def test_invalid_password_reset_otp_commits_attempts_and_locks_at_limit(self):
        otp = OneTimePassword.objects.create(
            user=self.user,
            purpose=OneTimePassword.Purpose.PASSWORD_RESET,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        payload = {
            "email": self.user.email,
            "otp": "654321",
            "password": "ReplacementStrongPass456!",
            "password_confirm": "ReplacementStrongPass456!",
        }
        for attempts in range(1, 6):
            response = self.client.post(
                "/api/v1/auth/reset-password", payload, format="json"
            )
            self.assertEqual(response.status_code, 400, response.data)
            otp.refresh_from_db()
            self.assertEqual(otp.attempts, attempts)
        self.assertIsNotNone(otp.used_at)
        payload["otp"] = "123456"
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/reset-password", payload, format="json"
            ).status_code,
            400,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("InitialStrongPass123!"))
