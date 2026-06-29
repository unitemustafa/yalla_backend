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
from locations.models import Address
from markets.models import Market, MarketClassification
from offers.models import Offer

from .models import Order

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
        self.address = Address.objects.create(
            user=self.customer,
            name="Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0420000"),
        )
        market_classification = MarketClassification.objects.create(name="Food")
        self.market = Market.objects.create(
            classification=market_classification,
            name="Order Market",
        )
        category_classification = CategoryClassification.objects.create(name="Meals")
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Main Meals",
        )
        product = Product.objects.create(
            market=self.market,
            category=category,
            name="Burger",
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("500.00"),
            sku="BURGER-1",
        )
        now = timezone.now()
        self.offer = Offer.objects.create(
            market=self.market,
            title="Lunch",
            discount=Decimal("50.00"),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
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
