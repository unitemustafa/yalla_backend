"""Mixed application write correctness; this is not an HTTP capacity benchmark.

Use PostgreSQL: SQLite cannot exercise the row locks used by these endpoints.
The 100 accounts share eight executing threads, matching the default web slot
count without claiming to reproduce Gunicorn, network, or worker performance.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient, APITransactionTestCase

from accounts.models import CourierProfile, User
from locations.models import Address

from . import tests as fixtures
from .models import Order, OrderEvent


class MixedAppConcurrencyTests(APITransactionTestCase):
    def create_customer(self, index):
        customer = User.objects.create_user(
            username=f"mixed-customer-{index}",
            email=f"mixed-customer-{index}@example.invalid",
            role=User.Role.CLIENT,
            market_region_mode=self.customer.market_region_mode,
            market_region_service_city=self.service_city,
            market_region_updated_at=timezone.now(),
        )
        address = Address.objects.create(
            user=customer,
            name="Test home",
            latitude=self.address.latitude,
            longitude=self.address.longitude,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )
        return customer, address

    def create_assigned_order(self, index):
        courier = User.objects.create_user(
            username=f"mixed-courier-{index}",
            email=f"mixed-courier-{index}@example.invalid",
            role=User.Role.REPRESENTATIVE,
        )
        CourierProfile.objects.create(
            user=courier,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
        )
        order = Order.objects.create(
            user=self.other_customer,
            market=self.market,
            assigned_representative=courier,
            status=Order.Status.ASSIGNED,
            review_status=Order.ReviewStatus.APPROVED,
            payment_method="cash",
            total_price="620.00",
        )
        return courier, order

    @skipUnlessDBFeature("has_select_for_update")
    def test_100_accounts_checkout_and_deliver_without_duplicate_writes(self):
        fixtures.OrderAPITests.setUp(self)
        jobs = []
        for index in range(20):
            for offset in range(4):
                user, address = self.create_customer(index * 4 + offset)
                jobs.append(("checkout", user.pk, address.pk))
            courier, order = self.create_assigned_order(index)
            jobs.append(("deliver", courier.pk, order.pk))
        start = Barrier(8)

        def run(entry):
            position, (action, user_id, resource_id) = entry
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=user_id))
                if position < 8:
                    start.wait(timeout=15)
                if action == "checkout":
                    payload = {
                        "address_id": resource_id,
                        "payment_method": "cash",
                        "items": [{"variant_id": self.variant.pk, "quantity": 1}],
                    }
                    headers = {"HTTP_IDEMPOTENCY_KEY": f"mixed-checkout-{user_id}"}
                    created = client.post(
                        "/api/v1/orders/create/", payload, format="json", **headers
                    )
                    self.assertEqual(created.status_code, 201, created.data)
                    replay = client.post(
                        "/api/v1/orders/create/", payload, format="json", **headers
                    )
                    self.assertEqual(replay.status_code, 200, replay.data)
                    self.assertEqual(replay.data[0]["id"], created.data[0]["id"])
                    return action, created.data[0]["id"]
                path = f"/api/v1/courier/orders/{resource_id}/status/"
                for status in (Order.Status.PICKED_UP, Order.Status.DELIVERED):
                    response = client.patch(path, {"status": status}, format="json")
                    self.assertEqual(response.status_code, 200, response.data)
                replay = client.patch(
                    path, {"status": Order.Status.DELIVERED}, format="json"
                )
                self.assertEqual(replay.status_code, 200, replay.data)
                return action, resource_id
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(run, enumerate(jobs)))
        created_ids = [pk for action, pk in results if action == "checkout"]
        delivered_ids = [pk for action, pk in results if action == "deliver"]
        self.assertEqual(len(set(created_ids)), 80)
        self.assertEqual(len(set(delivered_ids)), 20)
        self.assertEqual(Order.objects.count(), 100)
        self.assertEqual(
            Order.objects.filter(
                pk__in=created_ids,
                status=Order.Status.PENDING,
                total_price="620.00",
                items__quantity=1,
            ).count(),
            80,
        )
        self.assertEqual(
            Order.objects.filter(
                pk__in=delivered_ids,
                status=Order.Status.DELIVERED,
                delivered_at__isnull=False,
            ).count(),
            20,
        )
        self.assertEqual(OrderEvent.objects.count(), 120)

    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_courier_retries_record_only_one_transition(self):
        fixtures.OrderAPITests.setUp(self)
        courier, order = self.create_assigned_order(0)
        start = Barrier(2)

        def update():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=courier.pk))
                start.wait(timeout=10)
                response = client.patch(
                    f"/api/v1/courier/orders/{order.pk}/status/",
                    {"status": Order.Status.PICKED_UP},
                    format="json",
                )
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: update(), range(2)))
        self.assertEqual(results, [200, 200])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PICKED_UP)
        self.assertEqual(OrderEvent.objects.filter(order=order).count(), 1)
