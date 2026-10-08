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
from .services import OTPCooldownError
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
    @patch("accounts.services._dispatch_otp_email")
    @patch("accounts.services.secrets.choice", return_value="1")
    @patch("accounts.serializers.verify_social_id_token")
    def test_facebook_email_only_verifies_then_completes_profile_inside_app(
        self, verify_token, _choice, _send_email
    ):
        verify_token.return_value = social_identity(
            uid="facebook-deferred", provider="facebook", email="", email_verified=False
        )
        signup = self.client.post(
            f"{AUTH_BASE}/social/signup",
            {
                "id_token": "token",
                "email": "deferred@example.com",
                "defer_profile": True,
                "terms_accepted": True,
            },
            format="json",
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        self.assertTrue(signup.data["verification_required"])
        self.assertNotIn("accessToken", signup.data)
        pending = PendingRegistration.objects.get(email="deferred@example.com")
        self.assertIsNone(pending.phone)
        self.assertTrue(pending.profile_username_pending)
        self.assertEqual(pending.first_name, "Social")

        verified = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": pending.email, "otp": "111111"},
            format="json",
        )
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertIn("accessToken", verified.data)
        user = User.objects.get(email=pending.email)
        self.assertIsNone(user.phone)
        self.assertTrue(user.profile_username_pending)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(
            user.social_identities.filter(firebase_uid="facebook-deferred").exists()
        )

        self.client.force_authenticate(user)
        completed = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {
                "username": "completed.facebook",
                "phone": "+201001234567",
                "city": "Cairo",
            },
            format="json",
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertFalse(user.profile_username_pending)
        self.assertEqual(user.phone, "+201001234567")

    @patch("accounts.services._dispatch_otp_email")
    @patch("accounts.serializers.verify_social_id_token")
    def test_deferred_registrations_do_not_share_a_placeholder_phone(
        self, verify_token, _send_email
    ):
        for number in range(2):
            verify_token.return_value = social_identity(
                uid=f"facebook-{number}",
                provider="facebook",
                email="",
                email_verified=False,
            )
            response = self.client.post(
                f"{AUTH_BASE}/social/signup",
                {
                    "id_token": "token",
                    "email": f"person{number}@example.com",
                    "defer_profile": True,
                    "terms_accepted": True,
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            PendingRegistration.objects.filter(phone__isnull=True).count(), 2
        )
        self.assertEqual(
            PendingRegistration.objects.values("username").distinct().count(), 2
        )

    @patch("accounts.serializers.verify_social_id_token")
    def test_legacy_signup_still_requires_profile_fields(self, verify_token):
        verify_token.return_value = social_identity()
        response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            {"id_token": "token", "terms_accepted": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {"first_name", "username", "phone"})
        self.assertFalse(User.objects.exists())

    @patch("accounts.serializers.verify_social_id_token")
    def test_verified_deferred_signup_uses_signed_name_and_pending_username(
        self, verify_token
    ):
        verify_token.return_value = social_identity(provider="facebook")
        response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            {"id_token": "token", "defer_profile": True, "terms_accepted": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("accessToken", response.data)
        user = User.objects.get(email="social@example.com")
        self.assertEqual(user.first_name, "Social")
        self.assertIsNone(user.phone)
        self.assertTrue(user.profile_username_pending)

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
    def test_facebook_without_email_is_valid_but_not_email_verified(
        self, verify_token, _get_firebase_app
    ):
        verify_token.return_value = {
            "uid": "facebook-no-email",
            "firebase": {"sign_in_provider": "facebook.com"},
            "email_verified": True,
        }

        identity = verify_social_id_token("verified-token")

        self.assertEqual(identity.firebase_uid, "facebook-no-email")
        self.assertEqual(identity.email, "")
        self.assertFalse(identity.email_verified)
        verify_token.assert_called_once_with(
            "verified-token", app=_get_firebase_app.return_value, check_revoked=True
        )

    @patch("accounts.social_auth.get_firebase_app", return_value=object())
    @patch("accounts.social_auth.auth.verify_id_token")
    def test_missing_identity_or_invalid_email_cannot_bypass_token_validation(
        self, verify_token, _get_firebase_app
    ):
        for claims in (
            {"firebase": {"sign_in_provider": "facebook.com"}},
            {"uid": "uid", "firebase": {"sign_in_provider": "password"}},
            {"uid": "uid", "firebase": {"sign_in_provider": "google.com"}},
            {
                "uid": "uid",
                "firebase": {"sign_in_provider": "facebook.com"},
                "email": "invalid-email",
            },
        ):
            with self.subTest(claims=claims):
                verify_token.return_value = claims
                with self.assertRaises(SocialTokenError):
                    verify_social_id_token("verified-token")

    @patch("accounts.services._dispatch_otp_email")
    @patch("accounts.services.secrets.choice", return_value="1")
    @patch("accounts.serializers.verify_social_id_token")
    def test_missing_facebook_email_requires_otp_then_signs_in_by_uid(
        self, verify_token, _choice, _send_email
    ):
        verify_token.return_value = social_identity(
            uid="facebook-no-email", provider="facebook", email="", email_verified=False
        )
        session = self.client.post(
            f"{AUTH_BASE}/social/session", {"id_token": "token"}, format="json"
        )
        self.assertEqual(session.status_code, status.HTTP_200_OK)
        self.assertEqual(session.data["status"], "profile_completion_required")
        self.assertEqual(session.data["email"], "")

        signup = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(email=" Manual@Example.com "),
            format="json",
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        self.assertTrue(signup.data["verification_required"])
        self.assertEqual(signup.data["email"], "manual@example.com")
        self.assertNotIn("accessToken", signup.data)
        self.assertFalse(User.objects.filter(email="manual@example.com").exists())
        self.assertFalse(
            SocialIdentity.objects.filter(firebase_uid="facebook-no-email").exists()
        )

        wrong_code = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": "manual@example.com", "otp": "222222"},
            format="json",
        )
        self.assertEqual(wrong_code.status_code, status.HTTP_400_BAD_REQUEST)
        verified = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": "manual@example.com", "otp": "111111"},
            format="json",
        )
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertTrue(
            SocialIdentity.objects.filter(firebase_uid="facebook-no-email").exists()
        )
        subsequent = self.client.post(
            f"{AUTH_BASE}/social/session", {"id_token": "token"}, format="json"
        )
        self.assertEqual(subsequent.status_code, status.HTTP_200_OK)
        self.assertEqual(subsequent.data["status"], "authenticated")

    @patch("accounts.serializers.verify_social_id_token")
    def test_missing_facebook_email_needs_valid_manual_address(self, verify_token):
        verify_token.return_value = social_identity(
            provider="facebook", email="", email_verified=False
        )
        for fields in ({}, {"email": "invalid-email"}):
            with self.subTest(fields=fields):
                response = self.client.post(
                    f"{AUTH_BASE}/social/signup",
                    self.social_payload(**fields),
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("email", response.data)
        self.assertFalse(PendingRegistration.objects.exists())

    @patch("accounts.serializers.verify_social_id_token")
    def test_client_email_cannot_replace_verified_provider_email(self, verify_token):
        verify_token.return_value = social_identity()
        response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(email="different@example.com"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="social@example.com").exists())
        self.assertFalse(User.objects.filter(email="different@example.com").exists())

    @patch("accounts.serializers.verify_social_id_token")
    def test_missing_email_existing_account_needs_password_to_link(self, verify_token):
        verify_token.return_value = social_identity(
            uid="facebook-no-email", provider="facebook", email="", email_verified=False
        )
        user = User.objects.create_user(
            username="existing", email="existing@example.com", password="StrongPass1!"
        )
        signup = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(email=user.email),
            format="json",
        )
        self.assertEqual(signup.data["status"], "account_link_required")
        self.assertFalse(SocialIdentity.objects.exists())
        same_username = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(email=user.email, username=user.username),
            format="json",
        )
        self.assertEqual(same_username.data["status"], "account_link_required")
        payload = {"id_token": "token", "email": user.email, "password": "wrong"}
        wrong_password = self.client.post(
            f"{AUTH_BASE}/social/link", payload, format="json"
        )
        self.assertEqual(wrong_password.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(SocialIdentity.objects.exists())
        linked = self.client.post(
            f"{AUTH_BASE}/social/link",
            {**payload, "password": "StrongPass1!"},
            format="json",
        )
        self.assertEqual(linked.status_code, status.HTTP_200_OK)
        self.assertTrue(
            SocialIdentity.objects.filter(
                user=user, firebase_uid="facebook-no-email"
            ).exists()
        )

    @patch("accounts.views.issue_registration_otp", side_effect=OTPCooldownError(30))
    @patch("accounts.serializers.verify_social_id_token")
    def test_changing_manual_email_invalidates_code_for_previous_address(
        self, verify_token, _issue_otp
    ):
        verify_token.return_value = social_identity(
            uid="facebook-no-email", provider="facebook", email="", email_verified=False
        )
        pending = PendingRegistration.objects.create(
            first_name="Social",
            last_name="Customer",
            username="social.customer",
            email="previous@example.com",
            phone="+201001234567",
            city="Cairo",
            password_hash=make_password(None),
            terms_accepted_at=timezone.now(),
            firebase_uid="facebook-no-email",
            auth_provider="facebook",
            otp_code_hash=make_password("111111"),
            otp_expires_at=timezone.now() + timedelta(minutes=10),
        )
        response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(email="new@example.com"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        pending.refresh_from_db()
        self.assertEqual(pending.email, "new@example.com")
        self.assertEqual(pending.otp_code_hash, "")
        self.assertIsNone(pending.otp_expires_at)
        self.assertEqual(PendingRegistration.objects.count(), 1)

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

    @patch("accounts.serializers.verify_social_id_token")
    def test_social_sign_in_does_not_reveal_non_client_role(self, verify_token):
        verify_token.return_value = social_identity()
        user = User.objects.create_user(
            username="social.admin",
            email="social@example.com",
            phone="+201111111112",
            password="StrongPass1!",
            role=User.Role.ADMIN,
            is_verified=True,
        )
        payload = {"id_token": "firebase-id-token"}
        unlinked_response = self.client.post(
            f"{AUTH_BASE}/social/session", payload, format="json"
        )
        SocialIdentity.objects.create(
            user=user, firebase_uid="firebase-google-1", provider="google"
        )
        linked_response = self.client.post(
            f"{AUTH_BASE}/social/session", payload, format="json"
        )
        signup_response = self.client.post(
            f"{AUTH_BASE}/social/signup",
            self.social_payload(),
            format="json",
        )
        link_response = self.client.post(
            f"{AUTH_BASE}/social/link",
            {**payload, "password": "StrongPass1!"},
            format="json",
        )
        wrong_password_response = self.client.post(
            f"{AUTH_BASE}/social/link",
            {**payload, "password": "WrongPassword123!"},
            format="json",
        )
        for response in (
            unlinked_response,
            linked_response,
            signup_response,
            link_response,
            wrong_password_response,
        ):
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(response.data, {"detail": "Invalid sign-in credentials."})

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
        self.assertFalse(User.objects.filter(email="social@example.com").exists())

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
