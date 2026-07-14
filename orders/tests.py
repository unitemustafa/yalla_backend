from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CourierProfile
from catalog.models import (
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAttribute,
    ProductAttributeOption,
    ProductCategory,
    ProductVariant,
    VariantAttributeValue,
)
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from offers.models import Offer, OfferItem
from notifications.models import Notification

from .models import Order, OrderEvent, OrderItem, OrderMarketSection, OrderOffer

User = get_user_model()
ORDERS_BASE = "/api/v1/orders"


class OrderAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="order-admin",
            email="order-admin@example.com",
            phone="+213555700001",
            password="Password1!",
            role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(
            username="order-customer",
            email="order-customer@example.com",
            phone="+213555700002",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        self.representative = User.objects.create_user(
            username="order-representative",
            email="order-representative@example.com",
            phone="+213555700003",
            password="Password1!",
            role=User.Role.REPRESENTATIVE,
        )
        self.other_customer = User.objects.create_user(
            username="order-other-customer",
            email="order-other-customer@example.com",
            phone="+213555700004",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        self.service_city = ServiceCity.objects.create(
            name="Algiers",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("20.00"),
            delivery_price=Decimal("120.00"),
        )
        self.delivery_area = DeliveryArea.objects.create(
            service_city=self.service_city,
            name="Central Algiers",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("5.00"),
            delivery_price=Decimal("120.00"),
        )
        self.address = Address.objects.create(
            user=self.customer,
            name="Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0420000"),
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )
        self.customer.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        self.customer.market_region_service_city = self.service_city
        self.customer.market_region_updated_at = timezone.now()
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        CourierProfile.objects.create(
            user=self.representative,
            vehicle_type="Motorcycle",
            plate_number="ORD-1",
            delivery_area=self.delivery_area,
            service_city=self.service_city,
        )
        market_classification = MarketClassification.objects.create(name="Food")
        self.market = Market.objects.create(
            classification=market_classification,
            name="Order Market",
        )
        self.market.delivery_areas.add(self.delivery_area)
        self.market.service_cities.add(self.service_city)
        self.second_market = Market.objects.create(
            classification=market_classification,
            name="Second Order Market",
        )
        self.second_market.delivery_areas.add(self.delivery_area)
        self.second_market.service_cities.add(self.service_city)
        category_classification = CategoryClassification.objects.create(name="Meals")
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Main Meals",
        )
        size_attribute = CategoryAttribute.objects.create(
            category=category,
            name="Size",
        )
        large_option = CategoryOption.objects.create(
            attribute=size_attribute,
            value="Large",
        )
        self.product = Product.objects.create(
            market=self.market,
            category=category,
            name="Burger",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("500.00"),
            sku="BURGER-1",
        )
        VariantAttributeValue.objects.create(
            variant=self.variant,
            attribute=size_attribute,
            option=large_option,
        )
        self.second_product = Product.objects.create(
            market=self.second_market,
            category=category,
            name="Pizza",
        )
        self.second_variant = ProductVariant.objects.create(
            product=self.second_product,
            price=Decimal("700.00"),
            sku="PIZZA-1",
        )
        now = timezone.now()
        self.offer = Offer.objects.create(
            market=self.market,
            show_in_general=False,
            title="Lunch",
            discount=Decimal("10.00"),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        self.offer.products.set([self.product])
        self.offer.service_cities.set([self.service_city])
        self.second_offer = Offer.objects.create(
            market=self.second_market,
            show_in_general=False,
            title="Pizza Deal",
            discount=Decimal("20.00"),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        self.second_offer.products.set([self.second_product])
        self.second_offer.service_cities.set([self.service_city])
        token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def authenticate_customer(self):
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_inactive_client_cannot_preview_or_create_with_existing_access_token(self):
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        payload = {
            "address_id": self.address.id,
            "payment_method": "cash_on_delivery",
            "items": [{"variant_id": self.variant.id, "quantity": 1}],
        }

        preview = self.client.post(
            f"{ORDERS_BASE}/preview/",
            payload,
            format="json",
        )
        create = self.client.post(
            f"{ORDERS_BASE}/create/",
            payload,
            format="json",
        )

        for response in (preview, create):
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data["code"], "account_inactive")
        self.assertFalse(Order.objects.exists())

    @patch("notifications.order_services.send_notification_push")
    def test_multi_market_creation_creates_one_parent_lifecycle_notification(self, send_push):
        self.authenticate_customer()
        payload = {
            "address_id": self.address.id,
            "payment_method": "cash_on_delivery",
            "items": [
                {"variant_id": self.variant.id, "quantity": 1},
                {"variant_id": self.second_variant.id, "quantity": 1},
            ],
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{ORDERS_BASE}/create/",
                payload,
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.market_sections.count(), 2)
        notifications = Notification.objects.filter(
            order=order,
            recipient=self.customer,
            type=Notification.Type.ORDER_CREATED,
        )
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.get().data["market_count"], 2)
        send_push.assert_called_once_with(notifications.get().id)

    @patch("notifications.order_services.send_notification_push")
    def test_real_order_transitions_create_idempotent_client_notifications(self, send_push):
        self.authenticate_customer()
        with self.captureOnCommitCallbacks(execute=True):
            created = self.client.post(
                f"{ORDERS_BASE}/create/",
                {
                    "address_id": self.address.id,
                    "payment_method": "cash_on_delivery",
                    "items": [{"variant_id": self.variant.id, "quantity": 1}],
                },
                format="json",
            )
        order = Order.objects.get(pk=created.data[0]["id"])

        admin_token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        with self.captureOnCommitCallbacks(execute=True):
            approved = self.client.post(f"/api/v1/admin/orders/{order.id}/approve/")
        with self.captureOnCommitCallbacks(execute=True):
            assigned = self.client.patch(
                f"{ORDERS_BASE}/{order.id}/assignment/",
                {"representative_id": self.representative.id},
                format="json",
            )

        courier_token = RefreshToken.for_user(self.representative).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {courier_token}")
        with self.captureOnCommitCallbacks(execute=True):
            picked_up = self.client.patch(
                f"/api/v1/courier/orders/{order.id}/status/",
                {"status": Order.Status.PICKED_UP},
                format="json",
            )
        with self.captureOnCommitCallbacks(execute=True):
            failed = self.client.patch(
                f"/api/v1/courier/orders/{order.id}/status/",
                {"status": Order.Status.FAILED_DELIVERY, "delivery_note": "No answer"},
                format="json",
            )
        before_repeat = Notification.objects.filter(order=order, recipient=self.customer).count()
        with self.captureOnCommitCallbacks(execute=True):
            repeated = self.client.patch(
                f"/api/v1/courier/orders/{order.id}/status/",
                {"status": Order.Status.FAILED_DELIVERY},
                format="json",
            )

        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.assertEqual(picked_up.status_code, status.HTTP_200_OK)
        self.assertEqual(failed.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            Notification.objects.filter(order=order, recipient=self.customer).count(),
            before_repeat,
        )
        events = set(
            Notification.objects.filter(order=order, recipient=self.customer)
            .values_list("data__event", flat=True)
        )
        self.assertTrue(
            {
                "order_created",
                "order_review_approved",
                "order_status_changed",
                "order_failed_delivery",
            }.issubset(events)
        )
        self.assertEqual(
            Notification.objects.filter(
                order=order,
                recipient=self.customer,
                type=Notification.Type.ORDER_FAILED_DELIVERY,
            ).count(),
            1,
        )

    def set_customer_region(self, mode, service_city=None):
        self.customer.market_region_mode = mode
        self.customer.market_region_service_city = service_city
        self.customer.market_region_updated_at = timezone.now() if mode else None
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )

    def make_general_market_region(self):
        self.set_customer_region(User.MarketRegionMode.GENERAL)
        self.market.scope = Market.Scope.GENERAL
        self.market.save(update_fields=["scope"])
        self.market.service_cities.clear()
        self.market.delivery_areas.clear()
        self.offer.show_in_general = True
        self.offer.save(update_fields=["show_in_general"])
        self.offer.service_cities.clear()

    def create_general_address(self, **kwargs):
        data = {
            "user": self.customer,
            "name": "General Home",
            "manual_city": "Mansoura",
            "manual_area": "University district",
            "delivery_type": Address.DeliveryType.DELIVERY,
        }
        data.update(kwargs)
        return Address.objects.create(**data)

    def assert_address_region_mismatch(self, response):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        address_error = response.data["address_id"]
        if isinstance(address_error, list):
            address_error = address_error[0]
        code = response.data["code"]
        if isinstance(code, list):
            code = code[0]
        self.assertEqual(
            str(address_error),
            "This address does not belong to the currently selected market region.",
        )
        self.assertEqual(str(code), "address_region_mismatch")

    def payload(self):
        return {
            "user_id": self.customer.id,
            "delivery_address_id": self.address.id,
            "market_id": self.market.id,
            "service_city_id": self.service_city.id,
            "payment_method": "cash_on_delivery",
            "description": "Call on arrival",
            "delivery_note": "Leave at reception",
            "items": [
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                    "unit_price": "500.00",
                }
            ],
            "offers": [
                {
                    "offer_id": self.offer.id,
                    "discount_amount": "50.00",
                }
            ],
        }

    def create_order(self):
        response = self.client.post(f"{ORDERS_BASE}/", self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response

    def test_admin_can_create_list_read_and_update_order(self):
        create_response = self.create_order()
        order_id = create_response.data["id"]

        list_response = self.client.get(f"{ORDERS_BASE}/")
        detail_response = self.client.get(f"{ORDERS_BASE}/{order_id}/")
        update_response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/",
            {"description": "Updated description", "total_price": "1100.00"},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail_response.data["items"]), 1)
        self.assertEqual(len(detail_response.data["offers"]), 1)
        serialized_offer = detail_response.data["offers"][0]
        self.assertEqual(serialized_offer["offer_id"], self.offer.id)
        self.assertEqual(serialized_offer["offer"]["id"], self.offer.id)
        self.assertEqual(serialized_offer["offer"]["title"], "Lunch")
        self.assertEqual(serialized_offer["offer"]["type"], self.offer.type)
        self.assertEqual(
            detail_response.data["market_sections"][0]["offers"][0]["offer"]["title"],
            "Lunch",
        )
        list_order = next(item for item in list_response.data if item["id"] == order_id)
        self.assertTrue(list_order["has_offer"])
        self.assertEqual(list_order["offer_titles"], ["Lunch"])
        self.assertEqual(detail_response.data["service_city"]["id"], self.service_city.id)
        self.assertEqual(detail_response.data["order_scope"], Order.Scope.SERVICE_CITY)
        self.assertFalse(detail_response.data["is_multi_market"])
        self.assertEqual(detail_response.data["market_count"], 1)
        self.assertEqual(len(detail_response.data["market_sections"]), 1)
        self.assertEqual(detail_response.data["review_status"], Order.ReviewStatus.PENDING_REVIEW)
        self.assertEqual(detail_response.data["status"], Order.Status.PENDING)
        self.assertEqual(detail_response.data["subtotal_price"], "1000.00")
        self.assertEqual(detail_response.data["discount"], "100.00")
        self.assertEqual(detail_response.data["delivery_price"], "120.00")
        self.assertEqual(detail_response.data["total_price"], "1020.00")
        self.assertEqual(detail_response.data["items"][0]["product_name"], "Burger")
        self.assertEqual(detail_response.data["items"][0]["variant_name"], "Size: Large")
        self.assertEqual(
            detail_response.data["market_sections"][0]["items"][0]["product_name"],
            "Burger",
        )
        self.assertEqual(
            detail_response.data["market_sections"][0]["items"][0]["variant_name"],
            "Size: Large",
        )
        self.assertEqual(detail_response.data["description"], "Call on arrival")
        self.assertEqual(detail_response.data["delivery_note"], "Leave at reception")
        self.assertEqual(
            detail_response.data["history"][0]["event_type"],
            OrderEvent.EventType.ORDER_CREATED,
        )
        self.assertEqual(detail_response.data["history"][0]["actor"]["id"], self.admin.id)
        self.assertEqual(detail_response.data["allowed_statuses"], [Order.Status.CANCELLED])
        self.assertEqual(update_response.data["description"], "Updated description")

    def test_order_detail_serializes_product_scoped_variant_attributes(self):
        color_attribute = ProductAttribute.objects.create(
            product=self.product,
            name="Color",
        )
        green_option = ProductAttributeOption.objects.create(
            attribute=color_attribute,
            value="Green",
        )
        self.variant.attribute_values.all().delete()
        VariantAttributeValue.objects.create(
            variant=self.variant,
            product_attribute=color_attribute,
            product_attribute_option=green_option,
        )

        create_response = self.create_order()
        order_id = create_response.data["id"]
        detail_response = self.client.get(f"{ORDERS_BASE}/{order_id}/")

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["items"][0]["variant_name"], "Color: Green")
        self.assertEqual(
            detail_response.data["market_sections"][0]["items"][0]["variant_name"],
            "Color: Green",
        )

    def test_order_list_discount_without_order_offer_is_not_an_offer(self):
        payload = self.payload()
        payload["offers"] = []
        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(pk=response.data["id"])
        order.discount = Decimal("25.00")
        order.save(update_fields=["discount"])

        list_response = self.client.get(f"{ORDERS_BASE}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        list_order = next(item for item in list_response.data if item["id"] == order.id)
        self.assertFalse(list_order["has_offer"])
        self.assertEqual(list_order["offer_titles"], [])

    def test_admin_create_sets_selected_client_as_order_user(self):
        response = self.client.post(f"{ORDERS_BASE}/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.user_id, self.customer.id)
        self.assertEqual(response.data["user_id"], self.customer.id)

    def test_admin_create_accepts_contract_without_client_prices(self):
        payload = self.payload()
        for item in payload["items"]:
            item.pop("unit_price", None)
        for offer in payload["offers"]:
            offer.pop("discount_amount", None)

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["items"][0]["unit_price"], "500.00")
        self.assertEqual(response.data["offers"][0]["discount_amount"], "100.00")
        self.assertEqual(response.data["offers"][0]["offer"]["discount"], "10.00")
        self.assertEqual(response.data["subtotal_price"], "1000.00")
        self.assertEqual(response.data["discount"], "100.00")

    def test_admin_create_applies_free_delivery_offer(self):
        self.offer.type = Offer.OfferType.DELIVERY
        self.offer.discount = Decimal("0.00")
        self.offer.save(update_fields=["type", "discount"])

        response = self.client.post(f"{ORDERS_BASE}/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["subtotal_price"], "1000.00")
        self.assertEqual(response.data["discount"], "0.00")
        self.assertEqual(response.data["delivery_price"], "0.00")
        self.assertEqual(response.data["total_price"], "1000.00")
        self.assertEqual(response.data["offers"][0]["discount_amount"], "0.00")

    def test_admin_create_does_not_require_selected_market_region(self):
        self.customer.market_region_mode = None
        self.customer.market_region_service_city = None
        self.customer.market_region_updated_at = None
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )

        response = self.client.post(f"{ORDERS_BASE}/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertNotIn("requires_region_selection", response.data)
        self.assertEqual(Order.objects.count(), 1)

    def test_admin_create_without_user_id_is_rejected(self):
        payload = self.payload()
        payload.pop("user_id")

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)
        self.assertFalse(Order.objects.exists())

    def test_admin_create_with_invalid_or_non_client_user_id_is_rejected(self):
        inactive_client = User.objects.create_user(
            username="inactive-create-client",
            email="inactive-create-client@example.com",
            phone="+213555700205",
            password="Password1!",
            role=User.Role.CLIENT,
            is_active=False,
        )
        deleted_client = User.objects.create_user(
            username="deleted-create-client",
            email="deleted-create-client@example.com",
            phone="+213555700206",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        deleted_client.deleted_at = timezone.now()
        deleted_client.save(update_fields=["deleted_at"])

        for user_id in (
            999999,
            self.admin.id,
            self.representative.id,
            inactive_client.id,
            deleted_client.id,
        ):
            with self.subTest(user_id=user_id):
                payload = self.payload()
                payload["user_id"] = user_id
                response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("user_id", response.data)
        self.assertFalse(Order.objects.exists())

    def test_representative_remains_forbidden_for_admin_create(self):
        token = RefreshToken.for_user(self.representative).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(f"{ORDERS_BASE}/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Order.objects.exists())

    def test_client_cannot_create_another_user_order_with_user_id(self):
        self.authenticate_customer()
        payload = {
            "user_id": self.other_customer.id,
            "address_id": self.address.id,
            "payment_method": "cash_on_delivery",
            "items": [{"variant_id": self.variant.id, "quantity": 1}],
        }

        response = self.client.post(f"{ORDERS_BASE}/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)
        self.assertFalse(Order.objects.exists())

    def test_admin_can_update_manual_delivery_price_and_total(self):
        other_address = Address.objects.create(
            user=self.customer,
            name="Other Area",
            service_city=self.service_city,
            delivery_type=Address.DeliveryType.DELIVERY,
        )
        payload = self.payload()
        payload["delivery_address_id"] = other_address.id
        payload.pop("service_city_id")
        payload["offers"] = []
        create_response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
        self.assertIsNone(create_response.data["delivery_price"])
        self.assertEqual(create_response.data["total_price"], "1000.00")

        response = self.client.patch(
            f"{ORDERS_BASE}/{create_response.data['id']}/delivery-price/",
            {"delivery_price": "75.50"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["delivery_price"], "75.50")
        self.assertEqual(response.data["total_price"], "1075.50")
        self.assertEqual(
            response.data["history"][-1]["event_type"],
            OrderEvent.EventType.DELIVERY_PRICE_CHANGED,
        )
        self.assertEqual(
            response.data["history"][-1]["metadata"]["to_delivery_price"],
            "75.50",
        )
        order = Order.objects.get(pk=create_response.data["id"])
        self.assertEqual(order.delivery_price, Decimal("75.50"))
        self.assertEqual(order.total_price, Decimal("1075.50"))

    def test_admin_cannot_restore_delivery_fee_on_free_delivery_order(self):
        self.offer.type = Offer.OfferType.DELIVERY
        self.offer.discount = Decimal("0.00")
        self.offer.save(update_fields=["type", "discount"])
        create_response = self.client.post(
            f"{ORDERS_BASE}/",
            self.payload(),
            format="json",
        )
        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
            create_response.data,
        )

        response = self.client.patch(
            f"{ORDERS_BASE}/{create_response.data['id']}/delivery-price/",
            {"delivery_price": "75.50"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_price", response.data)
        order = Order.objects.get(pk=create_response.data["id"])
        self.assertEqual(order.delivery_price, Decimal("0.00"))
        self.assertEqual(order.total_price, Decimal("1000.00"))
        self.assertFalse(
            order.history_events.filter(
                event_type=OrderEvent.EventType.DELIVERY_PRICE_CHANGED,
            ).exists()
        )

    def test_admin_delivery_price_update_rejects_terminal_orders(self):
        order_id = self.create_order().data["id"]
        Order.objects.filter(pk=order_id).update(status=Order.Status.CANCELLED)

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/delivery-price/",
            {"delivery_price": "75.50"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_order_create_rejects_unsafe_system_fields(self):
        unsafe_payload = self.payload()
        unsafe_payload.update(
            {
                "status": Order.Status.CONFIRMED,
                "review_status": Order.ReviewStatus.APPROVED,
                "assigned_representative_id": self.representative.id,
                "delivery_price": "999.00",
                "order_scope": Order.Scope.GENERAL,
                "delivery_area_id": self.delivery_area.id,
                "delivery_type": Order.DeliveryType.DELIVERY,
                "subtotal_price": "1.00",
                "total_price": "1.00",
                "discount": "1.00",
                "assigned_at": timezone.now().isoformat(),
                "delivered_at": timezone.now().isoformat(),
                "image": None,
                "delivery_proof": None,
            }
        )

        response = self.client.post(
            f"{ORDERS_BASE}/",
            unsafe_payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in (
            "status",
            "review_status",
            "assigned_representative_id",
            "delivery_price",
            "order_scope",
            "delivery_area_id",
            "delivery_type",
            "subtotal_price",
            "total_price",
            "discount",
            "assigned_at",
            "delivered_at",
            "image",
            "delivery_proof",
        ):
            self.assertIn(field, response.data)
        self.assertFalse(Order.objects.exists())

    def test_admin_create_other_delivery_stores_null_delivery_price(self):
        other_address = Address.objects.create(
            user=self.customer,
            name="Other Area",
            service_city=self.service_city,
            delivery_type=Address.DeliveryType.DELIVERY,
        )
        payload = self.payload()
        payload["delivery_address_id"] = other_address.id
        payload.pop("service_city_id")
        payload["offers"] = [
            {
                "offer_id": self.offer.id,
                "discount_amount": "25.00",
            }
        ]

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data["id"])
        self.assertIsNone(order.delivery_area_id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertIsNone(order.delivery_price)
        self.assertEqual(order.subtotal_price, Decimal("1000.00"))
        self.assertEqual(order.discount, Decimal("100.00"))
        self.assertEqual(order.total_price, Decimal("900.00"))
        self.assertIsNone(response.data["delivery_price"])

    def test_admin_create_allows_variants_from_multiple_markets(self):
        payload = self.payload()
        payload["items"].append(
            {
                "variant_id": self.second_variant.id,
                "quantity": 1,
                "unit_price": "700.00",
            }
        )
        payload["offers"].append(
            {
                "offer_id": self.second_offer.id,
                "discount_amount": "1.00",
            }
        )

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.market_id, self.market.id)
        self.assertEqual(order.subtotal_price, Decimal("1700.00"))
        self.assertEqual(order.discount, Decimal("240.00"))
        self.assertEqual(order.delivery_price, Decimal("120.00"))
        self.assertEqual(order.total_price, Decimal("1580.00"))
        self.assertEqual(order.market_sections.count(), 2)
        self.assertEqual(
            set(order.market_sections.values_list("market_id", flat=True)),
            {self.market.id, self.second_market.id},
        )
        self.assertEqual(Order.objects.count(), 1)
        self.assertTrue(response.data["is_multi_market"])
        self.assertEqual(response.data["market_count"], 2)
        self.assertEqual(len(response.data["market_sections"]), 2)
        self.assertEqual(len(response.data["pickup_stops"]), 2)

    def test_admin_preview_and_create_totals_match_for_fixed_area_delivery(self):
        payload = {
            "user_id": self.customer.id,
            "address_id": self.address.id,
            "payment_method": "cash_on_delivery",
            "items": [{"variant_id": self.variant.id, "quantity": 1}],
            "offers": [],
        }

        preview_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            payload,
            format="json",
        )
        create_response = self.client.post(
            f"{ORDERS_BASE}/",
            payload,
            format="json",
        )

        self.assertEqual(preview_response.status_code, status.HTTP_200_OK, preview_response.data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
        order = Order.objects.get(id=create_response.data["id"])
        self.assertEqual(preview_response.data["summary"]["subtotal"], f"{order.subtotal_price:.2f}")
        self.assertEqual(preview_response.data["summary"]["discount_total"], f"{order.discount:.2f}")
        self.assertEqual(preview_response.data["summary"]["delivery_total"], f"{order.delivery_price:.2f}")
        self.assertEqual(preview_response.data["summary"]["grand_total"], f"{order.total_price:.2f}")

    def test_fixed_area_delivery_is_included_once_in_preview_and_admin_create(self):
        self.variant.price = Decimal("157.50")
        self.variant.save(update_fields=["price"])
        self.delivery_area.delivery_price = Decimal("40.00")
        self.delivery_area.save(update_fields=["delivery_price"])

        payload = {
            "user_id": self.customer.id,
            "address_id": self.address.id,
            "payment_method": "cash_on_delivery",
            "items": [{"variant_id": self.variant.id, "quantity": 1}],
        }

        preview_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            payload,
            format="json",
        )
        create_response = self.client.post(
            f"{ORDERS_BASE}/",
            payload,
            format="json",
        )

        self.assertEqual(preview_response.status_code, status.HTTP_200_OK, preview_response.data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
        order = Order.objects.get(id=create_response.data["id"])
        self.assertEqual(preview_response.data["summary"]["subtotal"], "157.50")
        self.assertEqual(preview_response.data["summary"]["delivery_total"], "40.00")
        self.assertEqual(preview_response.data["summary"]["grand_total"], "197.50")
        self.assertEqual(order.subtotal_price, Decimal("157.50"))
        self.assertEqual(order.delivery_price, Decimal("40.00"))
        self.assertEqual(order.total_price, Decimal("197.50"))

    def test_admin_create_writes_initial_order_event_with_admin_actor(self):
        response = self.client.post(f"{ORDERS_BASE}/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        event = OrderEvent.objects.get(order_id=response.data["id"])
        self.assertEqual(event.event_type, OrderEvent.EventType.ORDER_CREATED)
        self.assertEqual(event.actor_id, self.admin.id)
        self.assertEqual(event.order.user_id, self.customer.id)

    def test_failed_admin_create_does_not_leave_partial_rows(self):
        other_address = Address.objects.create(
            user=self.other_customer,
            name="Other User Home",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )
        payload = self.payload()
        payload["delivery_address_id"] = other_address.id

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderMarketSection.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.assertFalse(OrderOffer.objects.exists())
        self.assertFalse(OrderEvent.objects.exists())

    def test_admin_create_rejects_address_for_another_user(self):
        other_address = Address.objects.create(
            user=self.other_customer,
            name="Other User Home",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )
        payload = self.payload()
        payload["delivery_address_id"] = other_address.id

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_address_id", response.data)

    def test_admin_create_rejects_service_city_mismatch(self):
        other_city = ServiceCity.objects.create(
            name="Wrong City",
            delivery_price=Decimal("80.00"),
        )
        payload = self.payload()
        payload["service_city_id"] = other_city.id

        response = self.client.post(f"{ORDERS_BASE}/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service_city_id", response.data)

    def test_assignment_sets_order_status_to_assigned(self):
        order_id = self.create_order().data["id"]
        approve_response = self.client.post(
            f"/api/v1/admin/orders/{order_id}/approve/",
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order"]["status"], Order.Status.ASSIGNED)
        self.assertEqual(
            response.data["order"]["assigned_representative_id"],
            self.representative.id,
        )
        self.assertIsNotNone(response.data["order"]["assigned_at"])
        self.assertTrue(
            Notification.objects.filter(
                audience=Notification.Audience.COURIER,
                type=Notification.Type.ORDER_ASSIGNED,
                recipient=self.representative,
            ).exists()
        )

    def test_admin_order_list_and_detail_include_assigned_representative_summary(self):
        order_id = self.create_order().data["id"]
        self.client.post(f"/api/v1/admin/orders/{order_id}/approve/", format="json")
        assign_response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)

        list_response = self.client.get(f"{ORDERS_BASE}/")
        detail_response = self.client.get(f"{ORDERS_BASE}/{order_id}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        list_order = list_response.data[0]
        self.assertEqual(
            list_order["assigned_representative"]["id"],
            self.representative.id,
        )
        self.assertEqual(
            list_order["assigned_representative"]["phone"],
            self.representative.phone,
        )
        self.assertEqual(
            detail_response.data["assigned_representative"]["service_city"]["id"],
            self.service_city.id,
        )
        self.assertEqual(
            detail_response.data["assigned_representative"]["vehicle_type"],
            "Motorcycle",
        )
        self.assertNotIn("history", list_order)
        self.assertIn("history", detail_response.data)
        self.assertIn("allowed_statuses", detail_response.data)

    def test_unassigned_order_serializes_null_representative_summary(self):
        order_id = self.create_order().data["id"]

        list_response = self.client.get(f"{ORDERS_BASE}/")
        detail_response = self.client.get(f"{ORDERS_BASE}/{order_id}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(list_response.data[0]["assigned_representative"])
        self.assertIsNone(detail_response.data["assigned_representative"])

    def test_assignment_and_unassignment_create_history_events(self):
        order_id = self.create_order().data["id"]
        self.client.post(f"/api/v1/admin/orders/{order_id}/approve/", format="json")
        self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": None},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["assigned_representative"])
        self.assertEqual(response.data["status"], Order.Status.CONFIRMED)
        event_types = [event["event_type"] for event in response.data["history"]]
        self.assertIn(OrderEvent.EventType.ASSIGNED, event_types)
        self.assertIn(OrderEvent.EventType.UNASSIGNED, event_types)

    def test_status_api_changes_status(self):
        order_id = self.create_order().data["id"]
        approve_response = self.client.post(
            f"/api/v1/admin/orders/{order_id}/approve/",
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/status/",
            {"status": Order.Status.CANCELLED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.CANCELLED)
        self.assertEqual(
            response.data["history"][-1]["event_type"],
            OrderEvent.EventType.CANCELLED,
        )

    def test_status_api_rejects_terminal_and_failed_delivery_transitions(self):
        order_id = self.create_order().data["id"]
        self.client.post(f"/api/v1/admin/orders/{order_id}/approve/", format="json")
        order = Order.objects.get(pk=order_id)
        order.status = Order.Status.FAILED_DELIVERY
        order.save(update_fields=["status", "updated_at"])

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/status/",
            {"status": Order.Status.DELIVERED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        detail_response = self.client.get(f"{ORDERS_BASE}/{order_id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["allowed_statuses"], [])

    def test_delete_cancels_order_without_removing_it(self):
        order_id = self.create_order().data["id"]

        response = self.client.delete(f"{ORDERS_BASE}/{order_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.CANCELLED)
        self.assertEqual(
            response.data["history"][-1]["event_type"],
            OrderEvent.EventType.CANCELLED,
        )
        self.assertTrue(Order.objects.filter(pk=order_id).exists())

    def test_order_detail_serializes_inactive_delivery_address(self):
        self.address.is_active = False
        self.address.is_default = False
        self.address.save(update_fields=["is_active", "is_default"])
        order = Order.objects.create(
            user=self.customer,
            delivery_address=self.address,
            market=self.market,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Order.DeliveryType.FIXED_AREA,
            payment_method="cash_on_delivery",
            delivery_price=self.delivery_area.delivery_price,
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("620.00"),
        )

        response = self.client.get(f"{ORDERS_BASE}/{order.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["delivery_address"]["id"], self.address.id)
        self.assertEqual(order.delivery_address_id, self.address.id)

    def test_client_can_list_only_their_orders(self):
        own_order_id = self.create_order().data["id"]
        other_order = Order.objects.create(
            user=self.other_customer,
            market=self.market,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Order.DeliveryType.FIXED_AREA,
            payment_method="cash_on_delivery",
            status=Order.Status.PENDING,
            delivery_price=self.delivery_area.delivery_price,
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("620.00"),
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get(f"{ORDERS_BASE}/my/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [own_order_id])
        self.assertNotIn(other_order.id, [item["id"] for item in response.data])

    def test_client_order_list_supports_status_filter(self):
        confirmed_order_id = self.create_order().data["id"]
        Order.objects.filter(id=confirmed_order_id).update(status=Order.Status.CONFIRMED)
        Order.objects.create(
            user=self.customer,
            market=self.market,
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Order.DeliveryType.FIXED_AREA,
            payment_method="cash_on_delivery",
            status=Order.Status.PENDING,
            delivery_price=self.delivery_area.delivery_price,
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("620.00"),
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get(
            f"{ORDERS_BASE}/my/",
            {"status": Order.Status.CONFIRMED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [confirmed_order_id])

    def test_non_client_cannot_list_client_orders(self):
        response = self.client.get(f"{ORDERS_BASE}/my/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_preview_requires_saved_market_region(self):
        self.customer.market_region_mode = None
        self.customer.market_region_service_city = None
        self.customer.market_region_updated_at = None
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"items": [{"variant_id": self.variant.id, "quantity": 1}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_client_preview_rejects_product_outside_saved_region(self):
        remote_city = ServiceCity.objects.create(
            name="Remote Preview City",
            delivery_price=Decimal("90.00"),
        )
        remote_market = Market.objects.create(
            classification=self.market.classification,
            name="Remote Preview Market",
        )
        remote_market.service_cities.add(remote_city)
        remote_product = Product.objects.create(
            market=remote_market,
            category=self.product.category,
            name="Remote Product",
        )
        remote_variant = ProductVariant.objects.create(
            product=remote_product,
            price=Decimal("300.00"),
            sku="REMOTE-1",
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"items": [{"variant_id": remote_variant.id, "quantity": 1}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["items"][0],
            "لا يمكن دمج منتجات من مدن مختلفة في نفس الطلب",
        )

    def test_client_create_general_order_uses_default_delivery_address_without_scope_leakage(self):
        self.make_general_market_region()
        general_address = self.create_general_address(
            manual_city="القاهرة",
            manual_area="مصر الجديدة",
            details="شارع الثورة بجوار بنزينة التعاون",
            is_default=True,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
                "offers": [{"offer_id": self.offer.id}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data[0]["id"])
        self.assertEqual(order.order_scope, Order.Scope.GENERAL)
        self.assertEqual(order.delivery_address_id, general_address.id)
        self.assertIsNone(order.service_city_id)
        self.assertIsNone(order.delivery_area_id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertIsNone(order.delivery_price)
        self.assertEqual(order.total_price, Decimal("450.00"))

    def test_client_can_preview_order_grouped_by_market(self):
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "items": [
                    {
                        "variant_id": self.variant.id,
                        "quantity": 2,
                    },
                    {
                        "variant_id": self.second_variant.id,
                        "quantity": 1,
                    },
                ],
                "offers": [
                    {
                        "offer_id": self.offer.id,
                    },
                    {
                        "offer_id": self.second_offer.id,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["addresses"][0]["id"], self.address.id)
        self.assertNotIn("fullName", response.data["addresses"][0])
        self.assertNotIn("phone", response.data["addresses"][0])
        self.assertEqual(response.data["order_scope"], Order.Scope.SERVICE_CITY)
        self.assertTrue(response.data["is_multi_market"])
        self.assertEqual(response.data["market_count"], 2)
        self.assertEqual(len(response.data["market_groups"]), 2)

        first_market = response.data["market_groups"][0]
        second_market = response.data["market_groups"][1]
        self.assertEqual(first_market["market"]["id"], self.market.id)
        self.assertEqual(first_market["delivery_area"]["id"], self.delivery_area.id)
        self.assertEqual(first_market["delivery_type"], Order.DeliveryType.FIXED_AREA)
        self.assertEqual(first_market["delivery_price"], "120.00")
        self.assertEqual(first_market["delivery_message"], "")
        self.assertEqual(first_market["pricing"]["products_subtotal"], "1000.00")
        self.assertEqual(first_market["pricing"]["total_offer_discounts"], "100.00")
        self.assertEqual(first_market["pricing"]["delivery_price"], "120.00")
        self.assertEqual(first_market["pricing"]["market_total"], "1020.00")
        self.assertEqual(
            first_market["selected_offers"][0]["offer_products_subtotal"],
            "1000.00",
        )
        self.assertEqual(first_market["selected_offers"][0]["discount_amount"], "100.00")
        self.assertEqual(
            first_market["selected_offers"][0]["products"][0]["variant_id"],
            self.variant.id,
        )
        self.assertEqual(
            first_market["selected_offers"][0]["products"][0]["unit_price"],
            "500.00",
        )
        self.assertTrue(
            first_market["selected_offers"][0]["products"][0]["is_selected"]
        )

        self.assertEqual(second_market["market"]["id"], self.second_market.id)
        self.assertEqual(second_market["pricing"]["products_subtotal"], "700.00")
        self.assertEqual(second_market["pricing"]["total_offer_discounts"], "140.00")
        self.assertIsNone(second_market["pricing"]["delivery_price"])
        self.assertEqual(second_market["pricing"]["market_total"], "560.00")

        self.assertEqual(response.data["summary"]["subtotal"], "1700.00")
        self.assertEqual(response.data["summary"]["discount_total"], "240.00")
        self.assertEqual(response.data["summary"]["delivery_total"], "120.00")
        self.assertEqual(response.data["summary"]["grand_total"], "1580.00")

    def test_product_percentage_discount_is_applied_to_preview_and_order(self):
        self.product.discount = Decimal("50.00")
        self.product.save(update_fields=["discount", "updated_at"])
        self.authenticate_customer()

        payload = {
            "address_id": self.address.id,
            "items": [{"variant_id": self.variant.id, "quantity": 2}],
        }
        preview_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            payload,
            format="json",
        )

        self.assertEqual(
            preview_response.status_code,
            status.HTTP_200_OK,
            preview_response.data,
        )
        selected_product = preview_response.data["market_groups"][0][
            "selected_products"
        ][0]
        self.assertEqual(selected_product["unit_price"], "250.00")
        self.assertEqual(selected_product["subtotal"], "500.00")
        self.assertEqual(preview_response.data["summary"]["subtotal"], "500.00")
        self.assertEqual(
            preview_response.data["summary"]["grand_total"],
            "620.00",
        )

        create_response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                **payload,
                "payment_method": "cash_on_delivery",
            },
            format="json",
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
            create_response.data,
        )
        order = Order.objects.get(pk=create_response.data[0]["id"])
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("250.00"))
        self.assertEqual(order.subtotal_price, Decimal("500.00"))
        self.assertEqual(order.total_price, Decimal("620.00"))

    def test_client_can_preview_their_own_order(self):
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": self.customer.id,
                "address_id": self.address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["selected_address"]["id"], self.address.id)
        self.assertEqual(response.data["summary"]["grand_total"], "620.00")

    def test_client_cannot_preview_another_user_by_sending_user_id(self):
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": self.other_customer.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)

    def test_admin_can_preview_for_selected_active_client(self):
        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": self.customer.id,
                "delivery_address_id": self.address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["selected_address"]["id"], self.address.id)
        self.assertEqual(response.data["summary"]["grand_total"], "620.00")

    def test_admin_preview_without_user_id_is_rejected(self):
        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"items": [{"variant_id": self.variant.id, "quantity": 1}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)

    def test_admin_preview_with_invalid_user_id_is_rejected(self):
        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": 999999,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)

    def test_admin_preview_with_representative_or_admin_user_id_is_rejected(self):
        for user in (self.representative, self.admin):
            with self.subTest(user=user.username):
                response = self.client.post(
                    f"{ORDERS_BASE}/preview/",
                    {
                        "user_id": user.id,
                        "items": [{"variant_id": self.variant.id, "quantity": 1}],
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("user_id", response.data)

    def test_admin_preview_with_inactive_or_deleted_client_is_rejected(self):
        inactive_client = User.objects.create_user(
            username="inactive-preview-client",
            email="inactive-preview-client@example.com",
            phone="+213555700105",
            password="Password1!",
            role=User.Role.CLIENT,
            is_active=False,
        )
        deleted_client = User.objects.create_user(
            username="deleted-preview-client",
            email="deleted-preview-client@example.com",
            phone="+213555700106",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        deleted_client.deleted_at = timezone.now()
        deleted_client.save(update_fields=["deleted_at"])

        for user in (inactive_client, deleted_client):
            with self.subTest(user=user.username):
                response = self.client.post(
                    f"{ORDERS_BASE}/preview/",
                    {
                        "user_id": user.id,
                        "items": [{"variant_id": self.variant.id, "quantity": 1}],
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("user_id", response.data)

    def test_representative_remains_forbidden_for_preview(self):
        token = RefreshToken.for_user(self.representative).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": self.customer.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_preview_uses_selected_clients_address_and_saved_region(self):
        self.other_customer.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        self.other_customer.market_region_service_city = self.service_city
        self.other_customer.market_region_updated_at = timezone.now()
        self.other_customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        other_address = Address.objects.create(
            user=self.other_customer,
            name="Other Customer Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0420000"),
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": self.other_customer.id,
                "address_id": other_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["selected_address"]["id"], other_address.id)
        self.assertEqual(response.data["addresses"][0]["id"], other_address.id)
        self.assertNotIn(self.address.id, [item["id"] for item in response.data["addresses"]])
        self.assertEqual(response.data["service_city"]["id"], self.service_city.id)

    def test_preview_totals_match_normal_create_order_calculation(self):
        preview_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "user_id": self.customer.id,
                "address_id": self.address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 2}],
                "offers": [{"offer_id": self.offer.id}],
            },
            format="json",
        )

        self.assertEqual(preview_response.status_code, status.HTTP_200_OK, preview_response.data)
        self.assertFalse(Order.objects.exists())

        self.authenticate_customer()
        create_response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "address_id": self.address.id,
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 2}],
                "offers": [{"offer_id": self.offer.id}],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
        order = Order.objects.get(id=create_response.data[0]["id"])
        self.assertEqual(preview_response.data["summary"]["subtotal"], f"{order.subtotal_price:.2f}")
        self.assertEqual(preview_response.data["summary"]["discount_total"], f"{order.discount:.2f}")
        self.assertEqual(preview_response.data["summary"]["delivery_total"], f"{order.delivery_price:.2f}")
        self.assertEqual(preview_response.data["summary"]["grand_total"], f"{order.total_price:.2f}")

    def test_client_preview_other_delivery_has_null_delivery_price(self):
        other_address = Address.objects.create(
            user=self.customer,
            name="Other Area",
            service_city=self.service_city,
            delivery_type=Address.DeliveryType.DELIVERY,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": other_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        group = response.data["market_groups"][0]
        self.assertIsNone(group["delivery_area"])
        self.assertEqual(group["delivery_type"], Order.DeliveryType.DELIVERY)
        self.assertIsNone(group["delivery_price"])
        self.assertIsNone(group["pricing"]["delivery_price"])
        self.assertEqual(
            group["delivery_message"],
            "Delivery price will be determined later.",
        )
        self.assertEqual(group["pricing"]["market_total"], "500.00")
        self.assertEqual(response.data["summary"]["delivery_total"], "0.00")
        self.assertEqual(response.data["summary"]["grand_total"], "500.00")

    def test_preview_offer_uses_product_variant_price_when_product_is_not_selected(self):
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "items": [
                    {
                        "variant_id": self.second_variant.id,
                        "quantity": 1,
                    },
                ],
                "offers": [
                    {
                        "offer_id": self.offer.id,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        first_market = response.data["market_groups"][0]
        self.assertEqual(first_market["pricing"]["products_subtotal"], "500.00")
        self.assertEqual(first_market["pricing"]["total_offer_discounts"], "50.00")
        self.assertEqual(first_market["pricing"]["market_total"], "570.00")
        self.assertEqual(
            first_market["selected_offers"][0]["offer_products_subtotal"],
            "500.00",
        )
        self.assertEqual(first_market["selected_offers"][0]["discount_amount"], "50.00")
        self.assertEqual(
            first_market["selected_offers"][0]["products"][0]["variant_id"],
            self.variant.id,
        )
        self.assertFalse(
            first_market["selected_offers"][0]["products"][0]["is_selected"]
        )

    def test_preview_offer_uses_its_exact_variant_and_quantity(self):
        selected_variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("900.00"),
            sku="BURGER-PREMIUM",
        )
        OfferItem.objects.create(
            offer=self.offer,
            variant=selected_variant,
            quantity=2,
        )
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"offers": [{"offer_id": self.offer.id}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        selected_offer = response.data["market_groups"][0]["selected_offers"][0]
        self.assertEqual(selected_offer["offer_products_subtotal"], "1800.00")
        self.assertEqual(selected_offer["discount_amount"], "180.00")
        self.assertEqual(selected_offer["products"][0]["variant_id"], selected_variant.id)
        self.assertEqual(selected_offer["products"][0]["quantity"], 2)

    def test_package_item_can_skip_product_discount_before_offer_discount(self):
        self.product.discount = Decimal("10.00")
        self.product.save(update_fields=["discount", "updated_at"])
        self.offer.discount = Decimal("15.00")
        self.offer.save(update_fields=["discount"])
        OfferItem.objects.create(
            offer=self.offer,
            variant=self.variant,
            quantity=1,
            apply_product_discount=False,
        )
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"offers": [{"offer_id": self.offer.id}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        selected_offer = response.data["market_groups"][0]["selected_offers"][0]
        product = selected_offer["products"][0]
        self.assertEqual(product["unit_price"], "500.00")
        self.assertFalse(product["apply_product_discount"])
        self.assertEqual(product["product_discount_percentage"], "10.00")
        self.assertEqual(selected_offer["offer_products_subtotal"], "500.00")
        self.assertEqual(selected_offer["discount_amount"], "75.00")
        self.assertEqual(response.data["summary"]["subtotal"], "500.00")
        self.assertEqual(response.data["summary"]["discount_total"], "75.00")

    def test_package_item_applies_product_discount_before_offer_discount_by_default(self):
        self.product.discount = Decimal("10.00")
        self.product.save(update_fields=["discount", "updated_at"])
        self.offer.discount = Decimal("15.00")
        self.offer.save(update_fields=["discount"])
        OfferItem.objects.create(
            offer=self.offer,
            variant=self.variant,
            quantity=1,
        )
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"offers": [{"offer_id": self.offer.id}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        selected_offer = response.data["market_groups"][0]["selected_offers"][0]
        product = selected_offer["products"][0]
        self.assertEqual(product["unit_price"], "450.00")
        self.assertTrue(product["apply_product_discount"])
        self.assertEqual(selected_offer["offer_products_subtotal"], "450.00")
        self.assertEqual(selected_offer["discount_amount"], "67.50")
        self.assertEqual(response.data["summary"]["subtotal"], "450.00")
        self.assertEqual(response.data["summary"]["discount_total"], "67.50")

    def test_delivery_offer_waives_delivery_in_preview_and_client_order(self):
        self.offer.type = Offer.OfferType.DELIVERY
        self.offer.discount = Decimal("0.00")
        self.offer.save(update_fields=["type", "discount"])
        self.authenticate_customer()
        payload = {
            "address_id": self.address.id,
            "payment_method": "cash_on_delivery",
            "offers": [{"offer_id": self.offer.id}],
        }

        preview_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            payload,
            format="json",
        )
        create_response = self.client.post(
            f"{ORDERS_BASE}/create/",
            payload,
            format="json",
        )

        self.assertEqual(preview_response.status_code, status.HTTP_200_OK, preview_response.data)
        preview_market = preview_response.data["market_groups"][0]
        self.assertEqual(preview_market["delivery_price"], "0.00")
        self.assertEqual(preview_market["pricing"]["delivery_price"], "0.00")
        self.assertEqual(preview_market["pricing"]["market_total"], "500.00")
        self.assertEqual(preview_response.data["summary"]["delivery_total"], "0.00")
        self.assertEqual(preview_response.data["summary"]["grand_total"], "500.00")

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
        created_order = create_response.data[0]
        self.assertEqual(created_order["subtotal_price"], "500.00")
        self.assertEqual(created_order["discount"], "0.00")
        self.assertEqual(created_order["delivery_price"], "0.00")
        self.assertEqual(created_order["total_price"], "500.00")
        self.assertEqual(created_order["offers"][0]["discount_amount"], "0.00")

    def test_client_create_order_creates_one_parent_order_with_market_sections(self):
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "payment_method": "cash_on_delivery",
                "description": "Leave at door",
                "items": [
                    {
                        "variant_id": self.variant.id,
                        "quantity": 2,
                    },
                    {
                        "variant_id": self.second_variant.id,
                        "quantity": 1,
                    },
                ],
                "offers": [
                    {
                        "offer_id": self.offer.id,
                    },
                    {
                        "offer_id": self.second_offer.id,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(len(response.data), 1)
        parent_order = Order.objects.get(id=response.data[0]["id"])
        self.assertEqual(parent_order.market_id, self.market.id)
        self.assertEqual(parent_order.order_scope, Order.Scope.SERVICE_CITY)
        self.assertEqual(parent_order.delivery_address_id, self.address.id)
        self.assertEqual(parent_order.service_city_id, self.service_city.id)
        self.assertEqual(parent_order.delivery_area_id, self.delivery_area.id)
        self.assertEqual(parent_order.delivery_type, Order.DeliveryType.FIXED_AREA)
        self.assertEqual(parent_order.status, Order.Status.PENDING)
        self.assertEqual(
            parent_order.review_status,
            Order.ReviewStatus.PENDING_REVIEW,
        )
        self.assertEqual(parent_order.subtotal_price, Decimal("1700.00"))
        self.assertEqual(parent_order.discount, Decimal("240.00"))
        self.assertEqual(parent_order.delivery_price, Decimal("120.00"))
        self.assertEqual(parent_order.total_price, Decimal("1580.00"))
        self.assertEqual(parent_order.items.count(), 2)
        self.assertEqual(parent_order.order_offers.count(), 2)
        sections = list(parent_order.market_sections.order_by("sort_order"))
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].market_id, self.market.id)
        self.assertEqual(sections[0].subtotal_price, Decimal("1000.00"))
        self.assertEqual(sections[0].discount, Decimal("100.00"))
        self.assertEqual(sections[1].market_id, self.second_market.id)
        self.assertEqual(sections[1].subtotal_price, Decimal("700.00"))
        self.assertEqual(sections[1].discount, Decimal("140.00"))
        self.assertEqual(
            OrderItem.objects.get(order=parent_order, section=sections[0]).variant_id,
            self.variant.id,
        )
        self.assertEqual(
            OrderOffer.objects.get(order=parent_order, section=sections[0]).discount_amount,
            Decimal("100.00"),
        )
        self.assertTrue(response.data[0]["is_multi_market"])
        self.assertEqual(response.data[0]["market_count"], 2)
        self.assertEqual(len(response.data[0]["market_sections"]), 2)
        self.assertEqual(
            Notification.objects.filter(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.NEW_ORDER_REVIEW,
                is_blocking=True,
                is_resolved=False,
            ).count(),
            1,
        )

    def test_client_create_other_delivery_stores_null_delivery_price(self):
        other_address = Address.objects.create(
            user=self.customer,
            name="Other Area",
            service_city=self.service_city,
            delivery_type=Address.DeliveryType.DELIVERY,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "address_id": other_address.id,
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data[0]["id"])
        self.assertEqual(order.service_city_id, self.service_city.id)
        self.assertIsNone(order.delivery_area_id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertIsNone(order.delivery_price)
        self.assertEqual(order.total_price, Decimal("500.00"))
        self.assertIsNone(response.data[0]["delivery_area"])
        self.assertEqual(response.data[0]["delivery_type"], Order.DeliveryType.DELIVERY)
        self.assertIsNone(response.data[0]["delivery_price"])

    def test_service_city_manual_unsupported_area_uses_city_courier_matching(self):
        unsupported_address = Address.objects.create(
            user=self.customer,
            name="Unsupported Area",
            service_city=self.service_city,
            manual_area="منطقة غير مضافة",
            delivery_type=Address.DeliveryType.DELIVERY,
        )
        remote_city = ServiceCity.objects.create(
            name="Remote Manual City",
            delivery_price=Decimal("90.00"),
        )
        remote_area = DeliveryArea.objects.create(
            service_city=remote_city,
            name="Remote Manual Area",
            delivery_price=Decimal("90.00"),
        )
        remote_representative = User.objects.create_user(
            username="manual-remote-representative",
            email="manual-remote-representative@example.com",
            phone="+213555700007",
            password="Password1!",
            role=User.Role.REPRESENTATIVE,
        )
        CourierProfile.objects.create(
            user=remote_representative,
            vehicle_type="Motorcycle",
            plate_number="MAN-REMOTE-1",
            delivery_area=remote_area,
            service_city=remote_city,
        )
        self.authenticate_customer()

        create_response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "address_id": unsupported_address.id,
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
            create_response.data,
        )
        order = Order.objects.get(id=create_response.data[0]["id"])
        self.assertEqual(order.order_scope, Order.Scope.SERVICE_CITY)
        self.assertEqual(order.service_city_id, self.service_city.id)
        self.assertIsNone(order.delivery_area_id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertIsNone(order.delivery_price)

        admin_token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        approve_response = self.client.post(
            f"/api/v1/admin/orders/{order.id}/approve/",
            format="json",
        )
        representative_ids = {
            item["representative_id"]
            for item in approve_response.data["available_representatives"]
        }
        self.assertIn(self.representative.id, representative_ids)
        self.assertNotIn(remote_representative.id, representative_ids)

        mismatch_response = self.client.patch(
            f"{ORDERS_BASE}/{order.id}/assignment/",
            {"representative_id": remote_representative.id},
            format="json",
        )
        self.assertEqual(mismatch_response.status_code, status.HTTP_400_BAD_REQUEST)

        assign_response = self.client.patch(
            f"{ORDERS_BASE}/{order.id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)

        courier_token = RefreshToken.for_user(self.representative).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {courier_token}")
        courier_list = self.client.get("/api/v1/courier/orders/")

        self.assertEqual(courier_list.status_code, status.HTTP_200_OK)
        self.assertEqual(courier_list.data[0]["id"], order.id)
        self.assertEqual(
            courier_list.data[0]["delivery_address"]["manual_area"],
            "منطقة غير مضافة",
        )

    def test_client_create_general_order_uses_default_manual_address(self):
        self.set_customer_region(User.MarketRegionMode.GENERAL)
        general_address = self.create_general_address(
            manual_city="القاهرة",
            manual_area="مصر الجديدة",
            details="شارع الثورة بجوار بنزينة التعاون",
            is_default=True,
        )
        self.second_market.scope = Market.Scope.GENERAL
        self.second_market.save(update_fields=["scope"])
        self.second_market.delivery_areas.clear()
        self.second_market.service_cities.clear()
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "payment_method": "cash_on_delivery",
                "items": [
                    {
                        "variant_id": self.second_variant.id,
                        "quantity": 1,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data[0]["id"])
        self.assertEqual(order.order_scope, Order.Scope.GENERAL)
        self.assertEqual(order.delivery_address_id, general_address.id)
        self.assertIsNone(order.service_city_id)
        self.assertIsNone(order.delivery_area_id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertIsNone(order.delivery_price)
        self.assertEqual(order.total_price, Decimal("700.00"))

    def test_general_manual_cairo_multi_market_create_has_no_fixed_delivery(self):
        self.make_general_market_region()
        self.second_market.scope = Market.Scope.GENERAL
        self.second_market.save(update_fields=["scope"])
        self.second_market.delivery_areas.clear()
        self.second_market.service_cities.clear()
        general_address = self.create_general_address(
            manual_city="القاهرة",
            manual_area="مصر الجديدة",
            details="شارع الثورة بجوار بنزينة التعاون",
            is_default=True,
        )
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "address_id": general_address.id,
                "payment_method": "cash_on_delivery",
                "items": [
                    {"variant_id": self.variant.id, "quantity": 1},
                    {"variant_id": self.second_variant.id, "quantity": 1},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(len(response.data), 1)
        order = Order.objects.get(id=response.data[0]["id"])
        self.assertEqual(order.order_scope, Order.Scope.GENERAL)
        self.assertEqual(order.delivery_address_id, general_address.id)
        self.assertIsNone(order.service_city_id)
        self.assertIsNone(order.delivery_area_id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertIsNone(order.delivery_price)
        self.assertEqual(order.total_price, Decimal("1200.00"))
        self.assertEqual(order.market_sections.count(), 2)
        self.assertTrue(response.data[0]["is_multi_market"])
        self.assertEqual(response.data[0]["market_count"], 2)
        self.assertEqual(
            response.data[0]["delivery_address"]["manual_city"],
            "القاهرة",
        )
        self.assertEqual(
            response.data[0]["delivery_address"]["manual_area"],
            "مصر الجديدة",
        )

    def test_general_manual_cairo_rejects_service_city_market_and_offer(self):
        self.set_customer_region(User.MarketRegionMode.GENERAL)
        general_address = self.create_general_address(
            manual_city="القاهرة",
            manual_area="مصر الجديدة",
            is_default=True,
        )
        self.authenticate_customer()

        market_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": general_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )
        offer_response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": general_address.id,
                "offers": [{"offer_id": self.offer.id}],
            },
            format="json",
        )

        self.assertEqual(market_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            market_response.data["items"][0],
            "لا يمكن دمج محلات عامة مع محلات مدينة في نفس الطلب",
        )
        self.assertEqual(offer_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            offer_response.data["offers"][0],
            "لا يمكن استخدام عرض مدينة داخل طلب عام",
        )

    def test_general_manual_address_allows_preview_with_null_delivery_price(self):
        self.customer.market_region_mode = User.MarketRegionMode.GENERAL
        self.customer.market_region_service_city = None
        self.customer.market_region_updated_at = timezone.now()
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.market.scope = Market.Scope.GENERAL
        self.market.save(update_fields=["scope"])
        self.market.service_cities.clear()
        self.market.delivery_areas.clear()
        self.offer.show_in_general = True
        self.offer.save(update_fields=["show_in_general"])
        self.offer.service_cities.clear()
        general_address = Address.objects.create(
            user=self.customer,
            name="General Home",
            manual_city="Mansoura",
            manual_area="University district",
            delivery_type=Address.DeliveryType.DELIVERY,
            is_default=True,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": general_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        group = response.data["market_groups"][0]
        self.assertTrue(group["delivery_available"])
        self.assertIsNone(group["service_city"])
        self.assertIsNone(group["delivery_area"])
        self.assertIsNone(group["delivery_price"])
        self.assertEqual(group["delivery_type"], Order.DeliveryType.DELIVERY)
        self.assertEqual(
            group["delivery_message"],
            "Delivery price will be determined later.",
        )
        self.assertIsNone(group["pricing"]["delivery_price"])
        self.assertEqual(group["pricing"]["market_total"], "500.00")
        self.assertEqual(response.data["service_city"], None)
        self.assertEqual(response.data["summary"]["delivery_total"], "0.00")
        self.assertEqual(response.data["summary"]["grand_total"], "500.00")
        self.assertEqual(
            response.data["selected_address"]["manual_city"],
            "Mansoura",
        )
        self.assertEqual(
            response.data["selected_address"]["manual_area"],
            "University district",
        )

    def test_service_city_region_rejects_address_from_another_city(self):
        other_city = ServiceCity.objects.create(name="Giza")
        other_area = DeliveryArea.objects.create(
            service_city=other_city,
            name="Dokki",
            delivery_price=Decimal("80.00"),
        )
        other_address = Address.objects.create(
            user=self.customer,
            name="Giza Home",
            service_city=other_city,
            delivery_area=other_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": other_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assert_address_region_mismatch(response)

    def test_service_city_region_rejects_general_address(self):
        general_address = self.create_general_address()
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": general_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assert_address_region_mismatch(response)

    def test_general_region_rejects_service_city_address(self):
        self.make_general_market_region()
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": self.address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assert_address_region_mismatch(response)

    def test_service_city_region_accepts_same_city_address(self):
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": self.address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["selected_address"]["id"], self.address.id)

    def test_general_create_rejects_service_city_address(self):
        self.make_general_market_region()
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "address_id": self.address.id,
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assert_address_region_mismatch(response)
        self.assertFalse(Order.objects.exists())

    def test_inactive_address_is_rejected_for_preview(self):
        self.address.is_active = False
        self.address.save(update_fields=["is_active"])
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": self.address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assert_address_region_mismatch(response)

    def test_general_region_uses_default_manual_address_for_logistics(self):
        self.make_general_market_region()
        general_address = self.create_general_address(is_default=True)
        self.address.is_default = False
        self.address.save(update_fields=["is_default"])
        self.authenticate_customer()

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {"items": [{"variant_id": self.variant.id, "quantity": 1}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["selected_address"]["id"], general_address.id)
        self.assertIsNone(response.data["service_city"])
        self.assertEqual(response.data["summary"]["delivery_total"], "0.00")
        self.assertIsNone(response.data["market_groups"][0]["delivery_area"])

    def test_general_manual_address_allows_create_with_null_service_city(self):
        self.customer.market_region_mode = User.MarketRegionMode.GENERAL
        self.customer.market_region_service_city = None
        self.customer.market_region_updated_at = timezone.now()
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.market.scope = Market.Scope.GENERAL
        self.market.save(update_fields=["scope"])
        self.market.service_cities.clear()
        self.market.delivery_areas.clear()
        general_address = Address.objects.create(
            user=self.customer,
            name="General Home",
            manual_city="Mansoura",
            manual_area="University district",
            delivery_type=Address.DeliveryType.DELIVERY,
            is_default=True,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "address_id": general_address.id,
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(id=response.data[0]["id"])
        self.assertEqual(order.delivery_address_id, general_address.id)
        self.assertIsNone(order.service_city_id)
        self.assertIsNone(order.delivery_area_id)
        self.assertIsNone(order.delivery_price)
        self.assertEqual(order.delivery_type, Order.DeliveryType.DELIVERY)
        self.assertEqual(order.total_price, Decimal("500.00"))
        self.assertIsNone(response.data[0]["service_city"])
        self.assertIsNone(response.data[0]["delivery_area"])
        self.assertIsNone(response.data[0]["delivery_price"])
        self.assertEqual(
            response.data[0]["delivery_address"]["manual_city"],
            "Mansoura",
        )

        remote_city = ServiceCity.objects.create(
            name="Remote Courier City",
            delivery_price=Decimal("90.00"),
        )
        remote_area = DeliveryArea.objects.create(
            service_city=remote_city,
            name="Remote Courier Area",
            delivery_price=Decimal("90.00"),
        )
        remote_representative = User.objects.create_user(
            username="general-remote-representative",
            email="general-remote-representative@example.com",
            phone="+213555700006",
            password="Password1!",
            role=User.Role.REPRESENTATIVE,
        )
        CourierProfile.objects.create(
            user=remote_representative,
            vehicle_type="Motorcycle",
            plate_number="GEN-REMOTE-1",
            delivery_area=remote_area,
            service_city=remote_city,
        )

        admin_token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        detail_response = self.client.get(f"{ORDERS_BASE}/{order.id}/")
        approve_response = self.client.post(
            f"/api/v1/admin/orders/{order.id}/approve/",
            format="json",
        )
        representatives_response = self.client.get(
            f"/api/v1/admin/orders/{order.id}/service-city-representatives/"
        )
        assignment_response = self.client.patch(
            f"{ORDERS_BASE}/{order.id}/assignment/",
            {"representative_id": remote_representative.id},
            format="json",
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(detail_response.data["service_city"])
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(approve_response.data["service_city"])
        self.assertEqual(
            {
                item["representative_id"]
                for item in approve_response.data["available_representatives"]
            },
            {self.representative.id, remote_representative.id},
        )
        self.assertEqual(representatives_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(representatives_response.data["service_city"])
        self.assertEqual(
            {
                item["representative_id"]
                for item in representatives_response.data["representatives"]
            },
            {self.representative.id, remote_representative.id},
        )
        self.assertEqual(
            assignment_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            assignment_response.data["order"]["assigned_representative_id"],
            remote_representative.id,
        )

    def test_general_manual_preview_rejects_other_users_address(self):
        self.customer.market_region_mode = User.MarketRegionMode.GENERAL
        self.customer.market_region_service_city = None
        self.customer.market_region_updated_at = timezone.now()
        self.customer.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.market.scope = Market.Scope.GENERAL
        self.market.save(update_fields=["scope"])
        other_address = Address.objects.create(
            user=self.other_customer,
            name="Other General Home",
            manual_city="Mansoura",
            manual_area="University district",
            delivery_type=Address.DeliveryType.DELIVERY,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            f"{ORDERS_BASE}/preview/",
            {
                "address_id": other_address.id,
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address_id", response.data)

    def test_service_city_review_assignment_and_courier_flow(self):
        remote_city = ServiceCity.objects.create(
            name="Cairo",
            delivery_price=Decimal("90.00"),
        )
        remote_area = DeliveryArea.objects.create(
            service_city=remote_city,
            name="Cairo Center",
            center_latitude=Decimal("30.0444000"),
            center_longitude=Decimal("31.2357000"),
            radius_km=Decimal("5.00"),
            delivery_price=Decimal("90.00"),
        )
        remote_representative = User.objects.create_user(
            username="cairo-representative",
            email="cairo-representative@example.com",
            phone="+213555700005",
            password="Password1!",
            role=User.Role.REPRESENTATIVE,
        )
        CourierProfile.objects.create(
            user=remote_representative,
            vehicle_type="Motorcycle",
            plate_number="CAI-1",
            delivery_area=remote_area,
            service_city=remote_city,
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        create_response = self.client.post(
            f"{ORDERS_BASE}/create/",
            {
                "payment_method": "cash_on_delivery",
                "items": [{"variant_id": self.variant.id, "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        order_id = create_response.data[0]["id"]
        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.service_city_id, self.service_city.id)
        self.assertEqual(order.delivery_area_id, self.delivery_area.id)
        self.assertEqual(order.delivery_type, Order.DeliveryType.FIXED_AREA)
        self.assertEqual(order.delivery_price, self.delivery_area.delivery_price)
        self.assertEqual(order.review_status, Order.ReviewStatus.PENDING_REVIEW)

        admin_token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        blocker_response = self.client.get("/api/v1/admin/order-review/blocker/")
        self.assertEqual(blocker_response.status_code, status.HTTP_200_OK)
        self.assertTrue(blocker_response.data["blocked"])
        self.assertEqual(blocker_response.data["pending_count"], 1)
        self.assertEqual(blocker_response.data["orders"][0]["id"], order_id)

        approve_response = self.client.post(
            f"/api/v1/admin/orders/{order_id}/approve/",
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        representative_ids = {
            item["representative_id"]
            for item in approve_response.data["available_representatives"]
        }
        self.assertIn(self.representative.id, representative_ids)
        self.assertNotIn(remote_representative.id, representative_ids)

        mismatch_response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": remote_representative.id},
            format="json",
        )
        self.assertEqual(mismatch_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            mismatch_response.data["representative_id"],
            "هذا المندوب لا يعمل في نفس مدينة الطلب.",
        )

        assign_response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)
        self.assertEqual(assign_response.data["order"]["status"], Order.Status.ASSIGNED)

        courier_token = RefreshToken.for_user(self.representative).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {courier_token}")
        courier_list = self.client.get("/api/v1/courier/orders/")
        self.assertEqual(courier_list.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in courier_list.data], [order_id])

        remote_token = RefreshToken.for_user(remote_representative).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {remote_token}")
        remote_list = self.client.get("/api/v1/courier/orders/")
        self.assertEqual(remote_list.status_code, status.HTTP_200_OK)
        self.assertEqual(remote_list.data, [])
        remote_detail = self.client.get(f"/api/v1/courier/orders/{order_id}/")
        self.assertEqual(remote_detail.status_code, status.HTTP_404_NOT_FOUND)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {courier_token}")
        for next_status in (
            Order.Status.PICKED_UP,
            Order.Status.DELIVERED,
        ):
            status_response = self.client.patch(
                f"/api/v1/courier/orders/{order_id}/status/",
                {"status": next_status},
                format="json",
            )
            self.assertEqual(status_response.status_code, status.HTTP_200_OK)
            self.assertEqual(status_response.data["status"], next_status)
        order.refresh_from_db()
        self.assertIsNotNone(order.delivered_at)
        delivered_list = self.client.get("/api/v1/courier/orders/")
        self.assertEqual(delivered_list.status_code, status.HTTP_200_OK)
        self.assertEqual(
            delivered_list.data[0]["delivered_at"],
            order.delivered_at.isoformat().replace("+00:00", "Z"),
        )
        admin_status_notifications = Notification.objects.filter(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.ORDER_STATUS_CHANGED,
            order=order,
        ).order_by("id")
        self.assertEqual(
            [item.data["event"] for item in admin_status_notifications],
            ["courier_order_picked_up", "courier_order_delivered"],
        )
