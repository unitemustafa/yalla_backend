from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import CategoryClassification, Product, ProductCategory, ProductVariant
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from offers.models import Offer
from orders.models import Order

from .models import ClientDevice, Notification
from .services import create_new_order_review_notification
from .courier_services import (
    notify_courier_order_assigned,
    notify_courier_order_cancelled,
    notify_courier_order_unassigned,
)

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
        self.city = city
        self.delivery_area = DeliveryArea.objects.create(
            service_city=city,
            name="Notification Area",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("5.00"),
            delivery_price=Decimal("25.00"),
        )
        self.address = Address.objects.create(
            user=self.customer,
            name="Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0420000"),
            service_city=city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )
        self.customer.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        self.customer.market_region_service_city = city
        self.customer.market_region_updated_at = timezone.now()
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        classification = MarketClassification.objects.create(name="Notifications")
        self.market = Market.objects.create(
            classification=classification,
            name="Notification Market",
        )
        self.market.service_cities.add(city)
        self.market.delivery_areas.add(self.delivery_area)
        category_classification = CategoryClassification.objects.create(
            name="Notification Products",
        )
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Main",
        )
        product = Product.objects.create(
            market=self.market,
            category=category,
            name="Notification Product",
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100.00"),
            sku="NOTIFY-1",
        )
        self.order = Order.objects.create(
            user=self.customer,
            market=self.market,
            service_city=city,
            payment_method="cash",
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

    def test_client_device_registration_refresh_and_unregister_are_idempotent(self):
        self.authenticate(self.customer)
        payload = {"token": "fcm-token-1", "platform": "android"}

        first = self.client.post(
            "/api/v1/notifications/devices/register/",
            payload,
            format="json",
        )
        second = self.client.post(
            "/api/v1/notifications/devices/register/",
            payload,
            format="json",
        )
        removed = self.client.delete(
            "/api/v1/notifications/devices/unregister/",
            payload,
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ClientDevice.objects.filter(token="fcm-token-1").count(), 1)
        self.assertFalse(ClientDevice.objects.get(token="fcm-token-1").is_active)

    def test_courier_device_registration_is_authenticated_and_moves_ownership(self):
        payload = {"token": "shared-courier-token", "platform": "android"}
        self.authenticate(self.customer)
        self.client.post(
            "/api/v1/notifications/devices/register/", payload, format="json"
        )

        self.authenticate(self.courier)
        response = self.client.post(
            "/api/v1/notifications/devices/register/", payload, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        device = ClientDevice.objects.get(token=payload["token"])
        self.assertEqual(device.user, self.courier)
        self.assertEqual(ClientDevice.objects.filter(token=payload["token"]).count(), 1)

    @patch("notifications.services._dispatch_courier_notification")
    def test_courier_order_events_create_one_db_notification_and_dispatch_after_commit(
        self, dispatch
    ):
        with self.captureOnCommitCallbacks(execute=True):
            assigned = notify_courier_order_assigned(self.order, self.courier)
        self.assertEqual(assigned.data["event"], "courier_order_assigned")
        dispatch.assert_called_once_with(assigned.id)

        dispatch.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            unassigned = notify_courier_order_unassigned(self.order, self.courier)
            cancelled = notify_courier_order_cancelled(self.order, self.courier)
        self.assertEqual(unassigned.data["event"], "courier_order_unassigned")
        self.assertEqual(cancelled.data["event"], "courier_order_cancelled")
        self.assertEqual(dispatch.call_count, 2)

    @patch("notifications.services._dispatch_courier_notification")
    def test_rolled_back_courier_notification_does_not_dispatch(self, dispatch):
        from django.db import transaction

        try:
            with transaction.atomic():
                notify_courier_order_assigned(self.order, self.courier)
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        dispatch.assert_not_called()
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.courier,
                data__event="courier_order_assigned",
            ).exists()
        )

    def create_client_order_requiring_review(self):
        self.authenticate(self.customer)
        response = self.client.post(
            "/api/v1/orders/create/",
            {
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Order.objects.get(pk=response.data[0]["id"])

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

    def test_admin_only_sees_new_orders_and_courier_pickup_or_delivery(self):
        hidden_notification = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.COURIER_AVAILABILITY_CHANGED,
            title="Hidden courier availability",
            message="This must not appear in the dashboard feed.",
        )
        for event_name, status_value in (
            ("courier_order_picked_up", Order.Status.PICKED_UP),
            ("courier_order_delivered", Order.Status.DELIVERED),
        ):
            Notification.objects.create(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.ORDER_STATUS_CHANGED,
                title=event_name,
                message=event_name,
                order=self.order,
                data={"event": event_name, "status": status_value},
            )
        self.authenticate(self.admin)

        list_response = self.client.get("/api/v1/notifications/")
        count_response = self.client.get("/api/v1/notifications/unread-count/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["type"] for item in list_response.data},
            {
                Notification.Type.NEW_ORDER_REVIEW,
                Notification.Type.ORDER_STATUS_CHANGED,
            },
        )
        self.assertEqual(
            {
                item["data"].get("event")
                for item in list_response.data
                if item["type"] == Notification.Type.ORDER_STATUS_CHANGED
            },
            {"courier_order_picked_up", "courier_order_delivered"},
        )
        self.assertEqual(count_response.data["unread_count"], 3)
        self.assertTrue(Notification.objects.filter(pk=hidden_notification.pk).exists())

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

    def test_client_notification_serializes_offer_without_market(self):
        now = timezone.now()
        offer = Offer.objects.create(
            market=None,
            show_in_general=True,
            title="Legacy Offer",
            description="Offer whose market was removed",
            type=Offer.OfferType.DISCOUNT,
            discount=Decimal("15.00"),
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            status=Offer.Status.ACTIVE,
        )
        notification = Notification.objects.create(
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.OFFER_CREATED,
            title="Legacy offer",
            message="Legacy offer notification",
            offer=offer,
            recipient=self.customer,
        )
        self.authenticate(self.customer)

        response = self.client.get("/api/v1/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(item for item in response.data if item["id"] == notification.id)
        self.assertEqual(item["offer"]["id"], offer.id)
        self.assertIsNone(item["offer"]["market_id"])
        self.assertEqual(item["offer"]["market_name"], "")

    def test_client_notification_without_offer_serializes_offer_as_null(self):
        notification = Notification.objects.create(
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.OFFER_CREATED,
            title="Unavailable offer",
            message="The linked offer is no longer available",
            offer=None,
            recipient=self.customer,
        )
        self.authenticate(self.customer)

        response = self.client.get("/api/v1/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(item for item in response.data if item["id"] == notification.id)
        self.assertIsNone(item["offer_id"])
        self.assertIsNone(item["offer"])

    def test_mark_all_read_marks_visible_notifications(self):
        self.authenticate(self.courier)

        response = self.client.post("/api/v1/notifications/mark-all-read/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["marked_read"], 1)
        self.courier_notification.refresh_from_db()
        self.admin_notification.refresh_from_db()
        self.assertTrue(self.courier_notification.is_read)
        self.assertFalse(self.admin_notification.is_read)

    def test_order_review_workflow_creates_single_blocking_notification(self):
        order = self.create_client_order_requiring_review()

        notification = Notification.objects.get(
            order=order,
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
        )
        self.assertTrue(notification.is_blocking)
        self.assertFalse(notification.is_resolved)
        self.assertFalse(notification.is_read)
        self.assertEqual(order.review_status, Order.ReviewStatus.PENDING_REVIEW)

        create_new_order_review_notification(order)

        unresolved_count = Notification.objects.filter(
            order=order,
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
            is_blocking=True,
            is_resolved=False,
        ).count()
        self.assertEqual(unresolved_count, 1)

    def test_unresolved_order_review_notification_blocks_delete_until_approval(self):
        order = self.create_client_order_requiring_review()
        notification = Notification.objects.get(
            order=order,
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
        )
        self.authenticate(self.admin)

        blocked_delete = self.client.delete(f"/api/v1/notifications/{notification.id}/")
        notification.refresh_from_db()

        self.assertEqual(blocked_delete.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            blocked_delete.data["detail"],
            "Unresolved blocking notifications cannot be deleted.",
        )
        self.assertFalse(notification.is_resolved)
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

        approval_response = self.client.post(
            f"/api/v1/admin/orders/{order.id}/approve/",
            format="json",
        )
        self.assertEqual(approval_response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        notification.refresh_from_db()
        self.assertEqual(order.review_status, Order.ReviewStatus.APPROVED)
        self.assertNotEqual(order.status, Order.Status.PENDING)
        self.assertTrue(notification.is_resolved)
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.resolved_at)
        self.assertIsNotNone(notification.read_at)

        allowed_delete = self.client.delete(f"/api/v1/notifications/{notification.id}/")
        self.assertEqual(allowed_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

    def test_order_rejection_resolves_review_and_keeps_client_notification(self):
        order = self.create_client_order_requiring_review()
        review_notification = Notification.objects.get(
            order=order,
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
        )
        self.authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            reject_response = self.client.post(
                f"/api/v1/admin/orders/{order.id}/reject/",
                {"rejection_reason": "Out of stock"},
                format="json",
            )

        self.assertEqual(reject_response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        review_notification.refresh_from_db()
        self.assertEqual(order.review_status, Order.ReviewStatus.REJECTED)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertTrue(review_notification.is_resolved)
        self.assertTrue(review_notification.is_read)
        self.assertIsNotNone(review_notification.resolved_at)
        self.assertIsNotNone(review_notification.read_at)
        self.assertTrue(
            Notification.objects.filter(
                order=order,
                audience=Notification.Audience.CLIENT,
                type=Notification.Type.ORDER_REJECTED,
                recipient=self.customer,
                is_blocking=False,
                is_read=False,
            ).exists()
        )

        delete_response = self.client.delete(
            f"/api/v1/notifications/{review_notification.id}/",
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_order_cancellation_resolves_review_notification(self):
        order = self.create_client_order_requiring_review()
        notification = Notification.objects.get(
            order=order,
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
        )
        self.authenticate(self.admin)

        cancel_response = self.client.delete(f"/api/v1/orders/{order.id}/")

        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        notification.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertTrue(notification.is_resolved)
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.resolved_at)
        self.assertIsNotNone(notification.read_at)
        delete_response = self.client.delete(f"/api/v1/notifications/{notification.id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_unauthenticated_delete_is_rejected(self):
        self.client.credentials()

        response = self.client.delete(f"/api/v1/notifications/{self.admin_notification.id}/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_visible_normal_notification_can_be_deleted(self):
        normal_notification = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.ORDER_STATUS_CHANGED,
            title="Normal",
            message="Normal visible notification",
            order=self.order,
            is_read=True,
            data={"event": "courier_order_picked_up"},
        )
        self.authenticate(self.admin)

        response = self.client.delete(f"/api/v1/notifications/{normal_notification.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=normal_notification.pk).exists())

    def test_non_visible_or_other_recipient_notification_returns_404(self):
        self.authenticate(self.customer)

        admin_response = self.client.delete(
            f"/api/v1/notifications/{self.admin_notification.id}/",
        )
        other_user_response = self.client.delete(
            f"/api/v1/notifications/{self.courier_notification.id}/",
        )
        missing_response = self.client.delete("/api/v1/notifications/999999/")

        self.assertEqual(admin_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(other_user_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unresolved_blocking_notification_cannot_be_deleted(self):
        self.authenticate(self.admin)

        response = self.client.delete(f"/api/v1/notifications/{self.admin_notification.id}/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Notification.objects.filter(pk=self.admin_notification.pk).exists())

    def test_resolved_blocking_notification_can_be_deleted(self):
        self.admin_notification.is_read = True
        self.admin_notification.is_resolved = True
        self.admin_notification.read_at = timezone.now()
        self.admin_notification.resolved_at = timezone.now()
        self.admin_notification.save()
        self.authenticate(self.admin)

        response = self.client.delete(f"/api/v1/notifications/{self.admin_notification.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=self.admin_notification.pk).exists())

    def test_clear_read_deletes_only_eligible_visible_notifications(self):
        visible_read_normal = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.ORDER_STATUS_CHANGED,
            title="Read normal",
            message="Read normal",
            order=self.order,
            is_read=True,
            data={"event": "courier_order_delivered"},
        )
        visible_unread = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.ORDER_STATUS_CHANGED,
            title="Unread",
            message="Unread",
            order=self.order,
            is_read=False,
            data={"event": "courier_order_picked_up"},
        )
        visible_resolved_blocking = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
            title="Resolved blocking",
            message="Resolved blocking",
            order=self.order,
            is_blocking=True,
            is_resolved=True,
            is_read=True,
            read_at=timezone.now(),
            resolved_at=timezone.now(),
        )
        visible_unresolved_blocking = Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.NEW_ORDER_REVIEW,
            title="Unresolved blocking",
            message="Unresolved blocking",
            order=self.order,
            is_blocking=True,
            is_resolved=False,
            is_read=True,
        )
        other_audience = Notification.objects.create(
            audience=Notification.Audience.COURIER,
            type=Notification.Type.ORDER_ASSIGNED,
            title="Courier read",
            message="Courier read",
            order=self.order,
            recipient=self.courier,
            is_read=True,
        )
        self.authenticate(self.admin)

        response = self.client.delete("/api/v1/notifications/clear-read/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 2)
        self.assertFalse(Notification.objects.filter(pk=visible_read_normal.pk).exists())
        self.assertFalse(
            Notification.objects.filter(pk=visible_resolved_blocking.pk).exists()
        )
        self.assertTrue(Notification.objects.filter(pk=visible_unread.pk).exists())
        self.assertTrue(
            Notification.objects.filter(pk=visible_unresolved_blocking.pk).exists()
        )
        self.assertTrue(Notification.objects.filter(pk=other_audience.pk).exists())
