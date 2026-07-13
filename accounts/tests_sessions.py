from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .client_sessions import (
    CLIENT_SESSION_EXPIRES_AT_CLAIM,
    CLIENT_SESSION_MODE_CLAIM,
    CLIENT_SESSION_STARTED_AT_CLAIM,
    PERSISTENT_MODE,
    TEMPORARY_MODE,
    sync_outstanding_token,
)


User = get_user_model()
AUTH_BASE = "/api/v1/auth"


@contextmanager
def jwt_time(value):
    with patch("django.utils.timezone.now", return_value=value), patch(
        "rest_framework_simplejwt.tokens.aware_utcnow",
        return_value=value,
    ):
        yield


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ClientSessionPolicyTests(APITestCase):
    password = "StrongPassword123!"
    role = User.Role.CLIENT
    login_endpoint = "client"

    def setUp(self):
        self.user = User.objects.create_user(
            username=f"session_{self.login_endpoint}",
            email=f"session-{self.login_endpoint}@example.com",
            phone="+213555000081",
            password=self.password,
            is_active=True,
            role=self.role,
        )
        self.started_at = timezone.now().replace(microsecond=0)

    def login(self, *, remember_marker="omitted", at=None):
        payload = {
            "identifier": self.user.email,
            "password": self.password,
        }
        if remember_marker != "omitted":
            payload["remember"] = remember_marker
        with jwt_time(at or self.started_at):
            return self.client.post(
                f"{AUTH_BASE}/login/{self.login_endpoint}/",
                payload,
                format="json",
            )

    def refresh(self, raw_refresh, *, at):
        with jwt_time(at):
            return self.client.post(
                f"{AUTH_BASE}/refresh/",
                {"refreshToken": raw_refresh},
                format="json",
            )

    def test_omitted_remember_defaults_to_temporary_with_metadata(self):
        response = self.login()

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, response.data
        )
        refresh = RefreshToken(response.data["refreshToken"])
        expected_deadline = int(
            (self.started_at + timedelta(hours=8)).timestamp()
        )
        self.assertEqual(refresh[CLIENT_SESSION_MODE_CLAIM], TEMPORARY_MODE)
        self.assertEqual(
            refresh[CLIENT_SESSION_STARTED_AT_CLAIM],
            int(self.started_at.timestamp()),
        )
        self.assertEqual(
            refresh[CLIENT_SESSION_EXPIRES_AT_CLAIM], expected_deadline
        )
        self.assertEqual(refresh["exp"], expected_deadline)
        self.assertEqual(
            response.data["session"]["mode"], TEMPORARY_MODE
        )
        self.assertFalse(response.data["session"]["remember"])
        self.assertEqual(response.data["expiresIn"], 900)

    def test_explicit_false_uses_temporary_policy(self):
        response = self.login(remember_marker=False)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, response.data
        )
        self.assertEqual(
            response.data["session"]["mode"], TEMPORARY_MODE
        )
        self.assertIsNotNone(
            response.data["session"]["absoluteExpiresAt"]
        )

    def test_inactive_login_has_stable_account_inactive_code(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.login(remember_marker=True)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_inactive")

    def test_persistent_login_uses_seven_day_refresh_lifetime(self):
        response = self.login(remember_marker=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = RefreshToken(response.data["refreshToken"])
        self.assertEqual(refresh[CLIENT_SESSION_MODE_CLAIM], PERSISTENT_MODE)
        self.assertNotIn(CLIENT_SESSION_EXPIRES_AT_CLAIM, refresh)
        self.assertEqual(
            refresh["exp"] - int(self.started_at.timestamp()),
            int(timedelta(days=7).total_seconds()),
        )
        self.assertTrue(response.data["session"]["remember"])
        self.assertIsNone(response.data["session"]["absoluteExpiresAt"])

    def test_persistent_refresh_slides_seven_days_and_blacklists_old_token(self):
        login = self.login(remember_marker=True)
        old_refresh = login.data["refreshToken"]
        refreshed_at = self.started_at + timedelta(days=6)

        response = self.refresh(old_refresh, at=refreshed_at)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, response.data
        )
        rotated = RefreshToken(response.data["refreshToken"], verify=False)
        self.assertEqual(
            rotated["exp"] - int(refreshed_at.timestamp()),
            int(timedelta(days=7).total_seconds()),
        )
        self.assertEqual(
            rotated[CLIENT_SESSION_STARTED_AT_CLAIM],
            int(self.started_at.timestamp()),
        )
        with self.assertRaises(TokenError):
            RefreshToken(old_refresh)
        reuse = self.refresh(
            old_refresh,
            at=refreshed_at + timedelta(seconds=1),
        )
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse.data["code"], "token_not_valid")

    def test_expired_blacklisted_refresh_remains_revoked(self):
        login = self.login(remember_marker=True)
        old_refresh = login.data["refreshToken"]
        self.refresh(
            old_refresh,
            at=self.started_at + timedelta(days=6),
        )

        reuse = self.refresh(
            old_refresh,
            at=self.started_at + timedelta(days=8),
        )

        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse.data["code"], "token_not_valid")

    def test_persistent_inactivity_expiration_has_stable_code(self):
        login = self.login(remember_marker=True)

        response = self.refresh(
            login.data["refreshToken"],
            at=self.started_at + timedelta(days=7),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "session_expired")

    def test_temporary_refreshes_preserve_original_deadline(self):
        expected_deadline = int(
            (self.started_at + timedelta(hours=8)).timestamp()
        )

        for hour in (2, 5, 7):
            login = self.login(remember_marker=False)
            response = self.refresh(
                login.data["refreshToken"],
                at=self.started_at + timedelta(hours=hour),
            )
            self.assertEqual(
                response.status_code, status.HTTP_200_OK, response.data
            )
            rotated = RefreshToken(
                response.data["refreshToken"], verify=False
            )
            self.assertEqual(rotated["exp"], expected_deadline)
            self.assertEqual(
                rotated[CLIENT_SESSION_EXPIRES_AT_CLAIM],
                expected_deadline,
            )

    def test_access_and_refresh_never_outlive_temporary_deadline(self):
        login = self.login(remember_marker=False)
        refresh_at = self.started_at + timedelta(hours=7, minutes=55)

        response = self.refresh(login.data["refreshToken"], at=refresh_at)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, response.data
        )
        refresh = RefreshToken(response.data["refreshToken"], verify=False)
        access = AccessToken(response.data["accessToken"], verify=False)
        deadline = int((self.started_at + timedelta(hours=8)).timestamp())
        self.assertEqual(refresh["exp"], deadline)
        self.assertEqual(access["exp"], deadline)
        self.assertEqual(response.data["expiresIn"], 300)

    def test_temporary_refresh_at_deadline_is_rejected(self):
        login = self.login(remember_marker=False)

        response = self.refresh(
            login.data["refreshToken"],
            at=self.started_at + timedelta(hours=8),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "session_expired")

    def test_inactive_account_has_priority_over_expired_session(self):
        login = self.login(remember_marker=False)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.refresh(
            login.data["refreshToken"],
            at=self.started_at + timedelta(hours=9),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_inactive")

    def test_inactive_account_has_priority_over_blacklisted_refresh(self):
        login = self.login(remember_marker=False)
        old_refresh = login.data["refreshToken"]
        self.refresh(
            old_refresh,
            at=self.started_at + timedelta(hours=1),
        )
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.refresh(
            old_refresh,
            at=self.started_at + timedelta(hours=2),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_inactive")

    def test_token_version_revocation_remains_invalid(self):
        login = self.login(remember_marker=False)
        self.user.auth_token_version += 1
        self.user.save(update_fields=["auth_token_version"])

        response = self.refresh(
            login.data["refreshToken"],
            at=self.started_at + timedelta(hours=1),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        if self.role == User.Role.REPRESENTATIVE:
            self.assertIn("Password changed", str(response.data))
        else:
            self.assertEqual(
                response.data.get("code"), "token_not_valid", response.data
            )

    def test_legacy_token_gets_eight_hour_grace_from_current_iat(self):
        with jwt_time(self.started_at):
            legacy = RefreshToken.for_user(self.user)
            legacy["auth_token_version"] = self.user.auth_token_version
            sync_outstanding_token(legacy, user=self.user)
            raw_legacy = str(legacy)

        response = self.refresh(
            raw_legacy,
            at=self.started_at + timedelta(hours=7),
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, response.data
        )
        rotated = RefreshToken(response.data["refreshToken"], verify=False)
        self.assertEqual(rotated[CLIENT_SESSION_MODE_CLAIM], TEMPORARY_MODE)
        self.assertEqual(
            rotated["exp"],
            int((self.started_at + timedelta(hours=8)).timestamp()),
        )

    def test_expired_legacy_token_is_rejected(self):
        with jwt_time(self.started_at):
            legacy = RefreshToken.for_user(self.user)
            legacy["auth_token_version"] = self.user.auth_token_version
            sync_outstanding_token(legacy, user=self.user)

        response = self.refresh(
            str(legacy),
            at=self.started_at + timedelta(hours=8),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "session_expired")

    def test_logout_blacklists_current_refresh_but_not_access_token(self):
        login = self.login(remember_marker=False)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.data['accessToken']}"
        )

        response = self.client.post(
            f"{AUTH_BASE}/logout/",
            {"refreshToken": login.data["refreshToken"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with self.assertRaises(TokenError):
            RefreshToken(login.data["refreshToken"])
        reuse = self.refresh(
            login.data["refreshToken"],
            at=self.started_at + timedelta(seconds=1),
        )
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse.data["code"], "token_not_valid")
        me_response = self.client.get(f"{AUTH_BASE}/me/")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)


class RepresentativeSessionPolicyTests(ClientSessionPolicyTests):
    role = User.Role.REPRESENTATIVE
    login_endpoint = "representative"
