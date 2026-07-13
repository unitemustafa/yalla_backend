from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from locations.models import Address, DeliveryArea, ServiceCity
from locations.views import DeliveryAreaListCreateView

from .delivery_area_services import (
    dispatch_delivery_area_created_notifications,
    schedule_delivery_area_created_notifications,
)
from .models import (
    ClientDevice,
    DeliveryAreaNotificationDispatch,
    Notification,
)


User = get_user_model()


class DeliveryAreaCreatedNotificationTests(APITestCase):
    endpoint = "/api/v1/locations/delivery-areas/"

    def setUp(self):
        self.admin = self.create_user("admin", User.Role.ADMIN)
        self.city = ServiceCity.objects.create(
            name="القاهرة",
            delivery_price=Decimal("30.00"),
        )
        self.other_city = ServiceCity.objects.create(
            name="الجيزة",
            delivery_price=Decimal("35.00"),
        )
        self.client.force_authenticate(self.admin)

    def create_user(self, suffix, role=User.Role.CLIENT, **extra):
        sequence = User.objects.count() + 1
        return User.objects.create_user(
            username=f"area-notification-{suffix}-{sequence}",
            email=f"area-notification-{suffix}-{sequence}@example.com",
            phone=f"+2011{sequence:08d}",
            password="Password1!",
            role=role,
            **extra,
        )

    def add_address(self, user, city=None, *, is_active=True, suffix="home"):
        return Address.objects.create(
            user=user,
            name=f"{suffix}-{user.id}",
            details="Test address",
            service_city=city or self.city,
            delivery_type=Address.DeliveryType.DELIVERY,
            is_active=is_active,
        )

    def post_area(self, *, name="المعادي", fee="25.00", execute=True):
        with (
            patch(
                "notifications.delivery_area_services.send_notification_push"
            ) as push,
            self.captureOnCommitCallbacks(execute=execute),
        ):
            response = self.client.post(
                self.endpoint,
                {
                    "service_city_id": self.city.id,
                    "name": name,
                    "delivery_price": fee,
                    "is_active": True,
                },
                format="json",
            )
        return response, push

    def area_notifications(self):
        return Notification.objects.filter(
            type=Notification.Type.DELIVERY_AREA_CREATED
        )

    def test_admin_endpoint_notifies_client_with_active_address_in_same_city(self):
        customer = self.create_user("eligible")
        self.add_address(customer)

        response, push = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        notification = self.area_notifications().get()
        self.assertEqual(notification.recipient, customer)
        push.assert_called_once_with(notification.id)

    def test_client_with_address_in_another_city_is_not_notified(self):
        customer = self.create_user("other-city")
        self.add_address(customer, self.other_city)

        response, push = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.area_notifications().exists())
        push.assert_not_called()

    def test_inactive_client_is_not_notified(self):
        customer = self.create_user("inactive", is_active=False)
        self.add_address(customer)

        response, _ = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.area_notifications().exists())

    def test_soft_deleted_client_is_not_notified(self):
        customer = self.create_user("deleted")
        customer.deleted_at = timezone.now()
        customer.save(update_fields=["deleted_at"])
        self.add_address(customer)

        response, _ = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.area_notifications().exists())

    def test_inactive_address_does_not_qualify_client(self):
        customer = self.create_user("inactive-address")
        self.add_address(customer, is_active=False)

        response, _ = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.area_notifications().exists())

    def test_client_without_address_is_not_notified(self):
        self.create_user("no-address")

        response, _ = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.area_notifications().exists())

    def test_multiple_addresses_in_city_create_one_notification(self):
        customer = self.create_user("multiple-addresses")
        self.add_address(customer, suffix="home")
        self.add_address(customer, suffix="work")

        response, push = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.area_notifications().filter(recipient=customer).count(), 1)
        self.assertEqual(push.call_count, 1)

    def test_each_eligible_client_gets_one_notification(self):
        first = self.create_user("first")
        second = self.create_user("second")
        self.add_address(first)
        self.add_address(second)

        response, push = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            set(self.area_notifications().values_list("recipient_id", flat=True)),
            {first.id, second.id},
        )
        self.assertEqual(push.call_count, 2)

    def test_admin_courier_and_staff_accounts_are_not_notified(self):
        courier = self.create_user("courier", User.Role.REPRESENTATIVE)
        staff_client = self.create_user("staff-client", is_staff=True)
        self.add_address(self.admin)
        self.add_address(courier)
        self.add_address(staff_client)

        response, _ = self.post_area()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.area_notifications().exists())

    def test_name_update_does_not_create_notification(self):
        customer = self.create_user("name-update")
        self.add_address(customer)
        area = DeliveryArea.objects.create(
            service_city=self.city,
            name="اسم قديم",
            delivery_price=Decimal("20.00"),
        )

        with patch(
            "notifications.delivery_area_services.send_notification_push"
        ) as push:
            response = self.client.patch(
                f"{self.endpoint}{area.id}/",
                {"name": "اسم جديد"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.area_notifications().exists())
        push.assert_not_called()

    def test_price_update_does_not_create_notification(self):
        customer = self.create_user("price-update")
        self.add_address(customer)
        area = DeliveryArea.objects.create(
            service_city=self.city,
            name="منطقة السعر",
            delivery_price=Decimal("20.00"),
        )

        response = self.client.patch(
            f"{self.endpoint}{area.id}/",
            {"delivery_price": "40.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.area_notifications().exists())

    def test_activation_update_does_not_create_notification(self):
        customer = self.create_user("activation-update")
        self.add_address(customer)
        area = DeliveryArea.objects.create(
            service_city=self.city,
            name="منطقة الحالة",
            delivery_price=Decimal("20.00"),
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{self.endpoint}{area.id}/",
                {"is_active": False},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.area_notifications().exists())

    def test_endpoint_rollback_creates_neither_area_nor_notification(self):
        customer = self.create_user("rollback")
        self.add_address(customer)

        def fail_after_scheduling(view, serializer):
            area = serializer.save()
            schedule_delivery_area_created_notifications(area.id)
            raise RuntimeError("force rollback")

        with (
            patch.object(
                DeliveryAreaListCreateView,
                "perform_create",
                fail_after_scheduling,
            ),
            patch(
                "notifications.delivery_area_services._dispatch_after_commit"
            ) as dispatch,
            self.assertRaisesRegex(RuntimeError, "force rollback"),
        ):
            self.client.post(
                self.endpoint,
                {
                    "service_city_id": self.city.id,
                    "name": "منطقة مرتجعة",
                    "delivery_price": "25.00",
                },
                format="json",
            )

        self.assertFalse(DeliveryArea.objects.filter(name="منطقة مرتجعة").exists())
        self.assertFalse(self.area_notifications().exists())
        dispatch.assert_not_called()

    def test_retry_does_not_duplicate_campaign_notification_or_push(self):
        customer = self.create_user("retry")
        self.add_address(customer)
        response, initial_push = self.post_area()
        area_id = response.data["id"]
        initial_push.assert_called_once()

        with patch(
            "notifications.delivery_area_services.send_notification_push"
        ) as retry_push:
            first = dispatch_delivery_area_created_notifications(area_id)
            second = dispatch_delivery_area_created_notifications(area_id)

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            DeliveryAreaNotificationDispatch.objects.filter(
                delivery_area_id=area_id
            ).count(),
            1,
        )
        self.assertEqual(self.area_notifications().filter(recipient=customer).count(), 1)
        retry_push.assert_not_called()

    def test_push_failure_does_not_fail_area_creation_or_in_app_notification(self):
        customer = self.create_user("push-failure")
        self.add_address(customer)

        with (
            patch(
                "notifications.delivery_area_services.send_notification_push",
                side_effect=RuntimeError("FCM unavailable"),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                self.endpoint,
                {
                    "service_city_id": self.city.id,
                    "name": "الدقي",
                    "delivery_price": "25.00",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DeliveryArea.objects.filter(pk=response.data["id"]).exists())
        self.assertEqual(self.area_notifications().filter(recipient=customer).count(), 1)

    def test_notification_copy_and_payload_have_trimmed_fee_and_real_values(self):
        customer = self.create_user("payload")
        self.add_address(customer)

        response, _ = self.post_area(name="مدينة نصر", fee="25.50")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = self.area_notifications().get(recipient=customer)
        self.assertEqual(notification.title, "وصلنا لمنطقتك")
        self.assertEqual(
            notification.message,
            'تمت إضافة منطقة التوصيل "مدينة نصر" داخل مدينة '
            '"القاهرة". رسوم التوصيل: 25.5 جنيه.',
        )
        self.assertEqual(
            notification.data,
            {
                "event": "delivery_area_created",
                "type": "delivery_area_created",
                "delivery_area_id": response.data["id"],
                "city_id": self.city.id,
                "area_name": "مدينة نصر",
                "city_name": "القاهرة",
                "delivery_fee": "25.5",
            },
        )

    def test_push_uses_current_service_with_complete_payload(self):
        customer = self.create_user("push-payload")
        self.add_address(customer)
        ClientDevice.objects.create(
            user=customer,
            token="delivery-area-device-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )

        with (
            patch("notifications.push._send_tokens") as send_tokens,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                self.endpoint,
                {
                    "service_city_id": self.city.id,
                    "name": "حلوان",
                    "delivery_price": "25.00",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        send_tokens.assert_called_once()
        tokens, payload = send_tokens.call_args.args
        self.assertEqual(tokens, ["delivery-area-device-token"])
        self.assertEqual(payload["type"], "delivery_area_created")
        self.assertEqual(payload["event"], "delivery_area_created")
        self.assertEqual(payload["delivery_area_id"], response.data["id"])
        self.assertEqual(payload["city_id"], self.city.id)
        self.assertEqual(payload["area_name"], "حلوان")
        self.assertEqual(payload["city_name"], "القاهرة")
        self.assertEqual(payload["delivery_fee"], "25")
        self.assertEqual(send_tokens.call_args.kwargs["title"], "وصلنا لمنطقتك")
