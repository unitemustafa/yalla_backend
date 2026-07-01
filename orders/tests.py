from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import (
    CategoryClassification,
    Product,
    ProductCategory,
    ProductVariant,
)
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from offers.models import Offer

from .models import Order, OrderItem, OrderOffer

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
        self.address = Address.objects.create(
            user=self.customer,
            name="Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0420000"),
        )
        service_city = ServiceCity.objects.create(
            name="Algiers",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("20.00"),
        )
        self.delivery_area = DeliveryArea.objects.create(
            service_city=service_city,
            name="Central Algiers",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("5.00"),
            delivery_price=Decimal("120.00"),
        )
        market_classification = MarketClassification.objects.create(name="Food")
        self.market = Market.objects.create(
            classification=market_classification,
            name="Order Market",
        )
        self.market.delivery_areas.add(self.delivery_area)
        self.second_market = Market.objects.create(
            classification=market_classification,
            name="Second Order Market",
        )
        self.second_market.delivery_areas.add(self.delivery_area)
        category_classification = CategoryClassification.objects.create(name="Meals")
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Main Meals",
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
            title="Lunch",
            discount=Decimal("10.00"),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        self.offer.products.set([self.product])
        self.second_offer = Offer.objects.create(
            market=self.second_market,
            title="Pizza Deal",
            discount=Decimal("20.00"),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        self.second_offer.products.set([self.second_product])
        token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def payload(self):
        return {
            "user_id": self.customer.id,
            "delivery_address_id": self.address.id,
            "assigned_representative_id": None,
            "market_id": self.market.id,
            "payment_method": "cash_on_delivery",
            "discount": "50.00",
            "description": "Call on arrival",
            "status": Order.Status.CONFIRMED,
            "delivery_price": "100.00",
            "subtotal_price": "1000.00",
            "total_price": "1050.00",
            "assigned_at": None,
            "delivered_at": None,
            "delivery_note": "",
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
        self.assertEqual(update_response.data["description"], "Updated description")

    def test_assignment_sets_order_status_to_ready(self):
        order_id = self.create_order().data["id"]

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.READY)
        self.assertEqual(
            response.data["assigned_representative_id"],
            self.representative.id,
        )
        self.assertIsNotNone(response.data["assigned_at"])

    def test_status_api_changes_status(self):
        order_id = self.create_order().data["id"]

        response = self.client.patch(
            f"{ORDERS_BASE}/{order_id}/status/",
            {"status": Order.Status.UNDER_PREPARATION},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.UNDER_PREPARATION)

    def test_delete_cancels_order_without_removing_it(self):
        order_id = self.create_order().data["id"]

        response = self.client.delete(f"{ORDERS_BASE}/{order_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Order.Status.CANCELLED)
        self.assertTrue(Order.objects.filter(pk=order_id).exists())

    def test_client_can_list_only_their_orders(self):
        own_order_id = self.create_order().data["id"]
        other_order = Order.objects.create(
            user=self.other_customer,
            market=self.market,
            payment_method="cash_on_delivery",
            status=Order.Status.PENDING,
            delivery_price=Decimal("100.00"),
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("600.00"),
        )
        token = RefreshToken.for_user(self.customer).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get(f"{ORDERS_BASE}/my/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [own_order_id])
        self.assertNotIn(other_order.id, [item["id"] for item in response.data])

    def test_client_order_list_supports_status_filter(self):
        confirmed_order_id = self.create_order().data["id"]
        Order.objects.create(
            user=self.customer,
            market=self.market,
            payment_method="cash_on_delivery",
            status=Order.Status.PENDING,
            delivery_price=Decimal("100.00"),
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("600.00"),
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
        self.assertEqual(len(response.data["market_groups"]), 2)

        first_market = response.data["market_groups"][0]
        second_market = response.data["market_groups"][1]
        self.assertEqual(first_market["market"]["id"], self.market.id)
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
        self.assertEqual(second_market["pricing"]["delivery_price"], "120.00")
        self.assertEqual(second_market["pricing"]["market_total"], "680.00")

        self.assertEqual(response.data["summary"]["subtotal"], "1700.00")
        self.assertEqual(response.data["summary"]["discount_total"], "240.00")
        self.assertEqual(response.data["summary"]["delivery_total"], "240.00")
        self.assertEqual(response.data["summary"]["grand_total"], "1700.00")

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

    def test_client_create_order_creates_one_order_per_market(self):
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
        self.assertEqual(len(response.data), 2)
        first_order = Order.objects.get(id=response.data[0]["id"])
        second_order = Order.objects.get(id=response.data[1]["id"])
        self.assertEqual(first_order.market_id, self.market.id)
        self.assertEqual(first_order.delivery_address_id, self.address.id)
        self.assertEqual(first_order.subtotal_price, Decimal("1000.00"))
        self.assertEqual(first_order.discount, Decimal("100.00"))
        self.assertEqual(first_order.delivery_price, Decimal("120.00"))
        self.assertEqual(first_order.total_price, Decimal("1020.00"))
        self.assertEqual(
            OrderItem.objects.get(order=first_order).variant_id,
            self.variant.id,
        )
        self.assertEqual(
            OrderOffer.objects.get(order=first_order).discount_amount,
            Decimal("100.00"),
        )

        self.assertEqual(second_order.market_id, self.second_market.id)
        self.assertEqual(second_order.subtotal_price, Decimal("700.00"))
        self.assertEqual(second_order.discount, Decimal("140.00"))
        self.assertEqual(second_order.delivery_price, Decimal("120.00"))
        self.assertEqual(second_order.total_price, Decimal("680.00"))

    def test_client_create_order_requires_market_delivery_coverage(self):
        self.second_market.delivery_areas.clear()
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

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address", response.data)
        self.assertFalse(
            Order.objects.filter(
                user=self.customer,
                market=self.second_market,
            ).exists()
        )
