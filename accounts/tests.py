from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from .models import OneTimePassword

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTH_OTP_INCLUDE_IN_RESPONSE=True,
)
class AuthenticationAPITests(APITestCase):
    password = "StrongPassword123!"
    new_password = "NewStrongPassword456!"
    email = "customer@example.com"

    def registration_payload(self):
        return {
            "first_name": "Yalla",
            "last_name": "Customer",
            "username": "yalla_customer",
            "email": self.email.upper(),
            "phone": "+213555000001",
            "password": self.password,
            "password_confirm": self.password,
            "terms_accepted": True,
        }

    def create_active_user(self):
        return User.objects.create_user(
            username="customer",
            email=self.email,
            phone="+213555000001",
            password=self.password,
            is_active=True,
        )

    def test_registration_requires_otp_before_login(self):
        response = self.client.post("/api/auth/register/", self.registration_payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], self.email)
        self.assertEqual(len(response.data["dev_otp"]), 6)
        self.assertEqual(len(mail.outbox), 1)

        user = User.objects.get(email=self.email)
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(user.username, "yalla_customer")

        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
        )
        self.assertEqual(login_response.status_code, status.HTTP_400_BAD_REQUEST)

        verify_response = self.client.post(
            "/api/auth/register/verify-otp/",
            {"email": self.email, "otp": response.data["dev_otp"]},
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertIn("accessToken", verify_response.data)
        self.assertIn("refreshToken", verify_response.data)
        self.assertTrue(User.objects.get(pk=user.pk).is_active)

    def test_registration_rejects_duplicate_active_email(self):
        self.create_active_user()
        response = self.client.post("/api/auth/register/", self.registration_payload())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_registration_rejects_duplicate_username_case_insensitively(self):
        User.objects.create_user(
            username="Yalla_Customer",
            email="existing@example.com",
            phone="+213555000002",
            password=self.password,
        )

        response = self.client.post(
            "/api/auth/register/",
            self.registration_payload(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["username"],
            ["This username is already taken."],
        )

    def test_registration_enforces_password_complexity(self):
        payload = self.registration_payload()
        payload["password"] = "password"
        payload["password_confirm"] = "password"

        response = self.client.post("/api/auth/register/", payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["password"],
            [
                "Password must contain at least one uppercase letter.",
                "Password must contain at least one number.",
                "Password must contain at least one special character.",
            ],
        )

    def test_registration_rejects_password_shorter_than_eight_characters(self):
        payload = self.registration_payload()
        payload["password"] = "Ab1!"
        payload["password_confirm"] = "Ab1!"

        response = self.client.post("/api/auth/register/", payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "Password must be at least 8 characters.",
            response.data["password"],
        )

    def test_login_uses_case_insensitive_email(self):
        self.create_active_user()
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.email.upper(), "password": self.password},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], self.email)
        self.assertIn("accessToken", response.data)
        self.assertIn("refreshToken", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_missing_fields_return_field_specific_required_messages(self):
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email},
        )
        self.assertEqual(login_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            login_response.data["password"],
            ["Password is required."],
        )

        blank_password_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": ""},
        )
        self.assertEqual(
            blank_password_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            blank_password_response.data["password"],
            ["Password is required."],
        )

        register_response = self.client.post(
            "/api/auth/register/",
            {},
        )
        self.assertEqual(register_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            register_response.data["email"],
            ["Email is required."],
        )
        self.assertEqual(
            register_response.data["username"],
            ["Username is required."],
        )
        self.assertEqual(
            register_response.data["phone"],
            ["Phone is required."],
        )

    def test_logout_blacklists_refresh_token(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.post(
            "/api/auth/logout/",
            {"refresh": str(refresh)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Logout successful.")
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())

    def test_refresh_accepts_mobile_refresh_token_name(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            "/api/auth/refresh/",
            {"refreshToken": str(refresh)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("accessToken", response.data)
        self.assertIn("refreshToken", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_forgot_and_reset_password_with_otp(self):
        user = self.create_active_user()
        existing_refresh = RefreshToken.for_user(user)

        forgot_response = self.client.post(
            "/api/auth/forgot-password/",
            {"email": self.email},
        )
        self.assertEqual(forgot_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(forgot_response.data["dev_otp"]), 6)
        self.assertEqual(len(mail.outbox), 1)

        reset_response = self.client.post(
            "/api/auth/reset-password/",
            {
                "email": self.email,
                "otp": forgot_response.data["dev_otp"],
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
        )
        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password(self.new_password))
        self.assertTrue(
            BlacklistedToken.objects.filter(token__user=user).exists()
        )
        with self.assertRaises(TokenError):
            RefreshToken(str(existing_refresh)).check_blacklist()

        reused_otp_response = self.client.post(
            "/api/auth/reset-password/",
            {
                "email": self.email,
                "otp": forgot_response.data["dev_otp"],
                "password": self.password,
                "password_confirm": self.password,
            },
        )
        self.assertEqual(reused_otp_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forgot_password_does_not_reveal_unknown_email(self):
        response = self.client.post(
            "/api/auth/forgot-password/",
            {"email": "unknown@example.com"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("dev_otp", response.data)

    def test_invalid_otp_is_limited(self):
        register_response = self.client.post(
            "/api/auth/register/",
            self.registration_payload(),
        )
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)

        for _ in range(5):
            response = self.client.post(
                "/api/auth/register/verify-otp/",
                {"email": self.email, "otp": "000000"},
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        otp = OneTimePassword.objects.get(
            user__email=self.email,
            purpose=OneTimePassword.Purpose.REGISTRATION,
        )
        self.assertEqual(otp.attempts, 5)
        self.assertIsNotNone(otp.used_at)
