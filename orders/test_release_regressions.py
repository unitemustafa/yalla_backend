"""Regression coverage for launch checkout, lifecycle, and courier contracts."""

from decimal import Decimal
import json

from rest_framework.renderers import JSONRenderer
from rest_framework.test import APITestCase

from accounts.deletion import permanently_delete_client_account
from catalog.models import AdditionClassification, ProductAddition
from . import tests as fixtures
from .models import Order, OrderEvent
from .serializers import order_delivery_address_data


class CheckoutReleaseTests(APITestCase):
    setUp = fixtures.OrderAPITests.setUp
    authenticate_customer = fixtures.OrderAPITests.authenticate_customer
    payload = fixtures.OrderAPITests.payload

    def checkout(self, **overrides):
        data = {
            "address_id": self.address.id,
            "payment_method": "cash",
            "items": [{"variant_id": self.variant.id, "quantity": 2}],
        }
        return data | overrides

    def addition(self, *, product=None, price="25.00", active=True):
        classification, _ = AdditionClassification.objects.get_or_create(
            name="Toppings"
        )
        addition = ProductAddition.objects.create(
            classification=classification,
            name_ar="Cheese",
            name_en="Cheese",
            price=Decimal(price),
            is_active=active,
        )
        addition.products.add(product or self.product)
        return addition

    def test_additions_price_preview_create_and_courier_use_frozen_rows(self):
        addition = self.addition()
        self.authenticate_customer()
        payload = self.checkout(
            items=[
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                    "addition_ids": [addition.id],
                }
            ]
        )
        preview = self.client.post("/api/v1/orders/preview/", payload, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        created = self.client.post("/api/v1/orders/create/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(pk=created.data[0]["id"])
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("525.00"))
        self.assertEqual(
            item.additions, [{"id": addition.id, "name": "Cheese", "price": "25.00"}]
        )
        self.assertEqual(
            Decimal(preview.data["summary"]["subtotal"]), order.subtotal_price
        )
        addition.name_ar, addition.price = "Changed", Decimal("99.00")
        addition.save()
        order.assigned_representative = self.representative
        order.save(update_fields=["assigned_representative"])
        self.client.force_authenticate(self.representative)
        detail = self.client.get(f"/api/v1/courier/orders/{order.pk}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["items"][0]["additions"], item.additions)

    def test_additions_fingerprint_is_sorted_and_changed_selection_conflicts(self):
        first, second = self.addition(), self.addition(price="10.00")
        self.authenticate_customer()
        payload = self.checkout(
            items=[
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                    "addition_ids": [second.pk, first.pk],
                }
            ]
        )
        headers = {"HTTP_IDEMPOTENCY_KEY": "extras-request-001"}
        created = self.client.post(
            "/api/v1/orders/create/", payload, format="json", **headers
        )
        self.assertEqual(created.status_code, 201, created.data)
        payload["items"][0]["addition_ids"].reverse()
        replay = self.client.post(
            "/api/v1/orders/create/", payload, format="json", **headers
        )
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data[0]["id"], created.data[0]["id"])
        payload["items"][0]["addition_ids"] = [first.pk]
        conflict = self.client.post(
            "/api/v1/orders/create/", payload, format="json", **headers
        )
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(Order.objects.count(), 1)

    def test_invalid_addition_selection_is_400_and_never_creates_order(self):
        good = self.addition()
        foreign = self.addition(product=self.second_product)
        inactive = self.addition(active=False)
        self.authenticate_customer()
        for selection in (
            [good.pk, good.pk],
            [foreign.pk],
            [inactive.pk],
            [999999],
            None,
            "bad",
            [1, {}],
        ):
            with self.subTest(selection=selection):
                payload = self.checkout(
                    items=[
                        {
                            "variant_id": self.variant.id,
                            "quantity": 1,
                            "addition_ids": selection,
                        }
                    ]
                )
                response = self.client.post(
                    "/api/v1/orders/create/", payload, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Order.objects.exists())

    def test_malformed_checkout_json_is_rejected_without_server_errors(self):
        self.authenticate_customer()
        for path in ("preview", "create"):
            for data in (
                [],
                [None],
                self.checkout(items=None),
                self.checkout(items={}),
                self.checkout(items=[None]),
                self.checkout(offers="bad"),
            ):
                with self.subTest(path=path, data=data):
                    response = self.client.post(
                        f"/api/v1/orders/{path}/", data, format="json"
                    )
                    self.assertEqual(response.status_code, 400, response.data)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post("/api/v1/orders/", [], format="json").status_code, 400
        )
        self.assertFalse(Order.objects.exists())

    def test_courier_history_date_bounds_and_empty_summary(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        for delivered_at in (now - timedelta(days=2), now):
            Order.objects.create(
                user=self.customer,
                market=self.market,
                assigned_representative=self.representative,
                status=Order.Status.DELIVERED,
                delivered_at=delivered_at,
                total_price=Decimal("80.00"),
                delivery_price=Decimal("12.00"),
            )
        self.client.force_authenticate(self.representative)
        response = self.client.get(
            "/api/v1/courier/orders/",
            {
                "scope": "history",
                "delivered_from": (now - timedelta(days=1)).isoformat(),
                "delivered_before": (now + timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["summary"]["total_value"], "80.00")
        empty = self.client.get(
            "/api/v1/courier/orders/",
            {
                "scope": "history",
                "delivered_from": (now + timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(empty.status_code, 200, empty.data)
        self.assertEqual(
            empty.data["summary"],
            {"count": 0, "total_value": "0.00", "total_delivery_fees": "0.00"},
        )
        for query in (
            "scope=unknown",
            "scope=history&status=unknown",
            "scope=history&delivered_from=2026-99-99T00:00:00Z",
        ):
            self.assertEqual(
                self.client.get(f"/api/v1/courier/orders/?{query}").status_code, 400
            )

    def test_unavailable_products_and_markets_reject_preview_and_checkout(self):
        self.authenticate_customer()
        for unavailable in ("product", "market"):
            self.product.is_available = unavailable != "product"
            self.product.save(update_fields=["is_available"])
            self.market.status = "inactive" if unavailable == "market" else "active"
            self.market.save(update_fields=["status"])
            for path in ("preview", "create"):
                response = self.client.post(
                    f"/api/v1/orders/{path}/", self.checkout(), format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Order.objects.exists())

    def test_duplicate_offer_and_unavailable_offer_product_are_rejected(self):
        self.authenticate_customer()
        duplicate = self.checkout(
            offers=[{"offer_id": self.offer.pk}, {"offer_id": self.offer.pk}]
        )
        response = self.client.post("/api/v1/orders/create/", duplicate, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.product.is_available = False
        self.product.save(update_fields=["is_available"])
        response = self.client.post(
            "/api/v1/orders/create/",
            self.checkout(items=[], offers=[{"offer_id": self.offer.pk}]),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Order.objects.exists())

    def test_admin_create_replay_and_conflict_do_not_repeat_events(self):
        payload = self.payload()
        payload["items"][0]["addition_ids"] = [self.addition().pk]
        headers = {"HTTP_IDEMPOTENCY_KEY": "admin-order-retry-001"}
        first = self.client.post("/api/v1/orders/", payload, format="json", **headers)
        self.assertEqual(first.status_code, 201, first.data)
        event_count = OrderEvent.objects.count()
        replay = self.client.post("/api/v1/orders/", payload, format="json", **headers)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(
            replay.data["items"][0]["additions"], first.data["items"][0]["additions"]
        )
        payload["description"] = "Different draft"
        changed = self.client.post("/api/v1/orders/", payload, format="json", **headers)
        self.assertEqual(changed.status_code, 409, changed.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderEvent.objects.count(), event_count)

    def test_admin_idempotency_is_scoped_to_the_acting_admin(self):
        first = self.client.post(
            "/api/v1/orders/",
            self.payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY="shared-admin-key-001",
        )
        self.assertEqual(first.status_code, 201, first.data)
        another_admin = type(self.admin).objects.create_user(
            username="second-release-admin",
            email="second-release-admin@example.com",
            phone="+201000000072",
            password="InitialStrongPass123!",
            role="admin",
        )
        self.client.force_authenticate(another_admin)
        second = self.client.post(
            "/api/v1/orders/",
            self.payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY="shared-admin-key-001",
        )
        self.assertEqual(second.status_code, 201, second.data)
        self.assertNotEqual(first.data["id"], second.data["id"])

    def test_status_endpoint_cancellation_also_resolves_pending_review(self):
        created = self.client.post("/api/v1/orders/", self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(pk=created.data["id"])
        cancelled = self.client.patch(
            f"/api/v1/orders/{order.pk}/status/", {"status": "cancelled"}, format="json"
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        order.refresh_from_db()
        self.assertEqual(order.review_status, Order.ReviewStatus.REJECTED)
        self.assertEqual(
            self.client.post(f"/api/v1/admin/orders/{order.pk}/approve/").status_code,
            400,
        )

    def test_cancelled_pending_review_cannot_be_approved(self):
        created = self.client.post("/api/v1/orders/", self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(pk=created.data["id"])
        cancelled = self.client.delete(f"/api/v1/orders/{order.pk}/")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        order.refresh_from_db()
        self.assertEqual(order.review_status, Order.ReviewStatus.REJECTED)
        approved = self.client.post(f"/api/v1/admin/orders/{order.pk}/approve/")
        self.assertEqual(approved.status_code, 400, approved.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        blocker = self.client.get("/api/v1/admin/order-review/blocker/")
        self.assertEqual(blocker.status_code, 200, blocker.data)
        self.assertEqual(blocker.data["pending_count"], 0)

    def test_delete_cannot_change_a_delivered_order(self):
        created = self.client.post("/api/v1/orders/", self.payload(), format="json")
        order = Order.objects.get(pk=created.data["id"])
        order.status = Order.Status.DELIVERED
        order.save(update_fields=["status"])
        response = self.client.delete(f"/api/v1/orders/{order.pk}/")
        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_address_book_edit_does_not_change_order_and_deletion_erases_copy(self):
        self.address.street = "Original street"
        self.address.recipient_phone = "+201001234567"
        self.address.save()
        self.authenticate_customer()
        created = self.client.post(
            "/api/v1/orders/create/", self.checkout(), format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(pk=created.data[0]["id"])
        original_wire_address = json.loads(
            JSONRenderer().render(order_delivery_address_data(self.address))
        )
        self.assertEqual(order.delivery_address_snapshot, original_wire_address)
        self.address.street = "Changed street"
        self.address.save(update_fields=["street"])
        detail = self.client.get("/api/v1/orders/my/")
        self.assertEqual(
            detail.data[0]["delivery_address"]["street"], "Original street"
        )
        order.status = Order.Status.DELIVERED
        order.save(update_fields=["status"])
        permanently_delete_client_account(self.customer)
        order.refresh_from_db()
        self.assertEqual(order.delivery_address_snapshot, {})
        order.delivery_address.refresh_from_db()
        self.assertEqual(order.delivery_address.recipient_phone, "")

    def test_courier_scopes_paginate_history_and_summary_uses_entire_filtered_set(self):
        for index in range(3):
            Order.objects.create(
                user=self.customer,
                market=self.market,
                delivery_address=self.address,
                assigned_representative=self.representative,
                status=Order.Status.DELIVERED if index else Order.Status.ASSIGNED,
                total_price=Decimal("100.00"),
                delivery_price=Decimal("15.00"),
            )
        self.client.force_authenticate(self.representative)
        active = self.client.get("/api/v1/courier/orders/?scope=active&page_size=1")
        history = self.client.get("/api/v1/courier/orders/?scope=history&page_size=1")
        self.assertEqual(active.status_code, 200, active.data)
        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(active.data["count"], 1)
        self.assertEqual(history.data["count"], 2)
        self.assertEqual(len(history.data["results"]), 1)
        self.assertIsNotNone(history.data["next"])
        self.assertEqual(
            history.data["summary"],
            {"count": 2, "total_value": "200.00", "total_delivery_fees": "30.00"},
        )
        self.assertIsInstance(self.client.get("/api/v1/courier/orders/").data, list)
        invalid = self.client.get(
            "/api/v1/courier/orders/?scope=history&delivered_from=2026-10-02"
        )
        self.assertEqual(invalid.status_code, 400)

    def test_repeated_courier_delivery_returns_committed_result_without_side_effects(
        self,
    ):
        order = Order.objects.create(
            user=self.customer,
            market=self.market,
            delivery_address=self.address,
            assigned_representative=self.representative,
            status=Order.Status.PICKED_UP,
        )
        self.client.force_authenticate(self.representative)
        url = f"/api/v1/courier/orders/{order.pk}/status/"
        first = self.client.patch(
            url,
            {"status": "delivered", "delivery_note": "Committed note"},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        event_count = OrderEvent.objects.count()
        repeated = self.client.patch(
            url, {"status": "delivered", "delivery_note": "Retry note"}, format="json"
        )
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data["delivery_note"], "Committed note")
        self.assertEqual(repeated.data["delivered_at"], first.data["delivered_at"])
        self.assertEqual(OrderEvent.objects.count(), event_count)
        self.client.force_authenticate(self.other_customer)
        self.assertEqual(
            self.client.patch(url, {"status": "delivered"}).status_code, 403
        )
