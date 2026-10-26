from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from markets import tests as fixtures
from markets import test_storefront_pagination as catalog_fixtures
from markets.serializers import HomeProductSerializer
from offers.models import Offer, OfferItem
from catalog.models import Product
from django.contrib.auth import get_user_model


class CustomerPerformanceTests(APITestCase):
    setUp = fixtures.HomeAPITests.setUp
    _create_market = fixtures.HomeAPITests._create_market
    _create_product = fixtures.HomeAPITests._create_product
    _create_offer = fixtures.HomeAPITests._create_offer

    def test_offer_query_count_does_not_grow_with_the_number_of_offers(self):
        self.client.force_authenticate(self.user)
        Offer.objects.all().update(status=Offer.Status.INACTIVE)
        product = self.local_products[0]
        variant = product.variants.first()
        counts = []
        for index in range(100):
            offer = self._create_offer(f"Offer {index}", self.local_market, product, timezone.now())
            OfferItem.objects.create(offer=offer, variant=variant)
            if index in (9, 99):
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get("/api/v1/offers/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.data), index + 1)
                self.assertEqual(len(response.data[0]["products"]), 1)
                counts.append(len(queries))
        self.assertLessEqual(counts[1], counts[0] + 1)
        self.assertLess(counts[1], 50)

    def test_banner_summary_does_not_serialize_products_and_detail_remains_complete(self):
        self.client.force_authenticate(self.user)
        catalog_fixtures.StorefrontPaginationTests.grow_catalog(self, 300)
        offer = self._create_offer("Large offer", self.local_market, self.local_products[0], timezone.now())
        offer.products.set(Product.objects.filter(market=self.local_market))
        with patch.object(HomeProductSerializer, "to_representation") as serialize:
            response = self.client.get("/api/v1/offers/", {"summary": "true"})
        self.assertEqual(response.status_code, 200)
        serialize.assert_not_called()
        self.assertTrue(all(item["is_summary"] and item["products"] == [] for item in response.data))
        with CaptureQueriesContext(connection) as queries:
            detail = self.client.get(f"/api/v1/offers/{offer.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data["products"]), 300)
        self.assertLess(len(queries), 50)

    def test_favorite_pages_include_complete_membership_without_all_card_details(self):
        self.client.force_authenticate(self.user)
        catalog_fixtures.StorefrontPaginationTests.grow_catalog(self, 300)
        products = Product.objects.filter(market=self.local_market)
        for product in products:
            product.liked_by.add(self.user)
        url = "/api/v1/catalog/products/likes/"
        response = self.client.get(url, {"page": 1, "page_size": 30, "include_ids": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 300)
        self.assertEqual(len(response.data["results"]), 30)
        self.assertEqual(set(response.data["liked_ids"]), set(products.values_list("id", flat=True)))
        second = self.client.get(url, {"page": 2, "page_size": 30})
        self.assertNotIn("liked_ids", second.data)
        self.assertFalse(set(item["id"] for item in response.data["results"]) &
                         set(item["id"] for item in second.data["results"]))
        self.assertIsInstance(self.client.get(url).data, list)
        self.local_market.liked_by.add(self.user)
        market_page = self.client.get("/api/v1/home/markets/likes/", {"page": 1, "include_ids": "true"})
        self.assertEqual(market_page.status_code, 200)
        self.assertIn(self.local_market.id, market_page.data["liked_ids"])
        other = get_user_model().objects.create_user(
            username="other-favorites-customer", phone="+213999012345", role="client",
        )
        self.client.force_authenticate(other)
        private = self.client.get(url, {"page": 1, "include_ids": "true"})
        self.assertEqual(private.status_code, 200)
        self.assertEqual(private.data["liked_ids"], [])
