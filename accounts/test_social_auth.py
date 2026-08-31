from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from firebase_admin import auth as firebase_auth
from rest_framework import status
from rest_framework.test import APITestCase

from .deletion import permanently_delete_client_account
from .models import PendingRegistration, SocialIdentity, User
from .serializers import AdminUserWriteSerializer
from .social_auth import (
    SocialTokenError,
    VerifiedSocialIdentity,
    verify_social_id_token,
)


AUTH_BASE = "/api/v1/auth"


def social_identity(
    *,
    uid="firebase-google-1",
    provider="google",
    email="social@example.com",
    email_verified=True,
):
    return VerifiedSocialIdentity(
        firebase_uid=uid,
        provider=provider,
        email=email,
        email_verified=email_verified,
        first_name="Social",
        last_name="Customer",
        avatar_url="https://example.com/avatar.png",
    )


class SocialAuthenticationTests(APITestCase):
    def social_payload(self, **overrides):
        payload = {
            "id_token": "firebase-id-token",
            "first_name": "Social",
            "last_name": "Customer",
            "username": "social.customer",
            "phone": "+201001234567",
            "city": "Cairo",
            "terms_accepted": True,
            "remember": True,
        }
        payload.update(overrides)
        return payload

    def test_admin_user_creation_still_requires_phone(self):
        serializer = AdminUserWriteSerializer()

        self.assertTrue(serializer.fields["phone"].required)
        self.assertFalse(serializer.fields["phone"].allow_null)

    @patch("accounts.social_auth.get_firebase_app", return_value=object())
    @patch("accounts.social_auth.auth.verify_id_token")
    def test_expired_firebase_token_keeps_specific_error(
        self,
        verify_token,
        _get_firebase_app,
    ):
        verify_token.side_effect = firebase_auth.ExpiredIdTokenError(
            "expired",
            None,
        )

        with self.assertRaisesRegex(SocialTokenError, "has expired"):
            verify_social_id_token("expired-token")

    @patch("accounts.social_auth.get_firebase_app", return_value=object())
    @patch("accounts.social_auth.auth.verify_id_token")
    def test_revoked_firebase_token_keeps_specific_error(
        self,
        verify_token,
        _get_firebase_app,
    ):
        verify_token.side_effect = firebase_auth.RevokedIdTokenError("revoked")

        with self.assertRaisesRegex(SocialTokenError, "was revoked"):
            verify_social_id_token("revoked-token")

    @patch("accounts.serializers.verify_social_id_token")
    def test_verified_identity_signs_in_with_incomplete_profile(self, verify_token):
        verify_token.return_value = social_identity()

        response = self.client.post(
            f"{AUTH_BASE}/social/session",
            {"id_token": "firebase-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "authenticated")
        self.assertIn("accessToken", response.data)
        user = User.objects.get(email="social@example.com")
        self.assertIsNone(user.phone)
        self.assertTrue(user.terms_accepted)
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertTrue(user.profile_username_pending)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(
            SocialIdentity.objects.filter(
                user=user,
                firebase_uid="firebase-google-1",
            ).exists()
        )

    @patch("accounts.serializers.verify_social_id_token")
    def test_incomplete_social_profile_can_be_completed_later(self, verify_token):
        verify_token.return_value = social_identity()
        session_response = self.client.post(
            f"{AUTH_BASE}/social/session",
            {"id_token": "firebase-id-token"},
            format="json",
        )
        user = User.objects.get(email="social@example.com")
        self.client.force_authenticate(user)

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {
                "username": "social.customer",
                "phone": "+201001234567",
                "city": "Cairo",
                "gender": "male",
                "birth_date": "1995-04-12",
            },
            format="json",
        )

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.username, "social.customer")
        self.assertEqual(user.phone, "+201001234567")
        self.assertEqual(user.city, "Cairo")
        self.assertEqual(user.gender, "male")
        self.assertEqual(user.birth_date.isoformat(), "1995-04-12")
        self.assertTrue(user.terms_accepted)
        self.assertFalse(user.profile_username_pending)

    @patch("accounts.serializers.verify_social_id_token")
    def test_verified_social_signup_creates_passwordless_client(self, verify_token):
        verify_token.return_value = social_identity()

        response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="social@example.com")
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertTrue(user.is_verified)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(response.data["user"]["has_password"], False)
        self.assertIn("accessToken", response.data)
        self.assertTrue(
            SocialIdentity.objects.filter(
                user=user,
                firebase_uid="firebase-google-1",
                provider="google",
            ).exists()
        )

    @patch("accounts.serializers.verify_social_id_token")
    def test_existing_password_account_requires_then_allows_link(self, verify_token):
        verify_token.return_value = social_identity()
        user = User.objects.create_user(
            username="existing.client",
            email="social@example.com",
            phone="+201111111111",
            password="StrongPass1!",
            role=User.Role.CLIENT,
            is_verified=True,
        )

        session_response = self.client.post(
            f"{AUTH_BASE}/social/session",
            {"id_token": "firebase-id-token"},
            format="json",
        )
        link_response = self.client.post(
            f"{AUTH_BASE}/social/link",
            {
                "id_token": "firebase-id-token",
                "password": "StrongPass1!",
                "remember": False,
            },
            format="json",
        )

        self.assertEqual(session_response.data["status"], "account_link_required")
        self.assertEqual(link_response.status_code, status.HTTP_200_OK)
        self.assertIn("accessToken", link_response.data)
        self.assertTrue(
            SocialIdentity.objects.filter(user=user, provider="google").exists()
        )

    @patch("accounts.views.issue_registration_otp")
    @patch("accounts.serializers.verify_social_id_token")
    def test_unverified_facebook_email_uses_existing_otp_flow(
        self,
        verify_token,
        issue_registration_otp,
    ):
        verify_token.return_value = social_identity(
            uid="firebase-facebook-1",
            provider="facebook",
            email_verified=False,
        )
        issue_registration_otp.side_effect = lambda registration: (
            registration,
            "123456",
            {
                "resend_after_seconds": 30,
                "resend_available_at": timezone.now() + timedelta(seconds=30),
            },
        )

        session_response = self.client.post(
            f"{AUTH_BASE}/social/session",
            {"id_token": "firebase-id-token"},
            format="json",
        )

        response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(),
            format="json",
        )

        self.assertEqual(session_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            session_response.data["status"],
            "profile_completion_required",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["verification_required"])
        pending = PendingRegistration.objects.get(email="social@example.com")
        self.assertEqual(pending.auth_provider, "facebook")
        self.assertEqual(pending.firebase_uid, "firebase-facebook-1")
        self.assertFalse(
            User.objects.filter(email="social@example.com").exists()
        )

    def test_verifying_social_pending_registration_creates_identity(self):
        pending = PendingRegistration.objects.create(
            first_name="Social",
            last_name="Customer",
            username="social.customer",
            email="social@example.com",
            phone="+201001234567",
            city="Cairo",
            password_hash=make_password(None),
            terms_accepted_at=timezone.now(),
            firebase_uid="firebase-facebook-1",
            auth_provider="facebook",
            otp_code_hash=make_password("123456"),
            otp_expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": pending.email, "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email=pending.email)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(
            SocialIdentity.objects.filter(
                user=user,
                firebase_uid="firebase-facebook-1",
            ).exists()
        )

    def test_deleted_social_account_releases_firebase_identity(self):
        user = User.objects.create_user(
            username="social.delete",
            email="social-delete@example.com",
            phone="+201009999999",
            role=User.Role.CLIENT,
            is_verified=True,
        )
        identity = SocialIdentity.objects.create(
            user=user,
            firebase_uid="firebase-google-delete",
            provider="google",
        )

        permanently_delete_client_account(user)

        self.assertFalse(SocialIdentity.objects.filter(pk=identity.pk).exists())
