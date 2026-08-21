import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from accounts.models import CourierProfile, OTPCooldown, User
from catalog.models import (
    CategoryClassification,
    Product,
    ProductCategory,
    ProductVariant,
    StoreSubcategory,
)
from dashboard.models import DashboardSettings
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from notifications.models import ClientDevice, Notification
from offers.models import Offer
from orders.models import Order, OrderItem


class ClearDomainDataPreserveUsersTests(TestCase):
    def test_clear_preserves_only_core_user_accounts(self):
        city = ServiceCity.objects.create(name="Reset City")
        area = DeliveryArea.objects.create(
            service_city=city,
            name="Reset Area",
            delivery_price=Decimal("10.00"),
        )
        admin = User.objects.create_user(
            username="reset_admin",
            email="reset-admin@example.com",
            phone="+201000000401",
            password="Passw0rd!",
            role=User.Role.ADMIN,
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city=city,
            market_region_updated_at=timezone.now(),
        )
        courier = User.objects.create_user(
            username="reset_courier",
            email="reset-courier@example.com",
            phone="+201000000402",
            password="Passw0rd!",
            role=User.Role.REPRESENTATIVE,
        )
        CourierProfile.objects.create(
            user=courier,
            vehicle_type="Bike",
            plate_number="RESET-1",
            service_city=city,
            delivery_area=area,
        )
        Address.objects.create(
            user=admin,
            name="Reset address",
            service_city=city,
        )
        classification = MarketClassification.objects.create(name="Reset markets")
        market = Market.objects.create(
            classification=classification,
            name="Reset Market",
        )
        category_classification = CategoryClassification.objects.create(
            name="Reset catalog"
        )
        category = ProductCategory.objects.create(
            classification=category_classification,
            name="Reset Category",
        )
        subcategory = StoreSubcategory.objects.create(
            name_ar="قسم الاختبار",
            name_en="Reset subcategory",
        )
        product = Product.objects.create(
            market=market,
            category=category,
            subcategory=subcategory,
            name="Reset Product",
        )
        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("20.00"),
        )
        offer = Offer.objects.create(
            market=market,
            title="Reset Offer",
            discount=Decimal("5.00"),
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(days=1),
        )
        order = Order.objects.create(
            user=admin,
            market=market,
            payment_method="cash",
        )
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=1,
            unit_price=Decimal("20.00"),
        )
        Notification.objects.create(
            audience=Notification.Audience.ADMIN,
            type=Notification.Type.OFFER_CREATED,
            title="Reset",
            message="Reset",
            recipient=admin,
            offer=offer,
        )
        ClientDevice.objects.create(
            user=admin,
            token="reset-device-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        OTPCooldown.objects.create(
            purpose="password_reset",
            identifier=admin.email,
        )
        DashboardSettings.objects.create()
        password_hash = admin.password

        migration = importlib.import_module(
            "accounts.migrations.0012_clear_domain_data_preserve_users"
        )
        schema_editor = type(
            "SchemaEditorStub",
            (),
            {"connection": connection},
        )()
        migration.clear_domain_data_preserve_users(apps, schema_editor)

        self.assertEqual(User.objects.count(), 2)
        admin.refresh_from_db()
        self.assertEqual(admin.password, password_hash)
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertIsNone(admin.market_region_mode)
        self.assertIsNone(admin.market_region_service_city_id)
        for app_label, model_name in migration.DELETE_ORDER:
            model = apps.get_model(app_label, model_name)
            self.assertEqual(
                model.objects.count(),
                0,
                f"{app_label}.{model_name} was not cleared",
            )
