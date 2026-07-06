from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.models import Count
from django.test import TestCase, override_settings
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
from notifications.models import Notification
from orders.models import Order, OrderItem, OrderMarketSection

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

    def create_section_order(
        self,
        *,
        user,
        market,
        order_status,
        total,
        created_at,
        sections,
    ):
        order = self.create_order(
            user=user,
            market=market,
            order_status=order_status,
            total=total,
            created_at=created_at,
        )
        for index, section_data in enumerate(sections):
            section = OrderMarketSection.objects.create(
                order=order,
                market=section_data["market"],
                subtotal_price=section_data["subtotal"],
                discount=section_data.get("discount", Decimal("0.00")),
                sort_order=index,
            )
            OrderItem.objects.bulk_create(
                OrderItem(
                    order=order,
                    section=section,
                    variant=variant,
                    quantity=quantity,
                    unit_price=unit_price,
                )
                for variant, quantity, unit_price in section_data.get("items", ())
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

    def test_overview_uses_to_day_for_orders_and_full_period_for_revenue_and_products(self):
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
                "total": 1,
                "completed": 1,
                "incomplete": 0,
                "completion_rate": 100.0,
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

    def test_active_orders_include_in_progress_statuses_and_exclude_terminal_statuses(self):
        picked_up = self.create_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.PICKED_UP,
            total=Decimal("40.00"),
            created_at=self.at("2026-05-12T10:00:00"),
        )
        on_the_way = self.create_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.ON_THE_WAY,
            total=Decimal("50.00"),
            created_at=self.at("2026-05-12T11:00:00"),
        )
        for terminal_status in (
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
            Order.Status.CANCELLED,
        ):
            self.create_order(
                user=self.client_user,
                market=self.main_market,
                order_status=terminal_status,
                total=Decimal("60.00"),
                created_at=self.at("2026-05-12T12:00:00"),
            )
        self.client.force_authenticate(self.admin)

        response = self.request_overview("2026-05-01", "2026-05-31")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_ids = {item["id"] for item in response.data["active_orders"]}
        self.assertEqual(active_ids, {picked_up.id, on_the_way.id})

    def test_active_orders_return_real_number_and_multi_market_fields(self):
        order = self.create_section_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.ON_THE_WAY,
            total=Decimal("120.00"),
            created_at=self.at("2026-05-14T09:00:00"),
            sections=(
                {
                    "market": self.second_market,
                    "subtotal": Decimal("60.00"),
                    "items": ((self.juice_variant, 1, Decimal("50.00")),),
                },
                {
                    "market": self.main_market,
                    "subtotal": Decimal("60.00"),
                    "items": ((self.apples_small, 1, Decimal("100.00")),),
                },
            ),
        )
        self.client.force_authenticate(self.admin)

        response = self.request_overview("2026-05-01", "2026-05-31")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_order = response.data["active_orders"][0]
        self.assertEqual(active_order["id"], order.id)
        self.assertEqual(active_order["number"], f"YM-20260514-{order.id:06d}")
        self.assertEqual(active_order["market_count"], 2)
        self.assertEqual(active_order["market_names_summary"], "Second Market, Yalla Market - Main")
        self.assertTrue(active_order["is_multi_market"])

    def test_active_orders_fall_back_to_legacy_market_without_sections(self):
        order = self.create_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.PENDING,
            total=Decimal("20.00"),
            created_at=self.at("2026-05-15T09:00:00"),
        )
        self.client.force_authenticate(self.admin)

        response = self.request_overview("2026-05-01", "2026-05-31")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_order = response.data["active_orders"][0]
        self.assertEqual(active_order["id"], order.id)
        self.assertEqual(active_order["market_count"], 1)
        self.assertEqual(active_order["market_names_summary"], "Yalla Market - Main")
        self.assertFalse(active_order["is_multi_market"])

    def test_top_shops_attribute_multi_market_sections_to_their_own_markets(self):
        self.create_section_order(
            user=self.client_user,
            market=self.main_market,
            order_status=Order.Status.DELIVERED,
            total=Decimal("250.00"),
            created_at=self.at("2026-06-03T10:00:00"),
            sections=(
                {
                    "market": self.main_market,
                    "subtotal": Decimal("120.00"),
                    "discount": Decimal("20.00"),
                    "items": ((self.apples_small, 2, Decimal("100.00")),),
                },
                {
                    "market": self.second_market,
                    "subtotal": Decimal("70.00"),
                    "discount": Decimal("10.00"),
                    "items": ((self.juice_variant, 3, Decimal("50.00")),),
                },
            ),
        )
        self.client.force_authenticate(self.admin)

        response = self.request_overview("2026-06-01", "2026-06-30")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shops = {shop["market_id"]: shop for shop in response.data["top_shops"]}
        self.assertEqual(shops[self.main_market.id]["orders_count"], 1)
        self.assertEqual(shops[self.main_market.id]["revenue"], "100.00")
        self.assertEqual(shops[self.main_market.id]["average_items_per_order"], 2.0)
        self.assertEqual(shops[self.second_market.id]["orders_count"], 1)
        self.assertEqual(shops[self.second_market.id]["revenue"], "60.00")
        self.assertEqual(shops[self.second_market.id]["average_items_per_order"], 3.0)

    def test_top_shops_include_legacy_orders_without_double_counting_sections(self):
        self.create_order(
            user=self.client_user,
            market=self.second_market,
            order_status=Order.Status.DELIVERED,
            total=Decimal("80.00"),
            created_at=self.at("2026-06-05T10:00:00"),
            items=((self.juice_variant, 4, Decimal("20.00")),),
        )
        self.create_section_order(
            user=self.client_user,
            market=self.second_market,
            order_status=Order.Status.DELIVERED,
            total=Decimal("500.00"),
            created_at=self.at("2026-06-06T10:00:00"),
            sections=(
                {
                    "market": self.main_market,
                    "subtotal": Decimal("100.00"),
                    "items": ((self.apples_small, 2, Decimal("50.00")),),
                },
            ),
        )
        self.client.force_authenticate(self.admin)

        response = self.request_overview("2026-06-01", "2026-06-30")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shops = {shop["market_id"]: shop for shop in response.data["top_shops"]}
        self.assertEqual(shops[self.second_market.id]["orders_count"], 1)
        self.assertEqual(shops[self.second_market.id]["revenue"], "80.00")
        self.assertEqual(shops[self.second_market.id]["average_items_per_order"], 4.0)
        self.assertEqual(shops[self.main_market.id]["orders_count"], 1)
        self.assertEqual(shops[self.main_market.id]["revenue"], "100.00")

    def test_overview_query_count_is_bounded(self):
        self.seed_dashboard_orders()
        self.client.force_authenticate(self.admin)

        with CaptureQueriesContext(connection) as queries:
            response = self.request_overview()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 12)


@override_settings(DEBUG=True)
class SeedDemoDataCommandTests(TestCase):
    def run_seed(self):
        call_command(
            "seed_demo_data",
            reset=True,
            yes_delete_all=True,
            no_media=True,
            quiet=True,
            verbosity=0,
        )

    def test_seed_demo_data_is_repeatable_and_creates_multi_market_sections(self):
        self.run_seed()
        first_counts = {
            "orders": Order.objects.count(),
            "sections": OrderMarketSection.objects.count(),
            "notifications": Notification.objects.count(),
        }

        self.run_seed()
        second_counts = {
            "orders": Order.objects.count(),
            "sections": OrderMarketSection.objects.count(),
            "notifications": Notification.objects.count(),
        }

        multi_market_orders = Order.objects.annotate(
            section_count=Count("market_sections")
        ).filter(section_count__gt=1)
        pending_review_orders = Order.objects.filter(
            review_status=Order.ReviewStatus.PENDING_REVIEW
        )

        self.assertEqual(first_counts, second_counts)
        self.assertFalse(User.objects.filter(phone__startswith="+213").exists())
        self.assertGreaterEqual(multi_market_orders.count(), 3)
        self.assertEqual(
            Order.objects.filter(market_sections__isnull=False).distinct().count(),
            Order.objects.count(),
        )
        self.assertFalse(
            Order.objects.filter(order_scope=Order.Scope.GENERAL)
            .exclude(
                service_city__isnull=True,
                delivery_area__isnull=True,
                delivery_type=Order.DeliveryType.DELIVERY,
                delivery_price__isnull=True,
            )
            .exists()
        )
        self.assertTrue(
            Order.objects.filter(
                order_scope=Order.Scope.GENERAL,
                service_city__isnull=True,
                delivery_area__isnull=True,
                delivery_address__manual_city="القاهرة",
                delivery_address__manual_area="مصر الجديدة",
                delivery_address__details="شارع الثورة بجوار بنزينة التعاون",
            )
            .annotate(section_count=Count("market_sections"))
            .filter(section_count__gt=1)
            .exists()
        )
        self.assertTrue(
            Order.objects.filter(
                order_scope=Order.Scope.SERVICE_CITY,
                service_city__name="القاهرة",
                delivery_area__name="السلام",
                delivery_type=Order.DeliveryType.FIXED_AREA,
            ).exists()
        )
        self.assertTrue(
            Order.objects.filter(
                order_scope=Order.Scope.SERVICE_CITY,
                service_city__name="القاهرة",
                delivery_area__isnull=True,
                delivery_type=Order.DeliveryType.DELIVERY,
                delivery_address__manual_area="منطقة غير مضافة",
            ).exists()
        )
        self.assertEqual(
            Notification.objects.filter(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.NEW_ORDER_REVIEW,
                is_blocking=True,
                is_resolved=False,
            ).count(),
            pending_review_orders.count(),
        )
