from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from locations.models import ServiceCity
from markets.models import Market, MarketClassification
from orders.models import Order

from .models import Notification

User = get_user_model()


class NotificationAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="notification-admin",
            email="notification-admin@example.com",
            phone="+213555800001",
            password="Password1!",
            role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(
            username="notification-customer",
            email="notification-customer@example.com",
            phone="+213555800002",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        self.courier = User.objects.create_user(
            username="notification-courier",
            email="notification-courier@example.com",
            phone="+213555800003",
            password="Password1!",
            role=User.Role.REPRESENTATIVE,
        )
        city = ServiceCity.objects.create(
            name="Notification City",
            delivery_price=Decimal("25.00"),
        )
        classification = MarketClassification.objects.create(name="Notifications")
        market = Market.objects.create(
            classification=classification,
            name="Notification Market",
        )
        market.service_cities.add(city)
        self.order = Order.objects.create(
            user=self.customer,
            market=market,
            service_city=city,
            payment_method="cash",
            delivery_price=Decimal("25.00"),
            subtotal_price=Decimal("100.00"),
            total_price=Decimal("125.00"),
        )
        self.admin_notification = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
            title="Review",
            message="Review order",
            order=self.order,
            is_blocking=True,
        )
        self.courier_notification = Notification.objects.create(
            audience=Notification.Audience.COURIER,
            type=Notification.Type.ORDER_ASSIGNED,
            title="Assigned",
            message="Assigned order",
            order=self.order,
            recipient=self.courier,
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_admin_can_filter_blocking_order_review_notifications(self):
        self.authenticate(self.admin)

        response = self.client.get(
            "/api/v1/notifications/",
            {
                "unread": "true",
                "type": Notification.Type.NEW_ORDER_REVIEW,
                "audience": Notification.Audience.ADMIN,
                "is_blocking": "true",
                "is_resolved": "false",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.admin_notification.id])
        self.assertEqual(response.data[0]["order_id"], self.order.id)

    def test_user_can_read_and_count_only_visible_notifications(self):
        self.authenticate(self.courier)

        count_response = self.client.get("/api/v1/notifications/unread-count/")
        list_response = self.client.get("/api/v1/notifications/")
        read_response = self.client.patch(
            f"/api/v1/notifications/{self.courier_notification.id}/read/"
        )
        admin_read_response = self.client.patch(
            f"/api/v1/notifications/{self.admin_notification.id}/read/"
        )
        final_count_response = self.client.get("/api/v1/notifications/unread-count/")

        self.assertEqual(count_response.data["unread_count"], 1)
        self.assertEqual([item["id"] for item in list_response.data], [self.courier_notification.id])
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertTrue(read_response.data["is_read"])
        self.assertEqual(admin_read_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(final_count_response.data["unread_count"], 0)

    def test_mark_all_read_marks_visible_notifications(self):
        self.authenticate(self.courier)

        response = self.client.post("/api/v1/notifications/mark-all-read/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["marked_read"], 1)
        self.courier_notification.refresh_from_db()
        self.admin_notification.refresh_from_db()
        self.assertTrue(self.courier_notification.is_read)
        self.assertFalse(self.admin_notification.is_read)
