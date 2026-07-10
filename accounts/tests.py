import io
import importlib
import os
import shutil
import tempfile
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.apps import apps
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from locations.models import DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from notifications.models import ClientDevice, Notification
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
        self.assertEqual(login_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(login_response.data["code"], "account_inactive")

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

    def test_admin_login_remember_true_refresh_exp_is_about_7_days(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="remember_admin",
            email="remember-admin@example.com",
            phone="+213555000071",
        )
        before = int(timezone.now().timestamp())

        response = self.client.post(
            f"{AUTH_BASE}/login/admin/",
            {"email": admin.email, "password": self.password, "remember": True},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = RefreshToken(response.data["refreshToken"])
        self.assertTrue(refresh["admin_remember"])
        self.assertEqual(refresh["admin_session_exp"], refresh["exp"])
        self.assertAlmostEqual(
            refresh["admin_session_exp"] - before,
            int(timedelta(days=7).total_seconds()),
            delta=5,
        )

    def test_admin_login_remember_false_refresh_exp_is_about_8_hours(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="temporary_admin",
            email="temporary-admin@example.com",
            phone="+213555000072",
        )
        before = int(timezone.now().timestamp())

        response = self.client.post(
            f"{AUTH_BASE}/login/admin/",
            {"email": admin.email, "password": self.password, "remember": False},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh = RefreshToken(response.data["refreshToken"])
        self.assertFalse(refresh["admin_remember"])
        self.assertEqual(refresh["admin_session_exp"], refresh["exp"])
        self.assertAlmostEqual(
            refresh["admin_session_exp"] - before,
            int(timedelta(hours=8).total_seconds()),
            delta=5,
        )

    def test_admin_refresh_preserves_original_admin_session_exp(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="refresh_admin",
            email="refresh-admin@example.com",
            phone="+213555000073",
        )
        login_response = self.client.post(
            f"{AUTH_BASE}/login/admin/",
            {"email": admin.email, "password": self.password, "remember": True},
        )
        original = RefreshToken(login_response.data["refreshToken"])

        response = self.client.post(
            f"{AUTH_BASE}/refresh/",
            {"refreshToken": login_response.data["refreshToken"]},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rotated = RefreshToken(response.data["refreshToken"])
        self.assertEqual(
            rotated["admin_session_exp"], original["admin_session_exp"]
        )
        self.assertEqual(rotated["exp"], original["admin_session_exp"])
        self.assertTrue(rotated["admin_remember"])

    def test_admin_refresh_after_admin_session_exp_returns_401(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="expired_admin",
            email="expired-admin@example.com",
            phone="+213555000074",
        )
        refresh = RefreshToken.for_user(admin)
        refresh["admin_session_exp"] = int(timezone.now().timestamp()) - 1
        refresh["admin_remember"] = False

        response = self.client.post(
            f"{AUTH_BASE}/refresh/", {"refreshToken": str(refresh)}
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["detail"], "Session expired. Please login again."
        )

    def test_client_or_representative_login_not_broken(self):
        client = self.create_active_user(
            username="unaffected_client",
            email="unaffected-client@example.com",
            phone="+213555000075",
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="unaffected_representative",
            email="unaffected-representative@example.com",
            phone="+213555000076",
        )

        client_response = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"email": client.email, "password": self.password},
        )
        representative_response = self.client.post(
            f"{AUTH_BASE}/login/representative/",
            {"email": representative.email, "password": self.password},
        )

        self.assertEqual(client_response.status_code, status.HTTP_200_OK)
        self.assertEqual(representative_response.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            "admin_session_exp", RefreshToken(client_response.data["refreshToken"])
        )
        self.assertNotIn(
            "admin_session_exp",
            RefreshToken(representative_response.data["refreshToken"]),
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
                    "service_city": city.id,
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
        self.assertEqual(
            create_response.data["courier_profile"]["service_city"],
            city.id,
        )
        self.assertIsNone(
            CourierProfile.objects.get(user_id=create_response.data["id"]).delivery_area_id
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

    def test_admin_can_restore_a_soft_deleted_representative(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="restore_courier_admin",
            email="restore-courier-admin@example.com",
            phone="+213555000130",
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="restore_courier",
            email="restore-courier@example.com",
            phone="+213555000131",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        delete_response = self.client.delete(f"{AUTH_BASE}/users/{representative.id}/")
        restore_response = self.client.post(
            f"{AUTH_BASE}/users/{representative.id}/restore/"
        )

        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)
        representative.refresh_from_db()
        self.assertIsNone(representative.deleted_at)
        self.assertTrue(representative.is_active)
        self.assertEqual(representative.username, "restore_courier")
        self.assertEqual(representative.email, "restore-courier@example.com")
        self.assertEqual(representative.phone, "+213555000131")

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
            Order.Status.ASSIGNED,
            Order.Status.PICKED_UP,
            Order.Status.DELIVERED,
            Order.Status.CONFIRMED,
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

    def test_admin_detail_reflects_the_client_saved_market_region(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="region_detail_admin",
            email="region-detail-admin@example.com",
            phone="+213555000126",
        )
        client = self.create_active_user(
            username="region_detail_client",
            email="region-detail-client@example.com",
            phone="+213555000127",
        )
        first_city = ServiceCity.objects.create(name="First Service City")
        updated_city = ServiceCity.objects.create(name="Updated Service City")
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        no_selection_response = self.client.get(f"{AUTH_BASE}/users/{client.id}/")
        self.assertEqual(no_selection_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(no_selection_response.data["market_region_mode"])
        self.assertIsNone(
            no_selection_response.data["market_region_service_city_name"]
        )

        client.market_region_mode = User.MarketRegionMode.GENERAL
        client.market_region_service_city = None
        client.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "updated_at",
            ]
        )
        general_response = self.client.get(f"{AUTH_BASE}/users/{client.id}/")
        self.assertEqual(
            general_response.data["market_region_mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertIsNone(general_response.data["market_region_service_city_name"])

        client.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        client.market_region_service_city = first_city
        client.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "updated_at",
            ]
        )
        city_response = self.client.get(f"{AUTH_BASE}/users/{client.id}/")
        self.assertEqual(
            city_response.data["market_region_service_city_name"],
            first_city.name,
        )

        client.market_region_service_city = updated_city
        client.save(
            update_fields=["market_region_service_city", "updated_at"]
        )
        updated_city_response = self.client.get(f"{AUTH_BASE}/users/{client.id}/")
        self.assertEqual(
            updated_city_response.data["market_region_service_city_name"],
            updated_city.name,
        )

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

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data,
            {
                "code": "account_inactive",
                "detail": "تم إيقاف حسابك. تواصل مع الدعم.",
            },
        )
        client.refresh_from_db()
        self.assertIsNone(client.last_login)

    def test_inactive_client_refresh_is_rejected_with_stable_contract(self):
        client = self.create_active_user(
            username="inactive_refresh_client",
            email="inactive-refresh-client@example.com",
            phone="+213555000039",
        )
        refresh = RefreshToken.for_user(client)
        refresh["auth_token_version"] = client.auth_token_version
        client.is_active = False
        client.save(update_fields=["is_active"])

        response = self.client.post(
            f"{AUTH_BASE}/refresh/",
            {"refreshToken": str(refresh)},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_inactive")

    @patch("accounts.deactivation._dispatch_account_disabled")
    def test_admin_customer_patch_uses_user_only_lock(self, dispatch):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="locking_admin",
            email="locking-admin@example.com",
            phone="+213555000144",
        )
        client = self.create_active_user(
            username="locking_client",
            email="locking-client@example.com",
            phone="+213555000145",
        )
        self.assertIsNone(client.market_region_service_city_id)
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with CaptureQueriesContext(connection) as queries:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.patch(
                    f"{AUTH_BASE}/users/{client.id}/",
                    {"is_active": False},
                    format="json",
                )

        locking_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "accounts_user"' in query["sql"]
            and '"accounts_user"."deleted_at" IS NULL' in query["sql"]
        ]
        self.assertEqual(len(locking_queries), 1)
        locking_sql = locking_queries[0].upper()
        self.assertNotIn(" JOIN ", locking_sql)
        if connection.features.has_select_for_update:
            self.assertIn("FOR UPDATE", locking_sql)

        client.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(client.is_active)
        self.assertEqual(client.auth_token_version, 1)
        self.assertTrue(
            Notification.objects.filter(
                recipient=client,
                type=Notification.Type.ACCOUNT_DISABLED,
            ).exists()
        )
        dispatch.assert_called_once_with(client.id)

    @patch("accounts.deactivation._dispatch_account_disabled")
    def test_admin_deactivation_dispatches_once_after_commit(self, dispatch):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="deactivation_admin",
            email="deactivation-admin@example.com",
            phone="+213555000040",
        )
        client = self.create_active_user(
            username="deactivation_client",
            email="deactivation-client@example.com",
            phone="+213555000041",
        )
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"is_active": False},
                format="json",
            )
        client.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(client.auth_token_version, 1)
        self.assertTrue(
            Notification.objects.filter(
                recipient=client,
                type=Notification.Type.ACCOUNT_DISABLED,
            ).exists()
        )
        dispatch.assert_called_once_with(client.id)

        dispatch.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            repeat = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"first_name": "Still disabled", "is_active": False},
                format="json",
            )
        self.assertEqual(repeat.status_code, status.HTTP_200_OK)
        self.assertEqual(client.auth_token_version, 1)
        self.assertEqual(
            Notification.objects.filter(
                recipient=client,
                type=Notification.Type.ACCOUNT_DISABLED,
            ).count(),
            1,
        )
        dispatch.assert_not_called()

    def test_admin_can_reactivate_an_inactive_client_without_notification(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="reactivation_admin",
            email="reactivation-admin@example.com",
            phone="+213555000130",
        )
        client = self.create_active_user(
            username="reactivation_client",
            email="reactivation-client@example.com",
            phone="+213555000131",
        )
        client.is_active = False
        client.auth_token_version = 4
        client.save(update_fields=["is_active", "auth_token_version"])
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.patch(
            f"{AUTH_BASE}/users/{client.id}/",
            {"is_active": True},
            format="json",
        )

        client.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertTrue(client.is_active)
        self.assertEqual(client.auth_token_version, 4)
        self.assertFalse(
            Notification.objects.filter(
                recipient=client,
                type=Notification.Type.ACCOUNT_DISABLED,
            ).exists()
        )

    def test_admin_profile_update_does_not_run_deactivation_logic(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="profile_update_admin",
            email="profile-update-admin@example.com",
            phone="+213555000132",
        )
        client = self.create_active_user(
            username="profile_update_client",
            email="profile-update-client@example.com",
            phone="+213555000133",
        )
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with patch("accounts.deactivation.handle_client_deactivation") as deactivation:
            response = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"first_name": "Updated"},
                format="json",
            )

        client.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(client.first_name, "Updated")
        self.assertTrue(client.is_active)
        self.assertEqual(client.auth_token_version, 0)
        deactivation.assert_not_called()

    @override_settings(
        FIREBASE_SERVICE_ACCOUNT_BASE64="",
        FIREBASE_SERVICE_ACCOUNT_JSON="",
    )
    @patch("accounts.deactivation.logger")
    def test_admin_deactivation_succeeds_when_firebase_configuration_fails(self, logger):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="firebase_failure_admin",
            email="firebase-failure-admin@example.com",
            phone="+213555000134",
        )
        client = self.create_active_user(
            username="firebase_failure_client",
            email="firebase-failure-client@example.com",
            phone="+213555000135",
        )
        ClientDevice.objects.create(
            user=client,
            token="firebase-config-failure-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        client_refresh = RefreshToken.for_user(client)
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"is_active": False},
                format="json",
            )

        client.refresh_from_db()
        device = ClientDevice.objects.get(user=client)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertFalse(client.is_active)
        self.assertEqual(client.auth_token_version, 1)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=client_refresh["jti"]).exists()
        )
        self.assertFalse(device.is_active)
        self.assertTrue(
            Notification.objects.filter(
                recipient=client,
                type=Notification.Type.ACCOUNT_DISABLED,
            ).exists()
        )
        logger.exception.assert_called_once()

    @patch("notifications.push._send_tokens", side_effect=RuntimeError("FCM failed"))
    @patch("accounts.deactivation.logger")
    def test_admin_deactivation_succeeds_when_firebase_send_fails(
        self,
        logger,
        send_tokens,
    ):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="firebase_send_failure_admin",
            email="firebase-send-failure-admin@example.com",
            phone="+213555000136",
        )
        client = self.create_active_user(
            username="firebase_send_failure_client",
            email="firebase-send-failure-client@example.com",
            phone="+213555000137",
        )
        ClientDevice.objects.create(
            user=client,
            token="firebase-send-failure-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"is_active": False},
                format="json",
            )

        client.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertFalse(client.is_active)
        self.assertEqual(client.auth_token_version, 1)
        self.assertTrue(send_tokens.called)
        logger.exception.assert_called_once()

    @override_settings(
        FIREBASE_SERVICE_ACCOUNT_BASE64="",
        FIREBASE_SERVICE_ACCOUNT_JSON="",
    )
    @patch("notifications.push._messaging_module")
    def test_admin_deactivation_with_no_device_skips_firebase_initialization(
        self,
        messaging_module,
    ):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="no_device_admin",
            email="no-device-admin@example.com",
            phone="+213555000138",
        )
        client = self.create_active_user(
            username="no_device_client",
            email="no-device-client@example.com",
            phone="+213555000139",
        )
        token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"is_active": False},
                format="json",
            )

        client.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertFalse(client.is_active)
        self.assertEqual(client.auth_token_version, 1)
        messaging_module.assert_not_called()

    def test_deactivation_invalidates_existing_client_tokens(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="token_invalidation_admin",
            email="token-invalidation-admin@example.com",
            phone="+213555000140",
        )
        client = self.create_active_user(
            username="token_invalidation_client",
            email="token-invalidation-client@example.com",
            phone="+213555000141",
        )
        login_response = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"email": client.email, "password": self.password},
            format="json",
        )
        access_token = login_response.data["accessToken"]
        refresh_token = login_response.data["refreshToken"]
        admin_token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{AUTH_BASE}/users/{client.id}/",
                {"is_active": False},
                format="json",
            )

        client.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(client.auth_token_version, 1)
        with self.assertRaises(TokenError):
            RefreshToken(refresh_token).check_blacklist()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        me_response = self.client.get(f"{AUTH_BASE}/me/")
        self.assertEqual(me_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(me_response["Content-Type"], "application/json")
        self.assertEqual(me_response.data["code"], "account_inactive")

    def test_admin_customer_update_error_responses_are_json(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="customer_errors_admin",
            email="customer-errors-admin@example.com",
            phone="+213555000142",
        )
        client = self.create_active_user(
            username="customer_errors_client",
            email="customer-errors-client@example.com",
            phone="+213555000143",
        )
        client_token = RefreshToken.for_user(client).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {client_token}")

        forbidden_response = self.client.patch(
            f"{AUTH_BASE}/users/{admin.id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(forbidden_response["Content-Type"], "application/json")

        admin_token = RefreshToken.for_user(admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        invalid_response = self.client.patch(
            f"{AUTH_BASE}/users/{client.id}/",
            {"is_active": "not-a-boolean"},
            format="json",
        )
        missing_response = self.client.patch(
            f"{AUTH_BASE}/users/999999/",
            {"is_active": False},
            format="json",
        )

        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_response["Content-Type"], "application/json")
        self.assertEqual(missing_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing_response["Content-Type"], "application/json")

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

    def test_admin_can_create_representative_with_service_city_and_optional_area(self):
        city = ServiceCity.objects.create(name="Courier City")
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="courier_city_admin",
            email="courier-city-admin@example.com",
            phone="+213555000046",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "City",
                "last_name": "Courier",
                "username": "service_city_courier",
                "email": "service-city-courier@example.com",
                "phone": "+213555000047",
                "password": self.password,
                "role": User.Role.REPRESENTATIVE,
                "is_active": True,
                "courier_profile": {
                    "vehicle_type": "Motorcycle",
                    "plate_number": "CITY-1",
                    "service_city": city.id,
                    "delivery_area": None,
                    "max_active_orders": 2,
                    "is_available": False,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = CourierProfile.objects.get(user_id=response.data["id"])
        self.assertEqual(profile.service_city_id, city.id)
        self.assertIsNone(profile.delivery_area_id)
        self.assertFalse(profile.is_available)

    def test_admin_can_update_courier_availability_without_resending_service_city(self):
        city = ServiceCity.objects.create(name="Inactive courier city")
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="availability_only_courier",
            email="availability-only-courier@example.com",
            phone="+213555000128",
        )
        CourierProfile.objects.create(
            user=representative,
            vehicle_type="Motorcycle",
            plate_number="ABC 128",
            service_city=city,
            max_active_orders=3,
            is_available=True,
        )
        city.is_active = False
        city.save(update_fields=["is_active"])
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="availability_only_admin",
            email="availability-only-admin@example.com",
            phone="+213555000129",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/users/{representative.id}/",
            {"courier_profile": {"is_available": False}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["courier_profile"]["is_available"])
        self.assertEqual(response.data["courier_profile"]["service_city"], city.id)

    def test_admin_representative_area_payload_is_ignored_and_cleared(self):
        city = ServiceCity.objects.create(name="Courier City A")
        other_city = ServiceCity.objects.create(name="Courier City B")
        other_area = DeliveryArea.objects.create(
            service_city=other_city,
            name="Other Area",
            delivery_price="15.00",
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="courier_mismatch_admin",
            email="courier-mismatch-admin@example.com",
            phone="+213555000048",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "Bad",
                "last_name": "Courier",
                "username": "mismatch_courier",
                "email": "mismatch-courier@example.com",
                "phone": "+213555000049",
                "password": self.password,
                "role": User.Role.REPRESENTATIVE,
                "is_active": True,
                "courier_profile": {
                    "vehicle_type": "Motorcycle",
                    "plate_number": "BAD-1",
                    "service_city": city.id,
                    "delivery_area": other_area.id,
                    "max_active_orders": 2,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = CourierProfile.objects.get(user_id=response.data["id"])
        self.assertEqual(profile.service_city_id, city.id)
        self.assertIsNone(profile.delivery_area_id)

    def test_admin_update_preserves_availability_and_hashes_password(self):
        city = ServiceCity.objects.create(name="Courier Edit City")
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="availability_courier",
            email="availability-courier@example.com",
            phone="+213555000050",
        )
        CourierProfile.objects.create(
            user=representative,
            vehicle_type="Motorcycle",
            plate_number="AVL-1",
            service_city=city,
            is_available=False,
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="availability_admin",
            email="availability-admin@example.com",
            phone="+213555000051",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/users/{representative.id}/",
            {"first_name": "Updated", "password": "NewPassword1!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        representative.refresh_from_db()
        representative.courier_profile.refresh_from_db()
        self.assertFalse(representative.courier_profile.is_available)
        self.assertTrue(representative.check_password("NewPassword1!"))

    def test_admin_update_keeps_delivery_area_null_and_preserves_active_flags(self):
        city = ServiceCity.objects.create(name="Null Area City")
        area = DeliveryArea.objects.create(
            service_city=city,
            name="Legacy Area",
            delivery_price=Decimal("15.00"),
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="null_area_courier",
            email="null-area-courier@example.com",
            phone="+213555000052",
        )
        CourierProfile.objects.create(
            user=representative,
            vehicle_type="Motorcycle",
            plate_number="NULL-1",
            service_city=city,
            delivery_area=area,
            is_available=False,
        )
        representative.is_active = False
        representative.save(update_fields=["is_active"])
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="null_area_admin",
            email="null-area-admin@example.com",
            phone="+213555000053",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/users/{representative.id}/",
            {
                "first_name": "Still Disabled",
                "courier_profile": {
                    "service_city": city.id,
                    "vehicle_type": "Motorcycle",
                    "plate_number": "NULL-2",
                    "delivery_area": area.id,
                    "is_available": False,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        representative.refresh_from_db()
        representative.courier_profile.refresh_from_db()
        self.assertFalse(representative.is_active)
        self.assertFalse(representative.courier_profile.is_available)
        self.assertIsNone(representative.courier_profile.delivery_area_id)

    def test_admin_update_rejects_same_password_and_accepts_different_password(self):
        user = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="same_password_user",
            email="same-password-user@example.com",
            phone="+213555000054",
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="same_password_admin",
            email="same-password-admin@example.com",
            phone="+213555000055",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        same_response = self.client.patch(
            f"{AUTH_BASE}/users/{user.id}/",
            {"password": self.password},
            format="json",
        )
        different_response = self.client.patch(
            f"{AUTH_BASE}/users/{user.id}/",
            {"password": "DifferentPassword1!"},
            format="json",
        )

        self.assertEqual(same_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", same_response.data)
        self.assertIn(
            "كلمة المرور الجديدة يجب أن تكون مختلفة عن كلمة المرور الحالية.",
            same_response.data["password"],
        )
        self.assertEqual(different_response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertNotEqual(user.password, "DifferentPassword1!")
        self.assertTrue(user.check_password("DifferentPassword1!"))

    def test_admin_username_trims_outer_spaces_and_rejects_internal_spaces(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="username_space_admin",
            email="username-space-admin@example.com",
            phone="+213555000056",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        create_response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "Trim",
                "last_name": "User",
                "username": " trimmed_user ",
                "email": "trimmed-user@example.com",
                "phone": "+213555000057",
                "password": self.password,
                "role": User.Role.CLIENT,
            },
            format="json",
        )
        internal_response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "Bad",
                "last_name": "User",
                "username": "bad user",
                "email": "bad-internal-user@example.com",
                "phone": "+213555000058",
                "password": self.password,
                "role": User.Role.CLIENT,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(pk=create_response.data["id"]).username, "trimmed_user")
        self.assertEqual(internal_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", internal_response.data)

    def test_admin_availability_checks_can_exclude_current_user(self):
        user = self.create_active_user(
            username="availability_check_user",
            email="availability-check@example.com",
            phone="+213555000059",
        )
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="availability_check_admin",
            email="availability-check-admin@example.com",
            phone="+213555000060",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        username_response = self.client.get(
            f"{AUTH_BASE}/check-username/",
            {"username": user.username, "exclude_user_id": user.id},
        )
        email_response = self.client.get(
            f"{AUTH_BASE}/check-email/",
            {"email": user.email, "exclude_user_id": user.id},
        )
        phone_response = self.client.get(
            f"{AUTH_BASE}/check-phone/",
            {"phone": user.phone, "exclude_user_id": user.id},
        )

        self.assertTrue(username_response.data["available"])
        self.assertTrue(email_response.data["available"])
        self.assertTrue(phone_response.data["available"])

    def test_representative_delete_uses_non_terminal_assigned_order_rule(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="delete_rule_admin",
            email="delete-rule-admin@example.com",
            phone="+213555000061",
        )
        customer = self.create_active_user(
            username="delete_rule_customer",
            email="delete-rule-customer@example.com",
            phone="+213555000062",
        )
        market = self.create_order_market()
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        for index, order_status in enumerate((
            Order.Status.ASSIGNED,
            Order.Status.PICKED_UP,
        ), start=1):
            representative = self.create_active_user(
                role=User.Role.REPRESENTATIVE,
                username=f"blocked_{order_status}",
                email=f"blocked-{order_status}@example.com",
                phone=f"+2135551{index:05d}",
            )
            order = self.create_customer_order(
                customer,
                market,
                order_status,
                Decimal("10.00"),
                timezone.now(),
            )
            order.assigned_representative = representative
            order.save(update_fields=["assigned_representative"])

            response = self.client.delete(f"{AUTH_BASE}/users/{representative.id}/")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(
                response.data["detail"],
                "Reassign active orders before deleting this courier.",
            )

        for index, order_status in enumerate((
            Order.Status.DELIVERED,
            Order.Status.CANCELLED,
            Order.Status.FAILED_DELIVERY,
        ), start=1):
            representative = self.create_active_user(
                role=User.Role.REPRESENTATIVE,
                username=f"allowed_{order_status}",
                email=f"allowed-{order_status}@example.com",
                phone=f"+2135552{index:05d}",
            )
            order = self.create_customer_order(
                customer,
                market,
                order_status,
                Decimal("10.00"),
                timezone.now(),
            )
            order.assigned_representative = representative
            order.save(update_fields=["assigned_representative"])

            response = self.client.delete(f"{AUTH_BASE}/users/{representative.id}/")
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_clear_courier_delivery_areas_migration_behavior(self):
        city = ServiceCity.objects.create(name="Migration City")
        area = DeliveryArea.objects.create(
            service_city=city,
            name="Migration Area",
            delivery_price=Decimal("15.00"),
        )
        representative = self.create_active_user(
            role=User.Role.REPRESENTATIVE,
            username="migration_courier",
            email="migration-courier@example.com",
            phone="+213555000063",
        )
        CourierProfile.objects.create(
            user=representative,
            vehicle_type="Motorcycle",
            plate_number="MIG-1",
            service_city=city,
            delivery_area=area,
        )

        migration = importlib.import_module(
            "accounts.migrations.0007_clear_courier_delivery_areas"
        )
        migration.clear_courier_delivery_areas(apps, None)

        representative.courier_profile.refresh_from_db()
        self.assertIsNone(representative.courier_profile.delivery_area_id)

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

    def test_admin_cannot_patch_own_email_through_me(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="own_email_admin",
            email="own-email-admin@example.com",
            phone="+213555000077",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/me",
            {"email": "changed-admin@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["email"],
            ["لا يمكن تغيير بريد حساب المدير من لوحة التحكم."],
        )

    def test_admin_can_patch_own_first_and_last_name(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="own_name_admin",
            email="own-name-admin@example.com",
            phone="+213555000078",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.patch(
            f"{AUTH_BASE}/me",
            {"first_name": "Updated", "last_name": "Administrator"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Updated")
        self.assertEqual(response.data["last_name"], "Administrator")

    def test_rejected_admin_email_change_keeps_original_email(self):
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="unchanged_email_admin",
            email="unchanged-email-admin@example.com",
            phone="+213555000079",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        self.client.patch(
            f"{AUTH_BASE}/me",
            {"email": "new-admin@example.com"},
            format="json",
        )

        admin.refresh_from_db()
        self.assertEqual(admin.email, "unchanged-email-admin@example.com")

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

    def test_availability_checks_normalize_phone_variants(self):
        self.create_active_user(phone="+201016787371")

        response = self.client.get(
            f"{AUTH_BASE}/check-phone",
            {"phone": "01016787371"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["available"])
        self.assertTrue(response.data["registered"])

    def test_admin_availability_exclude_user_id_allows_current_values(self):
        user = self.create_active_user(phone="+201016787371")
        admin = self.create_active_user(
            role=User.Role.ADMIN,
            username="availability_admin",
            email="availability-admin@example.com",
            phone="+201000000091",
        )
        refresh = RefreshToken.for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        username_response = self.client.get(
            f"{AUTH_BASE}/check-username",
            {"username": user.username, "exclude_user_id": user.id},
        )
        email_response = self.client.get(
            f"{AUTH_BASE}/check-email",
            {"email": user.email.upper(), "exclude_user_id": user.id},
        )
        phone_response = self.client.get(
            f"{AUTH_BASE}/check-phone",
            {"phone": "01016787371", "exclude_user_id": user.id},
        )

        self.assertTrue(username_response.data["available"])
        self.assertFalse(username_response.data["registered"])
        self.assertTrue(email_response.data["available"])
        self.assertFalse(email_response.data["registered"])
        self.assertTrue(phone_response.data["available"])
        self.assertFalse(phone_response.data["registered"])

    def test_non_admin_availability_exclude_user_id_is_ignored(self):
        user = self.create_active_user(phone="+201016787371")
        other_user = self.create_active_user(
            username="availability_other",
            email="availability-other@example.com",
            phone="+201000000092",
        )
        refresh = RefreshToken.for_user(other_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(
            f"{AUTH_BASE}/check-email",
            {"email": user.email, "exclude_user_id": user.id},
        )

        self.assertFalse(response.data["available"])
        self.assertTrue(response.data["registered"])

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

    @override_settings(AUTH_OTP_INCLUDE_IN_RESPONSE=False)
    def test_forgot_password_response_does_not_include_dev_otp_by_default(self):
        user = self.create_active_user()

        response = self.client.post(
            f"{AUTH_BASE}/forgot-password", {"email": user.email}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("dev_otp", response.data)
        self.assertEqual(response.data["resend_after_seconds"], 30)

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
