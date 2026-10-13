from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from catalog.models import Product, ProductVariant, StoreSubcategory
from markets.serializers import StorefrontProductSerializer
from markets import tests as home_tests
from markets.tests import HOME_BASE


class StorefrontPaginationTests(APITestCase):
    _create_market = home_tests.HomeAPITests._create_market
    _create_product = home_tests.HomeAPITests._create_product
    _create_offer = home_tests.HomeAPITests._create_offer

    def setUp(self):
        home_tests.HomeAPITests.setUp(self)
        self.client.force_authenticate(self.user)
        self.url = f"{HOME_BASE}/markets/{self.local_market.id}/storefront/products/"

    def grow_catalog(self, size):
        current = Product.objects.filter(market=self.local_market).count()
        products = Product.objects.bulk_create([
            Product(market=self.local_market, subcategory=self.subcategory,
                    name=f"Bulk {index:05}", description="Catalog fixture")
            for index in range(current, size)
        ])
        ProductVariant.objects.bulk_create([
            ProductVariant(product=product, price=Decimal("150"),
                           sku=f"STORE-PAGE-{product.pk}")
            for product in products
        ])

    def test_large_catalog_serializes_only_default_page_with_bounded_queries(self):
        query_counts = []
        original = StorefrontProductSerializer.to_representation
        for size in (100, 1000, 10000):
            with self.subTest(size=size):
                self.grow_catalog(size)
                with patch.object(StorefrontProductSerializer, "to_representation",
                                  autospec=True, side_effect=original) as serialize:
                    with CaptureQueriesContext(connection) as queries:
                        response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], size)
                self.assertEqual(len(response.data["results"]), 30)
                self.assertEqual(serialize.call_count, 30)
                self.assertIsNotNone(response.data["next"])
                self.assertIsNone(response.data["previous"])
                self.assertEqual(response.data["results"][0]["market"]["id"], self.local_market.id)
                query_counts.append(len(queries))
                product_selects = [q["sql"] for q in queries
                                   if 'FROM "catalog_product"' in q["sql"]
                                   and not q["sql"].startswith("SELECT COUNT(")]
                self.assertEqual(len(product_selects), 1)
                self.assertIn("LIMIT 30", product_selects[0])
        self.assertEqual(len(set(query_counts)), 1)
        self.assertLess(query_counts[0], 20)

    def test_header_only_avoids_product_materialization_and_preserves_metrics(self):
        url = self.url.removesuffix("products/")
        with patch("markets.views.storefront_products") as product_query:
            response = self.client.get(url, {"include_products": "false"})
        self.assertEqual(response.status_code, 200)
        product_query.assert_not_called()
        self.assertEqual(response.data["products"], [])
        self.assertEqual(response.data["product_count"], 5)
        self.assertEqual(Decimal(response.data["minimum_product_price"]), Decimal("100"))
        legacy = self.client.get(url)
        self.assertEqual(len(legacy.data["products"]), 5)

    def test_pages_are_ordered_without_duplicates_and_end(self):
        self.grow_catalog(100)
        ids = []
        for page in range(1, 5):
            response = self.client.get(self.url, {"page": page})
            self.assertEqual(response.status_code, 200)
            ids.extend(p["id"] for p in response.data["results"])
            self.assertEqual(response.data["next"] is None, page == 4)
        self.assertEqual(len(ids), 100)
        self.assertEqual(len(set(ids)), 100)
        self.assertEqual(self.client.get(self.url, {"page": 5}).status_code, 404)

    def test_search_matches_description_and_market_name_across_catalog(self):
        self.grow_catalog(100)
        product = Product.objects.filter(market=self.local_market).last()
        product.description = "needle beyond first batch"
        product.save(update_fields=["description"])
        response = self.client.get(self.url, {"q": "needle"})
        self.assertEqual([p["id"] for p in response.data["results"]], [product.id])
        response = self.client.get(self.url, {"q": self.local_market.name})
        self.assertEqual(response.data["count"], 100)
        self.assertEqual(self.client.get(self.url, {"q": "absent"}).data["results"], [])

    def test_primary_and_many_subcategories_are_combined_without_duplicates(self):
        category = StoreSubcategory.objects.create(name_ar="قسم جديد", name_en="New section")
        first, second = list(Product.objects.filter(market=self.local_market)[:2])
        first.subcategories.add(category)
        second.subcategory = category
        second.save(update_fields=["subcategory"])
        second.subcategories.add(category)
        response = self.client.get(self.url, {"subcategory_id": category.id})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual({p["id"] for p in response.data["results"]}, {first.id, second.id})

    def test_price_sort_uses_lowest_variant_before_discount_with_stable_ties(self):
        products = list(Product.objects.filter(market=self.local_market).order_by("id"))
        first, second = products[:2]
        ProductVariant.objects.filter(product=second).update(price=100)
        ProductVariant.objects.create(product=first, price=2000, sku="STORE-EXPENSIVE")
        second.discount = 99
        second.save(update_fields=["discount"])
        response = self.client.get(self.url, {"sort": "price_asc"})
        self.assertEqual([p["id"] for p in response.data["results"][:2]], [first.id, second.id])
        descending = self.client.get(self.url, {"sort": "price_desc"})
        self.assertEqual(descending.data["results"][0]["id"], products[-1].id)
        newest = self.client.get(self.url, {"sort": "newest"})
        self.assertEqual(newest.data["results"][0]["id"], products[-1].id)

    def test_validation_and_page_size(self):
        self.grow_catalog(150)
        self.assertEqual(len(self.client.get(self.url, {"page_size": 100}).data["results"]), 100)
        for params in ({"page_size": 101}, {"page_size": 0}, {"page": 0},
                       {"subcategory_id": "invalid"}, {"sort": "invalid"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.url, params).status_code, 400)

    def test_empty_first_page_is_successful_and_terminal(self):
        Product.objects.filter(market=self.local_market).update(is_available=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"count": 0, "next": None,
                                        "previous": None, "results": []})

    def test_availability_variants_and_archive_filters(self):
        products = list(Product.objects.filter(market=self.local_market))
        products[0].is_available = False
        products[0].save(update_fields=["is_available"])
        ProductVariant.objects.filter(product=products[1]).delete()
        products[2].archived_at = timezone.now()
        products[2].save(update_fields=["archived_at"])
        response = self.client.get(self.url)
        self.assertEqual(response.data["count"], 2)

    def test_authentication_role_region_and_inactive_market(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.user)
        remote = f"{HOME_BASE}/markets/{self.remote_market.id}/storefront/products/"
        self.assertEqual(self.client.get(remote).status_code, 404)
        self.local_market.archived_at = timezone.now()
        self.local_market.save(update_fields=["archived_at"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
