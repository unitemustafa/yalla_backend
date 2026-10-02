from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import skipUnlessDBFeature
from rest_framework.test import APIClient, APITransactionTestCase

from accounts.models import User
from locations.models import Address
from . import tests as order_fixtures
from .models import Order, OrderEvent


class OrderIdempotencyConcurrencyTests(APITransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_global_offer_last_use_is_serialized_between_different_clients(self):
        order_fixtures.OrderAPITests.setUp(self)
        self.offer.use_limits = 1
        self.offer.save(update_fields=["use_limits"])
        other = self.other_customer
        other.market_region_mode = self.customer.market_region_mode
        other.market_region_service_city = self.service_city
        other.market_region_updated_at = self.customer.market_region_updated_at
        other.save()
        other_address = Address.objects.create(
            user=other,
            name="Other home",
            latitude=self.address.latitude,
            longitude=self.address.longitude,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )
        barrier = Barrier(2)

        def submit(user_id, address_id):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=user_id))
                barrier.wait(timeout=10)
                response = client.post(
                    "/api/v1/orders/create/",
                    {
                        "address_id": address_id,
                        "payment_method": "cash",
                        "items": [],
                        "offers": [{"offer_id": self.offer.pk}],
                    },
                    format="json",
                )
                return response.status_code, response.data
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(submit, self.customer.pk, self.address.pk)
            second = executor.submit(submit, other.pk, other_address.pk)
            responses = [first.result(timeout=30), second.result(timeout=30)]
        self.assertEqual(sorted(code for code, _ in responses), [201, 400], responses)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.offer.order_offers.count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_same_key_creates_one_order(self):
        # Committed fixtures are visible to both independent connections.
        order_fixtures.OrderAPITests.setUp(self)
        user_id = self.customer.pk
        payload = {
            "address_id": self.address.pk,
            "payment_method": "cash",
            "items": [{"variant_id": self.variant.pk, "quantity": 1}],
        }
        barrier = Barrier(2)

        def submit():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=user_id))
                barrier.wait(timeout=10)
                response = client.post(
                    "/api/v1/orders/create/",
                    payload,
                    format="json",
                    HTTP_IDEMPOTENCY_KEY="checkout-concurrent-001",
                )
                return response.status_code, response.data
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(submit)
            second = executor.submit(submit)
            responses = [first.result(timeout=30), second.result(timeout=30)]

        self.assertEqual(sorted(code for code, _ in responses), [200, 201])
        self.assertEqual(responses[0][1][0]["id"], responses[1][1][0]["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderEvent.objects.count(), 1)
