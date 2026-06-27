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
from accounts.models import CourierProfile
from locations.models import Address, DeliveryArea

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
        self.admin = User.objects.create_user(
            username="orders_admin",
            email="orders-admin@example.com",
            phone="+213555300003",
            password="Password1!",
            role=User.Role.ADMIN,
        )
        self.representative = User.objects.create_user(
            username="orders_courier",
            email="orders-courier@example.com",
            phone="+213555300004",
            password="Password1!",
            role=User.Role.REPRESENTATIVE,
        )
        self.area = DeliveryArea.objects.create(
            name="Order Area",
            delivery_price=Decimal("20.00"),
            center_latitude=Decimal("30.0000000"),
            center_longitude=Decimal("31.0000000"),
            radius_km=Decimal("10.00"),
        )
        CourierProfile.objects.create(
            user=self.representative,
            vehicle_type="Motorcycle",
            plate_number="ORDER-123",
            delivery_area=self.area,
            max_active_orders=1,
        )
        self.address = Address.objects.create(
            user=self.user,
            name="Home",
            latitude=Decimal("30.1000000"),
            longitude=Decimal("31.1000000"),
            is_default=True,
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

    def test_admin_assigns_ready_order_and_representative_delivers_it(self):
        self.order.status = Order.Status.READY
        self.order.delivery_address = self.address
        self.order.save(update_fields=["status", "delivery_address"])

        admin_refresh = RefreshToken.for_user(self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {admin_refresh.access_token}"
        )
        assignment = self.client.patch(
            f"{ORDERS_BASE}/{self.order.id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(assignment.status_code, status.HTTP_200_OK)
        self.assertEqual(
            assignment.data["assigned_representative"]["id"],
            self.representative.id,
        )

        courier_refresh = RefreshToken.for_user(self.representative)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {courier_refresh.access_token}"
        )
        assigned = self.client.get(f"{ORDERS_BASE}/assigned/")
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in assigned.data], [self.order.id])

        missing_proof = self.client.post(
            f"{ORDERS_BASE}/{self.order.id}/deliver/",
            {},
            format="multipart",
        )
        self.assertEqual(missing_proof.status_code, status.HTTP_400_BAD_REQUEST)

        delivered = self.client.post(
            f"{ORDERS_BASE}/{self.order.id}/deliver/",
            {"note": "Delivered to the customer."},
            format="multipart",
        )
        self.assertEqual(delivered.status_code, status.HTTP_200_OK)
        self.assertEqual(delivered.data["status"], Order.Status.DELIVERED)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivered_at)

    def test_assignment_requires_ready_order_address_and_capacity(self):
        admin_refresh = RefreshToken.for_user(self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {admin_refresh.access_token}"
        )
        not_ready = self.client.patch(
            f"{ORDERS_BASE}/{self.order.id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(not_ready.status_code, status.HTTP_400_BAD_REQUEST)

        self.order.status = Order.Status.READY
        self.order.delivery_address = None
        self.order.save(update_fields=["status", "delivery_address"])
        missing_address = self.client.patch(
            f"{ORDERS_BASE}/{self.order.id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(missing_address.status_code, status.HTTP_400_BAD_REQUEST)

        self.order.delivery_address = self.address
        self.order.save(update_fields=["delivery_address"])
        first = self.client.patch(
            f"{ORDERS_BASE}/{self.order.id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second_order = self._create_order(self.user, "Second ready order")
        second_order.status = Order.Status.READY
        second_order.delivery_address = self.address
        second_order.save(update_fields=["status", "delivery_address"])
        over_capacity = self.client.patch(
            f"{ORDERS_BASE}/{second_order.id}/assignment/",
            {"representative_id": self.representative.id},
            format="json",
        )
        self.assertEqual(over_capacity.status_code, status.HTTP_400_BAD_REQUEST)

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
            delivery_address=self.address if user == self.user else None,
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            quantity=2,
            unit_price=Decimal("900.00"),
        )
        return order
