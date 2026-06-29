from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from locations.models import DeliveryArea

from .models import CourierProfile, OneTimePassword

User = get_user_model()
AUTH_BASE = "/api/v1/auth"


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

    def create_active_user(
        self,
        role=User.Role.CLIENT,
        username="customer",
        email=None,
        phone="+213555000001",
    ):
        return User.objects.create_user(
            username=username,
            email=email or self.email,
            phone=phone,
            password=self.password,
            is_active=True,
            role=role,
        )

    def test_registration_requires_otp_before_login(self):
        response = self.client.post(f"{AUTH_BASE}/signup", self.registration_payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], self.email)
        self.assertEqual(len(response.data["dev_otp"]), 6)
        self.assertEqual(len(mail.outbox), 1)

        user = User.objects.get(email=self.email)
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(user.username, "yalla_customer")

        login_response = self.client.post(
            f"{AUTH_BASE}/login",
            {"email": self.email, "password": self.password},
        )
        self.assertEqual(login_response.status_code, status.HTTP_400_BAD_REQUEST)

        verify_response = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": self.email, "otp": response.data["dev_otp"]},
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertIn("accessToken", verify_response.data)
        self.assertIn("refreshToken", verify_response.data)
        self.assertIn("expiresIn", verify_response.data)
        self.assertTrue(User.objects.get(pk=user.pk).is_active)

    def test_registration_rejects_duplicate_active_email(self):
        self.create_active_user()
        response = self.client.post(f"{AUTH_BASE}/signup", self.registration_payload())
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
            f"{AUTH_BASE}/signup",
            self.registration_payload(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["username"],
            ["This username is already taken."],
        )

    def test_registration_rejects_whitespace_in_signup_fields(self):
        payload = self.registration_payload()
        payload["first_name"] = "Ya lla"
        payload["username"] = "yalla customer"
        payload["email"] = "customer @example.com"
        payload["phone"] = "+213 555000001"
        payload["password"] = "Strong Password123!"

        response = self.client.post(f"{AUTH_BASE}/signup", payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["first_name"],
            ["Spaces are not allowed in this field."],
        )
        self.assertIn(
            "Spaces are not allowed in this field.",
            response.data["username"],
        )
        self.assertIn("email", response.data)
        self.assertEqual(
            response.data["phone"],
            ["Spaces are not allowed in this field."],
        )
        self.assertEqual(
            response.data["password"],
            ["Spaces are not allowed in this field."],
        )

    def test_registration_enforces_password_complexity(self):
        payload = self.registration_payload()
        payload["password"] = "password"
        payload["password_confirm"] = "password"

        response = self.client.post(f"{AUTH_BASE}/signup", payload)

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

        response = self.client.post(f"{AUTH_BASE}/signup", payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "Password must be at least 8 characters.",
            response.data["password"],
        )

    def test_login_uses_case_insensitive_email(self):
        self.create_active_user()
        response = self.client.post(
            f"{AUTH_BASE}/login",
            {"email": self.email.upper(), "password": self.password},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], self.email)
        self.assertIn("accessToken", response.data)
        self.assertIn("refreshToken", response.data)
        self.assertIn("expiresIn", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_role_specific_login_endpoints_require_matching_role(self):
        client = self.create_active_user(
            role=User.Role.CLIENT,
            username="client_user",
            email="client@example.com",
            phone="+213555000011",
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="representative_user",
            email="representative@example.com",
            phone="+213555000012",
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="admin_user",
            email="admin@example.com",
            phone="+213555000013",
        )

        client_response = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"email": client.email, "password": self.password},
        )
        representative_response = self.client.post(
            f"{AUTH_BASE}/login/representative/",
            {"email": representative.email, "password": self.password},
        )
        admin_response = self.client.post(
            f"{AUTH_BASE}/login/admin/",
            {"email": admin.email, "password": self.password},
        )
        wrong_role_response = self.client.post(
            f"{AUTH_BASE}/login/admin/",
            {"email": client.email, "password": self.password},
        )

        self.assertEqual(client_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            client_response.data["user"]["role"],
            User.Role.CLIENT,
        )
        self.assertEqual(representative_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            representative_response.data["user"]["role"],
            User.Role.REPRESENTATIVE,
        )
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.data["user"]["role"], User.Role.ADMIN)
        self.assertEqual(
            wrong_role_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            wrong_role_response.data["detail"],
            "This login is only for admin accounts.",
        )

    def test_admin_user_crud_requires_authentication(self):
        response = self.client.get(f"{AUTH_BASE}/users/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_user_crud_requires_admin_role(self):
        client = self.create_active_user()
        refresh = RefreshToken.for_user(client)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(f"{AUTH_BASE}/users/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Only admin users can manage users.")

    def test_admin_can_create_read_update_and_delete_user(self):
        area = DeliveryArea.objects.create(
            name="Central",
            delivery_price="20.00",
            center_latitude="30.0000000",
            center_longitude="31.0000000",
            radius_km="10.00",
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="admin_crud",
            email="admin-crud@example.com",
            phone="+213555000021",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        create_response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "New",
                "last_name": "User",
                "username": "managed_user",
                "email": "managed@example.com",
                "phone": "+213555000022",
                "password": self.password,
                "role": User.Role.REPRESENTATIVE,
                "is_active": True,
                "courier_profile": {
                    "vehicle_type": "Motorcycle",
                    "plate_number": "ABC-123",
                    "delivery_area": area.id,
                    "max_active_orders": 3,
                    "is_available": True,
                },
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["email"], "managed@example.com")
        self.assertEqual(create_response.data["role"], User.Role.REPRESENTATIVE)
        self.assertEqual(
            create_response.data["courier_profile"]["plate_number"],
            "ABC-123",
        )
        self.assertTrue(
            User.objects.get(email="managed@example.com").check_password(
                self.password
            )
        )

        user_id = create_response.data["id"]
        list_response = self.client.get(f"{AUTH_BASE}/users/")
        detail_response = self.client.get(f"{AUTH_BASE}/users/{user_id}/")
        update_response = self.client.patch(
            f"{AUTH_BASE}/users/{user_id}/",
            {
                "first_name": "Updated",
                "role": User.Role.CLIENT,
            },
        )
        delete_response = self.client.delete(f"{AUTH_BASE}/users/{user_id}/")
        deleted_detail_response = self.client.get(f"{AUTH_BASE}/users/{user_id}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(
            int(user_id),
            [int(user["id"]) for user in list_response.data],
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["username"], "managed_user")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["first_name"], "Updated")
        self.assertEqual(update_response.data["role"], User.Role.CLIENT)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertIsNotNone(User.objects.get(pk=user_id).deleted_at)

    def test_admin_can_create_representative_without_courier_profile(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="profile_optional_admin",
            email="profile-optional-admin@example.com",
            phone="+213555000031",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "New",
                "last_name": "Representative",
                "username": "representative_without_profile",
                "email": "representative-without-profile@example.com",
                "phone": "+213555000032",
                "password": self.password,
                "role": User.Role.REPRESENTATIVE,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], User.Role.REPRESENTATIVE)
        self.assertIsNone(response.data["courier_profile"])
        self.assertFalse(
            CourierProfile.objects.filter(user_id=response.data["id"]).exists()
        )

    def test_missing_fields_return_field_specific_required_messages(self):
        login_response = self.client.post(
            f"{AUTH_BASE}/login",
            {"email": self.email},
        )
        self.assertEqual(login_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            login_response.data["password"],
            ["Password is required."],
        )

        blank_password_response = self.client.post(
            f"{AUTH_BASE}/login",
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
            f"{AUTH_BASE}/signup",
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
            f"{AUTH_BASE}/logout",
            {"refreshToken": str(refresh)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Logout successful.")
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())

    def test_refresh_accepts_mobile_refresh_token_name(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            f"{AUTH_BASE}/refresh",
            {"refreshToken": str(refresh)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("accessToken", response.data)
        self.assertIn("refreshToken", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_me_can_be_loaded_and_updated(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        me_response = self.client.get(f"{AUTH_BASE}/me")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], self.email)
        self.assertEqual(me_response.data["username"], "customer")
        self.assertTrue(me_response.data["has_password"])

        update_response = self.client.patch(
            f"{AUTH_BASE}/me",
            {
                "first_name": "Updated",
                "last_name": "Customer",
                "username": "updated_customer",
                "phone": "+213555000009",
                "gender": "male",
                "birth_date": "1995-04-12",
                "avatar_url": "https://example.com/avatar.png",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["first_name"], "Updated")
        self.assertEqual(update_response.data["username"], "updated_customer")
        self.assertEqual(update_response.data["gender"], "male")
        self.assertEqual(update_response.data["birth_date"], "1995-04-12")
        self.assertEqual(
            update_response.data["avatar_url"],
            "https://example.com/avatar.png",
        )
        self.assertIsNotNone(update_response.data["username_changed_at"])
        user.refresh_from_db()
        self.assertEqual(user.phone, "+213555000009")
        self.assertEqual(user.gender, "male")
        self.assertEqual(user.birth_date.isoformat(), "1995-04-12")
        self.assertIsNotNone(user.username_changed_at)

    def test_me_delete_requires_password_and_deletes_account(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        invalid_response = self.client.delete(
            f"{AUTH_BASE}/me",
            {"password": "wrong"},
            format="json",
        )
        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

        response = self.client.delete(
            f"{AUTH_BASE}/me",
            {"password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.deleted_at)
        self.assertNotEqual(user.email, self.email)
        self.assertTrue(user.email.endswith("@deleted.local"))
        self.assertTrue(user.username.startswith("deleted-"))
        self.assertTrue(user.phone.startswith("deleted-"))
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())

        self.client.credentials()
        email_response = self.client.get(
            f"{AUTH_BASE}/check-email",
            {"email": self.email},
        )
        self.assertTrue(email_response.data["available"])
        self.assertFalse(email_response.data["registered"])

    def test_availability_checks(self):
        self.create_active_user()

        username_response = self.client.get(
            f"{AUTH_BASE}/check-username",
            {"username": "customer"},
        )
        self.assertEqual(username_response.status_code, status.HTTP_200_OK)
        self.assertFalse(username_response.data["available"])
        self.assertTrue(username_response.data["registered"])

        email_response = self.client.get(
            f"{AUTH_BASE}/check-email",
            {"email": self.email.upper()},
        )
        self.assertFalse(email_response.data["available"])
        self.assertTrue(email_response.data["registered"])

        phone_response = self.client.get(
            f"{AUTH_BASE}/check-phone",
            {"phone": "+213555000009"},
        )
        self.assertTrue(phone_response.data["available"])
        self.assertFalse(phone_response.data["registered"])

    def test_resend_registration_otp(self):
        signup_response = self.client.post(
            f"{AUTH_BASE}/signup",
            self.registration_payload(),
        )
        self.assertEqual(signup_response.status_code, status.HTTP_201_CREATED)

        resend_response = self.client.post(
            f"{AUTH_BASE}/resend-verification",
            {"email": self.email},
        )
        self.assertEqual(resend_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resend_response.data["dev_otp"]), 6)

    def test_forgot_and_reset_password_with_otp(self):
        user = self.create_active_user()
        existing_refresh = RefreshToken.for_user(user)

        forgot_response = self.client.post(
            f"{AUTH_BASE}/forgot-password",
            {"email": self.email},
        )
        self.assertEqual(forgot_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(forgot_response.data["dev_otp"]), 6)
        self.assertEqual(len(mail.outbox), 1)

        reset_response = self.client.post(
            f"{AUTH_BASE}/reset-password",
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
            f"{AUTH_BASE}/reset-password",
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
            f"{AUTH_BASE}/forgot-password",
            {"email": "unknown@example.com"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("dev_otp", response.data)

    def test_invalid_otp_is_limited(self):
        register_response = self.client.post(
            f"{AUTH_BASE}/signup",
            self.registration_payload(),
        )
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)

        for _ in range(5):
            response = self.client.post(
                f"{AUTH_BASE}/verify-email",
                {"email": self.email, "otp": "000000"},
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        otp = OneTimePassword.objects.get(
            user__email=self.email,
            purpose=OneTimePassword.Purpose.REGISTRATION,
        )
        self.assertEqual(otp.attempts, 5)
        self.assertIsNotNone(otp.used_at)
