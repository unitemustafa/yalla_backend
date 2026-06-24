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
from markets.models import Market, MarketClassification
from offers.models import Offer

from .models import Order, OrderItem, OrderOffer

User = get_user_model()
ORDERS_BASE = "/api/v1/orders"


class UserOrdersAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="orders_user",
            email="orders@example.com",
            phone="+213555300001",
            password="Password1!",
        )
        self.other_user = User.objects.create_user(
            username="other_orders_user",
            email="other-orders@example.com",
            phone="+213555300002",
            password="Password1!",
        )
        market_classification = MarketClassification.objects.create(
            name="Restaurants"
        )
        self.market = Market.objects.create(
            classification=market_classification,
            name="Order Market",
            branch="Main",
        )
        category_classification = CategoryClassification.objects.create(
            name="Food"
        )
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Meals",
        )
        product = Product.objects.create(
            market=self.market,
            category=category,
            name="Order Product",
            description="Order product description",
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("900.00"),
            sku="ORDER-1",
        )
        self.order = self._create_order(self.user, "Primary order")
        self.other_order = self._create_order(self.other_user, "Other order")

        now = timezone.now()
        offer = Offer.objects.create(
            market=self.market,
            title="Order Offer",
            description="Order offer description",
            type=Offer.OfferType.DISCOUNT,
            discount=Decimal("50.00"),
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            status=Offer.Status.ACTIVE,
        )
        OrderOffer.objects.create(
            order=self.order,
            offer=offer,
            discount_amount=Decimal("50.00"),
        )

    def authenticate(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def test_orders_require_authentication(self):
        response = self.client.get(f"{ORDERS_BASE}/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_orders_return_only_authenticated_users_orders(self):
        self.authenticate()

        response = self.client.get(f"{ORDERS_BASE}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.order.id)
        self.assertEqual(response.data[0]["description"], "Primary order")
        self.assertEqual(response.data[0]["market"]["id"], self.market.id)
        self.assertEqual(response.data[0]["items"][0]["quantity"], 2)
        self.assertEqual(
            response.data[0]["items"][0]["variant"]["product"]["name"],
            "Order Product",
        )
        self.assertEqual(response.data[0]["offers"][0]["title"], "Order Offer")

    def _create_order(self, user, description):
        order = Order.objects.create(
            user=user,
            market=self.market,
            payment_method="cash",
            discount=Decimal("0.00"),
            description=description,
            status=Order.Status.PENDING,
            delivery_price=Decimal("250.00"),
            subtotal_price=Decimal("1800.00"),
            total_price=Decimal("2050.00"),
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            quantity=2,
            unit_price=Decimal("900.00"),
        )
        return order
