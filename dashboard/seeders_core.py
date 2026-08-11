from pathlib import Path

from django.conf import settings
from django.core.management.color import no_style
from django.db import connection
from django.utils import timezone

from accounts.models import CourierProfile, OneTimePassword, User
from catalog.models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductAttributeValue,
    ProductCategory,
    StoreSubcategory,
    ProductVariant,
    VariantAttributeValue,
)
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification, MarketSubcategory
from notifications.models import Notification
from offers.models import Offer
from orders.models import Order, OrderItem, OrderMarketSection, OrderOffer


class DemoSeedCoreMixin:
    def _delete_project_data(self):
        delete_plan = [
            Notification,
            OrderOffer,
            OrderItem,
            OrderMarketSection,
            Order,
            Offer,
            ProductAddition,
            ProductAttributeValue,
            VariantAttributeValue,
            ProductVariant,
            Product,
            StoreSubcategory,
            CategoryOption,
            CategoryAttribute,
            ProductCategory,
            CategoryClassification,
            AdditionClassification,
            Market,
            MarketClassification,
            Address,
            CourierProfile,
            OneTimePassword,
            User,
            DeliveryArea,
            ServiceCity,
        ]
        deleted = {}
        for model in delete_plan:
            count, _ = model.objects.all().delete()
            deleted[model.__name__] = count
        self._write("Deleted existing project/domain data.")
        return deleted

    def _delete_seed_media_files(self):
        media_root = Path(settings.MEDIA_ROOT)
        for folder in ("additions", "categories", "offers", "products"):
            directory = media_root / folder
            if not directory.exists():
                continue
            for path in directory.glob("seed_*.png"):
                path.unlink()
        self._write("Deleted old seed placeholder media files.")

    def _reset_sequences(self):
        models = [
            ServiceCity,
            DeliveryArea,
            User,
            CourierProfile,
            OneTimePassword,
            MarketClassification,
            Market,
            CategoryClassification,
            ProductCategory,
            CategoryAttribute,
            CategoryOption,
            AdditionClassification,
            ProductAddition,
            Product,
            ProductAttributeValue,
            ProductVariant,
            VariantAttributeValue,
            Offer,
            Order,
            OrderItem,
            OrderOffer,
            Notification,
        ]
        statements = connection.ops.sequence_reset_sql(no_style(), models)
        if not statements:
            return
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    def _create_seed_data(self):
        now = timezone.now()
        context = {
            "cities": {},
            "areas": {},
            "users": {},
            "market_classifications": {},
            "markets": {},
            "category_classifications": {},
            "categories": {},
            "store_subcategories": {},
            "attributes": {},
            "options": {},
            "addition_classifications": {},
            "additions": {},
            "products": {},
            "offers": {},
            "orders": [],
            "notifications": [],
            "credentials": [],
        }

        self._seed_locations(context)
        self._seed_users(context, now)
        self._seed_addresses(context)
        self._seed_market_classifications(context)
        self._seed_markets(context)
        self._seed_catalog(context)
        self._seed_products(context)
        self._seed_likes(context)
        self._seed_offers(context, now)
        self._seed_orders(context, now)
        self._seed_notifications(context, now)
        self._write("Created Egyptian demo data.")
        return context

