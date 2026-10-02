from decimal import Decimal
from datetime import timedelta

from django.utils import timezone

from rest_framework.test import APITestCase

from .models import Order
from . import tests as order_test_fixtures


class AdminOrderPaginationTests(APITestCase):
    def setUp(self):
        order_test_fixtures.OrderAPITests.setUp(self)
        self.client.force_authenticate(self.admin)

    def order(self, status, *, representative=None, destination="old destination"):
        return Order.objects.create(
            user=self.customer,
            market=self.market,
            status=status,
            assigned_representative=representative,
            payment_method="cash",
            delivery_type=Order.DeliveryType.FIXED_AREA,
            delivery_address=self.address,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            order_scope=Order.Scope.SERVICE_CITY,
            fulfillment_type=Order.FulfillmentType.DIRECT,
            external_shipping_status=Order.ExternalShippingStatus.NOT_REQUIRED,
            total_price=Decimal("100.00"),
            delivery_price=Decimal("20.00"),
            delivery_address_snapshot={"details": destination},
        )

    def test_page_count_and_metrics_include_rows_outside_current_page(self):
        self.order(Order.Status.CONFIRMED)
        self.order(Order.Status.ASSIGNED, representative=self.representative)
        self.order(Order.Status.DELIVERED, representative=self.representative)
        response = self.client.get(
            "/api/v1/orders/", {"page": 1, "page_size": 1, "include_courier_summary": 1}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(
            response.data["metrics"],
            {"total": 3, "assignmentReady": 1, "assigned": 1, "delivered": 1},
        )
        self.assertEqual(
            response.data["courier_summary"],
            [
                {
                    "assigned_representative_id": self.representative.id,
                    "active": 1,
                    "delivered": 1,
                    "total": 2,
                    "delivered_total": "100.00",
                }
            ],
        )
        self.assertEqual(response.data["summary"]["total_value"], "300.00")

    def test_history_filter_search_and_totals_are_server_side(self):
        wanted = self.order(
            Order.Status.DELIVERED,
            representative=self.representative,
            destination="frozen street",
        )
        self.order(
            Order.Status.ASSIGNED,
            representative=self.representative,
            destination="frozen street",
        )
        self.order(
            Order.Status.DELIVERED,
            representative=self.representative,
            destination="different street",
        )
        response = self.client.get(
            "/api/v1/orders/",
            {
                "page": 1,
                "page_size": 1,
                "scope": "history",
                "representative_id": self.representative.id,
                "search": "frozen",
                "delivery_type": "fixed_area",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], wanted.id)
        self.assertEqual(
            response.data["summary"],
            {"count": 1, "total_value": "100.00", "total_delivery_fees": "20.00"},
        )

    def test_invalid_filters_return_400_and_non_admin_cannot_read(self):
        for filters in (
            {"scope": "invalid"},
            {"representative_id": "invalid"},
            {"delivery_type": "invalid"},
            {"search": "x" * 201},
        ):
            with self.subTest(filters=filters):
                self.assertEqual(
                    self.client.get(
                        "/api/v1/orders/", {"page": 1, **filters}
                    ).status_code,
                    400,
                )
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.get("/api/v1/orders/", {"page": 1}).status_code, 403
        )

    def test_latest_delivered_uses_delivery_time_not_order_creation(self):
        delivered_later = self.order(
            Order.Status.DELIVERED, representative=self.representative
        )
        created_later = self.order(
            Order.Status.DELIVERED, representative=self.representative
        )
        # Historical delivered records may not have a delivery timestamp.
        self.order(Order.Status.DELIVERED, representative=self.representative)
        Order.objects.filter(pk=delivered_later.pk).update(delivered_at=timezone.now())
        Order.objects.filter(pk=created_later.pk).update(
            delivered_at=timezone.now() - timedelta(days=1)
        )
        response = self.client.get(
            "/api/v1/orders/",
            {
                "page": 1,
                "page_size": 1,
                "ordering": "-delivered_at",
                "status": "delivered",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], delivered_later.id)

    def test_legacy_shape_still_returns_array_and_active_excludes_history(self):
        active = self.order(Order.Status.ASSIGNED, representative=self.representative)
        self.order(Order.Status.DELIVERED, representative=self.representative)
        response = self.client.get("/api/v1/orders/", {"scope": "active"})
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual([row["id"] for row in response.data], [active.id])
