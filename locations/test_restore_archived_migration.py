import importlib
from datetime import timedelta

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product, StoreSubcategory
from locations.models import DeliveryArea, ServiceCity, ShippingCompany
from markets.models import Market, MarketClassification
from offers.models import Offer


class RestoreArchivedRecordsMigrationTests(TestCase):
    def test_archived_records_return_disabled_to_normal_lists(self):
        archived_at = timezone.now()
        classification = MarketClassification.objects.create(name="Migration category")
        subcategory = StoreSubcategory.objects.create(name_ar="Migration subcategory")
        market = Market.objects.create(
            classification=classification,
            name="Migration market",
            archived_at=archived_at,
        )
        product = Product.objects.create(
            market=market,
            subcategory=subcategory,
            name="Migration product",
            archived_at=archived_at,
        )
        city = ServiceCity.objects.create(name="Migration city", archived_at=archived_at)
        area = DeliveryArea.objects.create(
            service_city=city,
            name="Migration area",
            delivery_price=0,
            archived_at=archived_at,
        )
        company = ShippingCompany.objects.create(
            name="Migration shipping",
            archived_at=archived_at,
        )
        offer = Offer.objects.create(
            title="Migration offer",
            discount=0,
            start_time=archived_at,
            end_time=archived_at + timedelta(days=1),
            archived_at=archived_at,
        )
        migration = importlib.import_module("locations.migrations.0010_restore_archived_records")

        class SchemaEditor:
            connection = connection

        migration.restore_archived_records(apps, SchemaEditor())

        for record, disabled_field, disabled_value in (
            (product, "is_available", False),
            (market, "status", Market.Status.INACTIVE),
            (offer, "status", Offer.Status.INACTIVE),
            (city, "is_active", False),
            (area, "is_active", False),
            (company, "is_active", False),
        ):
            record.refresh_from_db()
            self.assertIsNone(record.archived_at)
            self.assertEqual(getattr(record, disabled_field), disabled_value)
