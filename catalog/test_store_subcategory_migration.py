from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class StoreSubcategoryMigrationTests(TransactionTestCase):
    migrate_from = [
        ("catalog", "0004_productimage"),
        ("markets", "0008_market_is_popular"),
    ]
    migrate_to = [
        ("catalog", "0006_backfill_store_subcategories"),
        ("markets", "0009_market_subcategories"),
    ]

    def test_legacy_categories_are_merged_and_empty_data_uses_other(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Classification = old_apps.get_model(
            "markets",
            "MarketClassification",
        )
        Market = old_apps.get_model("markets", "Market")
        CategoryClassification = old_apps.get_model(
            "catalog",
            "CategoryClassification",
        )
        ProductCategory = old_apps.get_model("catalog", "ProductCategory")
        Product = old_apps.get_model("catalog", "Product")

        classification = Classification.objects.create(name="Stores")
        used_market = Market.objects.create(
            classification=classification,
            name="Used Store",
        )
        empty_market = Market.objects.create(
            classification=classification,
            name="Empty Store",
        )
        category_classification = CategoryClassification.objects.create(
            name="Legacy",
        )
        first_category = ProductCategory.objects.create(
            classification=category_classification,
            name="Drinks",
            description="Legacy description",
        )
        second_category = ProductCategory.objects.create(
            classification=category_classification,
            name="drinks",
        )
        legacy_other = ProductCategory.objects.create(
            classification=category_classification,
            name="Other",
        )
        first_product = Product.objects.create(
            market=used_market,
            category=first_category,
            name="Water",
        )
        second_product = Product.objects.create(
            market=used_market,
            category=second_category,
            name="Juice",
        )
        uncategorized = Product.objects.create(
            market=used_market,
            category=None,
            name="Mystery",
        )
        legacy_other_product = Product.objects.create(
            market=used_market,
            category=legacy_other,
            name="Legacy Other",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        StoreSubcategory = new_apps.get_model(
            "catalog",
            "StoreSubcategory",
        )
        MigratedProduct = new_apps.get_model("catalog", "Product")
        MarketSubcategory = new_apps.get_model(
            "markets",
            "MarketSubcategory",
        )

        drinks = StoreSubcategory.objects.get(name_ar="Drinks")
        other = StoreSubcategory.objects.get(name_ar="أخرى", name_en="Other")
        self.assertEqual(
            MigratedProduct.objects.get(pk=first_product.pk).subcategory_id,
            drinks.id,
        )
        self.assertEqual(
            MigratedProduct.objects.get(pk=second_product.pk).subcategory_id,
            drinks.id,
        )
        self.assertEqual(
            MigratedProduct.objects.get(pk=uncategorized.pk).subcategory_id,
            other.id,
        )
        self.assertEqual(
            MigratedProduct.objects.get(
                pk=legacy_other_product.pk,
            ).subcategory_id,
            other.id,
        )
        self.assertEqual(
            StoreSubcategory.objects.filter(name_ar__iexact="drinks").count(),
            1,
        )
        self.assertTrue(
            MarketSubcategory.objects.filter(
                market_id=used_market.id,
                subcategory_id=drinks.id,
            ).exists()
        )
        self.assertTrue(
            MarketSubcategory.objects.filter(
                market_id=empty_market.id,
                subcategory_id=other.id,
            ).exists()
        )
