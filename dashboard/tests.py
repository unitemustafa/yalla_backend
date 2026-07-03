from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import (
    CategoryClassification,
    Product,
    ProductCategory,
    ProductVariant,
)
from locations.models import DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from orders.models import Order, OrderItem

User = get_user_model()
OVERVIEW_URL = "/api/v1/dashboard/overview/"


@override_settings(TIME_ZONE="UTC", USE_TZ=True)
class DashboardOverviewAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="dashboard_admin",
            email="dashboard-admin@example.com",
            phone="+213555800001",
            password="Password1!",
            role=User.Role.ADMIN,
        )
        self.client_user = User.objects.create_user(
            username="dashboard_client",
            first_name="New",
            email="dashboard-client@example.com",
            phone="+213555800002",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        self.returning_user = User.objects.create_user(
            username="returning_client",
            first_name="Returning",
            email="returning-client@example.com",
            phone="+213555800003",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        city = ServiceCity.objects.create(
            name="Algiers",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("30.00"),
            delivery_price=Decimal("100.00"),
        )
        self.city = city
        area = DeliveryArea.objects.create(
            service_city=city,
            name="Central",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0420000"),
            radius_km=Decimal("10.00"),
            delivery_price=Decimal("100.00"),
        )
        market_classification = MarketClassification.objects.create(name="Food")
        self.main_market = Market.objects.create(
            classification=market_classification,
            name="Yalla Market",
            branch="Main",
        )
        self.main_market.delivery_areas.add(area)
        self.main_market.service_cities.add(city)
        self.second_market = Market.objects.create(
            classification=market_classification,
            name="Second Market",
        )
        self.second_market.service_cities.add(city)
        category_classification = CategoryClassification.objects.create(name="Meals")
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Fresh Food",
        )
        self.apples = Product.objects.create(
            market=self.main_market,
            category=category,
            name="Red Apples",
        )
        self.apples_small = ProductVariant.objects.create(
            product=self.apples,
            price=Decimal("100.00"),
            sku="APPLE-S",
        )
        self.apples_large = ProductVariant.objects.create(
            product=self.apples,
            price=Decimal("50.00"),
            sku="APPLE-L",
        )
        self.juice = Product.objects.create(
            market=self.second_market,
            category=category,
            name="Orange Juice",
        )
        self.juice_variant = ProductVariant.objects.create(
            product=self.juice,
            price=Decimal("50.00"),
            sku="JUICE",
        )

    @staticmethod
    def at(value):
        return timezone.make_aware(datetime.fromisoformat(value))

    def create_order(self, *, user, market, order_status, total, created_at, items=()):
        order = Order.objects.create(
            user=user,
            market=market,
            service_city=market.service_cities.first(),
            payment_method="cash",
            status=order_status,
            subtotal_price=total,
            total_price=total,
        )
        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                variant=variant,
                quantity=quantity,
                unit_price=unit_price,
            )
            for variant, quantity, unit_price in items
        )
        return order

    def seed_dashboard_orders(self):
        self.create_order(
            user=self.returning_user,
            market=self.main_market,
            order_status=Order.Status.DELIVERED,
            total=Decimal("10.00"),
            created_at=self.at("2026-04-30T23:59:59"),
        )
        first = self.create_order(
            user=self.returning_user,
            market=self.main_market,
            order_status=Order.Status.DELIVERED,
            total=Decimal("300.00"),
            created_at=self.at("2026-05-01T00:00:00"),
            items=(
                (self.apples_small, 2, Decimal("100.00")),
                (self.apples_large, 1, Decimal("50.00")),
            ),
        )
        last = self.create_order(
            user=self.client_user,
            market=self.second_market,
            order_status=Order.Status.DELIVERED,
            total=Decimal("200.00"),
            created_at=self.at("2026-05-22T23:59:59"),
            items=((self.juice_variant, 4, Decimal("50.00")),),
        )
        older_active = self.create_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.CONFIRMED,
            total=Decimal("80.00"),
            created_at=self.at("2026-05-10T10:00:00"),
        )
        newer_active = self.create_order(
            user=self.returning_user,
            market=self.main_market,
            order_status=Order.Status.PENDING,
            total=Decimal("100.00"),
            created_at=self.at("2026-05-20T10:00:00"),
        )
        self.create_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.CANCELLED,
            total=Decimal("20.00"),
            created_at=self.at("2026-05-15T10:00:00"),
        )
        return first, last, older_active, newer_active

    def request_overview(self, from_date="2026-05-01", to_date="2026-05-22"):
        return self.client.get(
            OVERVIEW_URL,
            {"from": from_date, "to": to_date},
        )

    def test_overview_requires_authentication(self):
        response = self.request_overview()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_overview_requires_admin_role(self):
        self.client.force_authenticate(self.client_user)
        response = self.request_overview()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_missing_and_reversed_dates_are_rejected(self):
        self.client.force_authenticate(self.admin)

        missing = self.client.get(OVERVIEW_URL)
        malformed = self.request_overview(from_date="not-a-date")
        reversed_range = self.request_overview(
            from_date="2026-05-23",
            to_date="2026-05-22",
        )

        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(malformed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(reversed_range.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_data_range_returns_zero_sections_and_empty_lists(self):
        self.client.force_authenticate(self.admin)

        response = self.request_overview("2030-01-01", "2030-01-31")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["revenue"], {"total": "0.00", "percentage": 0.0})
        self.assertEqual(response.data["orders"]["total"], 0)
        self.assertEqual(response.data["customers"]["new"], 0)
        self.assertEqual(response.data["top_products"], [])
        self.assertEqual(response.data["active_orders"], [])
        self.assertEqual(response.data["top_shops"], [])

    def test_overview_aggregates_inclusive_range_and_rankings(self):
        first, last, older_active, newer_active = self.seed_dashboard_orders()
        self.client.force_authenticate(self.admin)

        response = self.request_overview()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["range"],
            {"from": "2026-05-01", "to": "2026-05-22", "timezone": "UTC"},
        )
        self.assertEqual(response.data["currency"], "EGP")
        self.assertEqual(response.data["revenue"], {"total": "500.00", "percentage": 71.4})
        self.assertEqual(
            response.data["orders"],
            {
                "total": 5,
                "completed": 2,
                "incomplete": 3,
                "completion_rate": 40.0,
            },
        )
        self.assertEqual(
            response.data["customers"],
            {"new": 1, "returning": 1, "return_rate": 50.0},
        )
        self.assertEqual(response.data["top_products"][0]["product_id"], self.apples.id)
        self.assertEqual(response.data["top_products"][0]["revenue"], "250.00")
        self.assertEqual(response.data["top_products"][0]["quantity_sold"], 3)
        self.assertEqual(response.data["top_products"][0]["orders_count"], 1)
        self.assertEqual(
            [item["id"] for item in response.data["active_orders"]],
            [newer_active.id, older_active.id],
        )
        self.assertNotIn(
            first.id,
            [item["id"] for item in response.data["active_orders"]],
        )
        self.assertNotIn(
            last.id,
            [item["id"] for item in response.data["active_orders"]],
        )
        self.assertEqual(response.data["top_shops"][0]["market_id"], self.main_market.id)
        self.assertEqual(response.data["top_shops"][0]["revenue"], "300.00")
        self.assertEqual(response.data["top_shops"][0]["zone"], "Algiers")
        self.assertEqual(response.data["top_shops"][0]["average_items_per_order"], 3.0)

    def test_overview_query_count_is_bounded(self):
        self.seed_dashboard_orders()
        self.client.force_authenticate(self.admin)

        with CaptureQueriesContext(connection) as queries:
            response = self.request_overview()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 12)
