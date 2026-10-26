from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APITestCase
from . import tests as order_tests
from .models import Order


class PagedOrderHistoryTests(APITestCase):
    setUp = order_tests.OrderAPITests.setUp

    def test_page_counts_and_dates_use_the_entire_customer_history(self):
        orders = Order.objects.bulk_create([
            Order(user=self.customer, market=self.market, service_city=self.service_city,
                delivery_area=self.delivery_area, delivery_type=Order.DeliveryType.FIXED_AREA,
                payment_method="cash_on_delivery", status=Order.Status.DELIVERED if i < 2 else Order.Status.PENDING,
                delivery_price=Decimal("0"), subtotal_price=Decimal("10"), total_price=Decimal("10"))
            for i in range(35)
        ])
        self.client.force_authenticate(self.customer)
        url = "/api/v1/orders/my/"
        response = self.client.get(url, {"page": 1, "page_size": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(response.data["count"], 35)
        self.assertEqual(response.data["delivered_count"], 2)
        focused = self.client.get(url, {"page": 1, "page_size": 1, "order_id": orders[0].id})
        self.assertEqual(focused.data["count"], 1)
        self.assertEqual(focused.data["results"][0]["id"], orders[0].id)
        self.assertEqual(self.client.get(url, {"order_id": "invalid"}).status_code, 400)
        self.client.force_authenticate(self.other_customer)
        private = self.client.get(url, {"page": 1, "order_id": orders[0].id})
        self.assertEqual(private.data["count"], 0)
        self.client.force_authenticate(self.customer)
        Order.objects.filter(id=orders[0].id).update(created_at=timezone.now()-timedelta(days=2))
        filtered = self.client.get(url, {"page": 1, "page_size": 10, "from_date": timezone.now().date().isoformat()})
        self.assertEqual(filtered.data["count"], 34)
        self.assertEqual(filtered.data["delivered_count"], 1)
        self.assertIsInstance(self.client.get(url).data, list)
