import io
import os
import shutil
import tempfile
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from locations.models import DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from orders.models import Order

from .models import CourierProfile, OTPCooldown, OneTimePassword
from .services import issue_otp

User = get_user_model()
AUTH_BASE = "/api/v1/auth"


def profile_image_file(name="avatar.png", size=(4, 4), image_format="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(32, 120, 180)).save(buffer, format=image_format)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type=f"image/{image_format.lower()}",
    )


def oversized_profile_image_file():
    buffer = io.BytesIO()
    image = Image.effect_noise((1800, 1800), 100).convert("RGB")
    image.save(buffer, format="PNG")
    content = buffer.getvalue()
    if len(content) <= 5 * 1024 * 1024:
        content += b"0" * ((5 * 1024 * 1024) - len(content) + 1)
    return SimpleUploadedFile(
        "huge.png",
        content,
        content_type="image/png",
    )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTH_OTP_INCLUDE_IN_RESPONSE=True,
)
class AuthenticationAPITests(APITestCase):
    password = "StrongPassword123!"
    new_password = "NewStrongPassword456!"
    email = "customer@example.com"

    def setUp(self):
        super().setUp()
        self._media_root = tempfile.mkdtemp()
        self._media_override = override_settings(MEDIA_ROOT=self._media_root)
        self._media_override.enable()

    def tearDown(self):
        self._media_override.disable()
        shutil.rmtree(self._media_root, ignore_errors=True)
        super().tearDown()

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

    def create_order_market(self):
        classification, _ = MarketClassification.objects.get_or_create(
            name="Account tests market",
        )
        return Market.objects.create(
            classification=classification,
            name="Account Test Market",
            scope=Market.Scope.GENERAL,
        )

    def create_customer_order(
        self,
        user,
        market,
        status_value,
        total,
        created_at,
    ):
        order = Order.objects.create(
            user=user,
            market=market,
            payment_method="cash",
            status=status_value,
            order_scope=Order.Scope.GENERAL,
            delivery_type=Order.DeliveryType.DELIVERY,
            subtotal_price=total,
            total_price=total,
        )
        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
        return order

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
        city = ServiceCity.objects.create(
            name="Algiers",
            center_latitude="30.0000000",
            center_longitude="31.0000000",
            radius_km="20.00",
        )
        area = DeliveryArea.objects.create(
            service_city=city,
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

    def test_admin_detail_for_client_returns_customer_stats_and_recent_orders(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="detail_stats_admin",
            email="detail-stats-admin@example.com",
            phone="+213555000023",
        )
        client = self.create_active_user(
            username="detail_stats_client",
            email="detail-stats-client@example.com",
            phone="+213555000024",
        )
        market = self.create_order_market()
        base_time = timezone.now() - timedelta(days=20)
        statuses = [
            Order.Status.DELIVERED,
            Order.Status.CANCELLED,
            Order.Status.FAILED_DELIVERY,
            Order.Status.PENDING,
            Order.Status.DELIVERED,
            Order.Status.CONFIRMED,
            Order.Status.DELIVERED,
            Order.Status.READY,
            Order.Status.ON_THE_WAY,
            Order.Status.DELIVERED,
            Order.Status.UNDER_PREPARATION,
            Order.Status.CANCELLED,
        ]
        orders = [
            self.create_customer_order(
                client,
                market,
                status_value,
                Decimal(index + 1),
                base_time + timedelta(hours=index),
            )
            for index, status_value in enumerate(statuses)
        ]
        newest = self.create_customer_order(
            client,
            market,
            Order.Status.FAILED_DELIVERY,
            Decimal("999.00"),
            timezone.now(),
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(f"{AUTH_BASE}/users/{client.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["customer_stats"]["orders_count"], 13)
        self.assertEqual(response.data["customer_stats"]["completed_orders_count"], 4)
        self.assertEqual(response.data["customer_stats"]["total_spent"], "23.00")
        self.assertEqual(
            response.data["customer_stats"]["last_order_at"],
            newest.created_at,
        )
        self.assertEqual(len(response.data["recent_orders"]), 10)
        self.assertEqual(response.data["recent_orders"][0]["id"], newest.id)
        self.assertEqual(
            response.data["recent_orders"][0]["number"],
            f"YM-{newest.created_at:%Y%m%d}-{newest.id:06d}",
        )
        self.assertIsInstance(response.data["recent_orders"][0]["id"], int)
        self.assertEqual(
            [item["id"] for item in response.data["recent_orders"]],
            [order.id for order in [newest, *reversed(orders[-9:])]],
        )
        self.assertNotIn("customer_stats", self.client.get(f"{AUTH_BASE}/users/").data[0])

    def test_admin_patch_detail_for_client_keeps_customer_stats_and_recent_orders(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="patch_detail_admin",
            email="patch-detail-admin@example.com",
            phone="+213555000123",
        )
        client = self.create_active_user(
            username="patch_detail_client",
            email="patch-detail-client@example.com",
            phone="+213555000124",
        )
        market = self.create_order_market()
        order = self.create_customer_order(
            client,
            market,
            Order.Status.DELIVERED,
            Decimal("125.50"),
            timezone.now() - timedelta(days=2),
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/users/{client.id}/",
            {"is_active": False},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])
        self.assertEqual(response.data["customer_stats"]["orders_count"], 1)
        self.assertEqual(response.data["customer_stats"]["completed_orders_count"], 1)
        self.assertEqual(response.data["customer_stats"]["total_spent"], "125.50")
        self.assertEqual(response.data["customer_stats"]["last_order_at"], order.created_at)
        self.assertEqual(response.data["recent_orders"][0]["id"], order.id)
        self.assertIsInstance(response.data["recent_orders"][0]["id"], int)
        self.assertEqual(
            response.data["recent_orders"][0]["number"],
            f"YM-{order.created_at:%Y%m%d}-{order.id:06d}",
        )

    def test_admin_detail_for_client_without_orders_returns_empty_customer_data(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="no_order_admin",
            email="no-order-admin@example.com",
            phone="+213555000025",
        )
        client = self.create_active_user(
            username="no_order_client",
            email="no-order-client@example.com",
            phone="+213555000026",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(f"{AUTH_BASE}/users/{client.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["customer_stats"],
            {
                "orders_count": 0,
                "completed_orders_count": 0,
                "total_spent": "0.00",
                "last_order_at": None,
            },
        )
        self.assertEqual(response.data["recent_orders"], [])

    def test_admin_detail_for_non_client_returns_no_customer_stats(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="non_client_detail_admin",
            email="non-client-detail-admin@example.com",
            phone="+213555000027",
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="non_client_detail_rep",
            email="non-client-detail-rep@example.com",
            phone="+213555000028",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(f"{AUTH_BASE}/users/{representative.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["customer_stats"])
        self.assertEqual(response.data["recent_orders"], [])

    def test_successful_logins_update_last_login_but_failures_and_refresh_do_not(self):
        client = self.create_active_user(
            username="last_login_client",
            email="last-login-client@example.com",
            phone="+213555000029",
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="last_login_admin",
            email="last-login-admin@example.com",
            phone="+213555000030",
        )

        client_response = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"email": client.email, "password": self.password},
        )
        admin_response = self.client.post(
            f"{AUTH_BASE}/login/admin/",
            {"email": admin.email, "password": self.password},
        )
        client.refresh_from_db()
        admin.refresh_from_db()

        self.assertEqual(client_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(client.last_login)
        self.assertIsNotNone(admin.last_login)

        client_login_time = client.last_login
        admin_login_time = admin.last_login
        failed_response = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"email": client.email, "password": "wrong"},
        )
        refresh = RefreshToken.for_user(admin)
        refresh_response = self.client.post(
            f"{AUTH_BASE}/refresh/",
            {"refreshToken": str(refresh)},
        )
        client.refresh_from_db()
        admin.refresh_from_db()

        self.assertEqual(failed_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertEqual(client.last_login, client_login_time)
        self.assertEqual(admin.last_login, admin_login_time)

    def test_disabled_account_receives_neutral_inactive_message(self):
        client = self.create_active_user(
            username="inactive_message_client",
            email="inactive-message-client@example.com",
            phone="+213555000033",
        )
        client.is_active = False
        client.save(update_fields=["is_active"])

        response = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"email": client.email, "password": self.password},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["non_field_errors"], ["Account is inactive."])
        client.refresh_from_db()
        self.assertIsNone(client.last_login)

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

    def test_admin_can_list_only_non_deleted_representatives(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="representative_list_admin",
            email="representative-list-admin@example.com",
            phone="+213555000041",
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="listed_representative",
            email="listed-representative@example.com",
            phone="+213555000042",
        )
        deleted_representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="deleted_representative",
            email="deleted-representative@example.com",
            phone="+213555000043",
        )
        deleted_representative.deleted_at = timezone.now()
        deleted_representative.save(update_fields=["deleted_at"])
        self.create_active_user(
            role=User.Role.CLIENT,
            username="unlisted_client",
            email="unlisted-client@example.com",
            phone="+213555000044",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(f"{AUTH_BASE}/representatives/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [int(item["id"]) for item in response.data],
            [representative.id],
        )
        self.assertEqual(response.data[0]["role"], User.Role.REPRESENTATIVE)
        self.assertIsNone(response.data[0]["courier_profile"])

    def test_representative_list_requires_admin_role(self):
        client = self.create_active_user(
            username="representative_list_client",
            email="representative-list-client@example.com",
            phone="+213555000045",
        )
        refresh = RefreshToken.for_user(client)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(f"{AUTH_BASE}/representatives/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

    def test_client_can_update_profile_information(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {
                "first_name": "Client",
                "last_name": "Updated",
                "username": "client_updated",
                "email": "client-updated@example.com",
                "phone": "+213555000088",
                "gender": "female",
                "birth_date": "1998-08-20",
                "avatar_url": "https://example.com/client-avatar.png",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Client")
        self.assertEqual(response.data["last_name"], "Updated")
        self.assertEqual(response.data["username"], "client_updated")
        self.assertEqual(response.data["email"], "client-updated@example.com")
        self.assertEqual(response.data["phone"], "+213555000088")
        self.assertEqual(response.data["role"], User.Role.CLIENT)
        self.assertIsNotNone(response.data["username_changed_at"])
        user.refresh_from_db()
        self.assertEqual(user.email, "client-updated@example.com")
        self.assertEqual(user.phone, "+213555000088")

    def test_client_profile_same_phone_same_format_is_noop(self):
        user = self.create_active_user(phone="+201012345678")
        original_updated_at = timezone.now() - timedelta(days=1)
        User.objects.filter(pk=user.pk).update(updated_at=original_updated_at)
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"phone": "+201012345678"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.phone, "+201012345678")
        self.assertEqual(user.updated_at, original_updated_at)

    def test_client_profile_equivalent_egyptian_phone_is_noop(self):
        user = self.create_active_user(phone="+201012345678")
        original_updated_at = timezone.now() - timedelta(days=1)
        User.objects.filter(pk=user.pk).update(updated_at=original_updated_at)
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"phone": "01012345678"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.phone, "+201012345678")
        self.assertEqual(user.updated_at, original_updated_at)

    def test_client_profile_valid_different_phone_updates(self):
        user = self.create_active_user(phone="+201012345678")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"phone": "201112345678"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.phone, "+201112345678")

    def test_client_profile_phone_used_by_another_account_is_rejected(self):
        user = self.create_active_user(phone="+201012345678")
        self.create_active_user(
            username="other_customer",
            email="other@example.com",
            phone="+201112345678",
        )
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"phone": "01112345678"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_client_profile_accepts_blank_last_name(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"first_name": "Solo", "last_name": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Solo")
        self.assertEqual(user.last_name, "")

    def test_client_can_upload_profile_avatar_multipart(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"avatar": profile_image_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("/media/avatars/", response.data["avatar_url"])
        self.assertTrue(response.data["avatar_url"].startswith("http://testserver"))
        user.refresh_from_db()
        self.assertTrue(user.avatar_image.name.startswith("avatars/"))

    def test_client_avatar_upload_replaces_old_file(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        first_response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"avatar": profile_image_file("first.png")},
            format="multipart",
        )
        user.refresh_from_db()
        old_path = user.avatar_image.path
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertTrue(os.path.exists(old_path))

        second_response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"avatar": profile_image_file("second.png")},
            format="multipart",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(user.avatar_image.path))
        self.assertNotEqual(first_response.data["avatar_url"], second_response.data["avatar_url"])

    def test_client_avatar_upload_rejects_oversized_file(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"avatar": oversized_profile_image_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("avatar", response.data)

    def test_client_avatar_upload_rejects_invalid_file(self):
        user = self.create_active_user()
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {
                "avatar": SimpleUploadedFile(
                    "avatar.txt",
                    b"not an image",
                    content_type="text/plain",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("avatar", response.data)

    def test_client_profile_json_update_still_works(self):
        user = self.create_active_user(username="json_profile_user")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"first_name": "Json", "last_name": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Json")
        self.assertEqual(response.data["last_name"], "Updated")

    def test_username_first_change_succeeds_and_second_before_seven_days_fails(self):
        user = self.create_active_user(username="cooldown_user")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        first_response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"username": "cooldown_user_next"},
            format="json",
        )
        second_response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"username": "cooldown_user_later"},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(first_response.data["username_changed_at"])
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", second_response.data)

    def test_sending_current_username_does_not_update_username_changed_at(self):
        changed_at = timezone.now() - timedelta(days=2)
        user = self.create_active_user(username="same_username_user")
        user.username_changed_at = changed_at
        user.save(update_fields=["username_changed_at"])
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"username": "same_username_user"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.username_changed_at, changed_at)

    def test_client_profile_update_rejects_non_client_users(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="profile_update_admin",
            email="profile-update-admin@example.com",
            phone="+213555000089",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/client/profile/",
            {"first_name": "Nope"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
        self.assertEqual(signup_response.data["resend_after_seconds"], 30)

        resend_response = self.client.post(
            f"{AUTH_BASE}/resend-verification",
            {"email": self.email},
        )
        self.assertEqual(
            resend_response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        self.assertIn("retry_after_seconds", resend_response.data)

        cooldown = OTPCooldown.objects.get(
            identifier=self.email,
            purpose=OneTimePassword.Purpose.REGISTRATION,
        )
        cooldown.next_allowed_at = timezone.now() - timedelta(seconds=1)
        cooldown.save(update_fields=["next_allowed_at"])

        resend_response = self.client.post(
            f"{AUTH_BASE}/resend-verification",
            {"email": self.email},
        )
        self.assertEqual(resend_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resend_response.data["dev_otp"]), 6)
        self.assertEqual(resend_response.data["resend_after_seconds"], 60)

    def test_otp_cooldown_progresses_to_maximum(self):
        user = self.create_active_user()

        durations = []
        for _ in range(5):
            response = self.client.post(
                f"{AUTH_BASE}/forgot-password",
                {"email": user.email},
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            durations.append(response.data["resend_after_seconds"])
            cooldown = OTPCooldown.objects.get(
                identifier=user.email,
                purpose=OneTimePassword.Purpose.PASSWORD_RESET,
            )
            cooldown.next_allowed_at = timezone.now() - timedelta(seconds=1)
            cooldown.save(update_fields=["next_allowed_at"])

        self.assertEqual(durations, [30, 60, 120, 300, 300])

    def test_otp_cooldowns_are_independent_by_purpose(self):
        user = self.create_active_user()
        OTPCooldown.objects.create(
            identifier=user.email,
            purpose=OneTimePassword.Purpose.REGISTRATION,
            resend_level=3,
            next_allowed_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.post(
            f"{AUTH_BASE}/forgot-password",
            {"email": user.email},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["resend_after_seconds"], 30)

    def test_email_send_failure_does_not_raise_cooldown_level(self):
        user = self.create_active_user()

        with patch("accounts.services.send_mail", side_effect=RuntimeError("down")):
            with self.assertRaises(RuntimeError):
                issue_otp(user, OneTimePassword.Purpose.PASSWORD_RESET)

        self.assertFalse(
            OTPCooldown.objects.filter(
                identifier=user.email,
                purpose=OneTimePassword.Purpose.PASSWORD_RESET,
            ).exists()
        )

    def test_successful_registration_verification_clears_cooldown(self):
        register_response = self.client.post(
            f"{AUTH_BASE}/signup",
            self.registration_payload(),
        )
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            OTPCooldown.objects.filter(
                identifier=self.email,
                purpose=OneTimePassword.Purpose.REGISTRATION,
            ).exists()
        )

        verify_response = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": self.email, "otp": register_response.data["dev_otp"]},
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            OTPCooldown.objects.filter(
                identifier=self.email,
                purpose=OneTimePassword.Purpose.REGISTRATION,
            ).exists()
        )

    def test_forgot_and_reset_password_with_otp(self):
        user = self.create_active_user()
        existing_refresh = RefreshToken.for_user(user)

        forgot_response = self.client.post(
            f"{AUTH_BASE}/forgot-password",
            {"email": self.email},
        )
        self.assertEqual(forgot_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(forgot_response.data["dev_otp"]), 6)
        self.assertEqual(forgot_response.data["resend_after_seconds"], 30)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            OTPCooldown.objects.filter(
                identifier=self.email,
                purpose=OneTimePassword.Purpose.PASSWORD_RESET,
            ).exists()
        )

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
        self.assertFalse(
            OTPCooldown.objects.filter(
                identifier=self.email,
                purpose=OneTimePassword.Purpose.PASSWORD_RESET,
            ).exists()
        )
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
