from unittest.mock import patch
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework.test import APITestCase
from rest_framework.renderers import JSONRenderer

from . import tests as home_tests
from . import test_storefront_pagination as storefront_tests
from .tests import HOME_BASE
from .serializers import MarketClassificationProductSerializer, HomeMarketSerializer
from .models import MarketType, MarketClassification


class CatalogPerformanceTests(APITestCase):
    setUp = home_tests.HomeAPITests.setUp
    _create_market = home_tests.HomeAPITests._create_market
    _create_product = home_tests.HomeAPITests._create_product
    _create_offer = home_tests.HomeAPITests._create_offer

    def test_compact_preview_queries_do_not_grow_per_classification(self):
        self.client.force_authenticate(self.user)
        url = f"{HOME_BASE}/classifications/"
        with CaptureQueriesContext(connection) as initial:
            first = self.client.get(url, {"include_products": "false"})
        self.assertEqual(first.status_code, 200)
        for i in range(6):
            classification = MarketClassification.objects.create(name=f"Extra {i}")
            self._create_market(f"Extra store {i}", classification, self.local_area)
        with CaptureQueriesContext(connection) as expanded:
            response = self.client.get(url, {"include_products": "false"})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data["market_classifications"]), 6)
        self.assertLessEqual(len(expanded), len(initial) + 1)

    def test_compact_summary_never_serializes_products_and_stays_bounded(self):
        self.client.force_authenticate(self.user)
        sizes = []
        for count in (300, 1000):
            storefront_tests.StorefrontPaginationTests.grow_catalog(self, count)
            with patch.object(MarketClassificationProductSerializer, "to_representation") as serialize:
                response = self.client.get(f"{HOME_BASE}/classifications/", {"include_products": "false"})
            self.assertEqual(response.status_code, 200)
            serialize.assert_not_called()
            markets = [m for c in response.data["market_classifications"] for m in c["markets"]]
            markets += response.data["latest_markets"]
            self.assertTrue(all(m["products"] == [] for m in markets))
            self.assertTrue(any(m["product_count"] == count for m in markets))
            sizes.append(len(JSONRenderer().render(response.data)))
        self.assertLess(abs(sizes[1] - sizes[0]), 100)

    def test_market_pages_are_bounded_and_search_covers_the_entire_category(self):
        self.client.force_authenticate(self.user)
        extra = [self._create_market(f"Needle {i:03}", self.local_market.classification, self.local_area) for i in range(45)]
        url = f"{HOME_BASE}/store-list/"
        params = {"classification_id": self.local_market.classification_id, "q": "Needle", "page_size": 10}
        original = HomeMarketSerializer.to_representation
        with patch.object(HomeMarketSerializer, "to_representation", autospec=True, side_effect=original) as serialize:
            first = self.client.get(url, params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["count"], 45)
        self.assertEqual(len(first.data["results"]), 10)
        self.assertEqual(serialize.call_count, 10)
        last = self.client.get(url, {**params, "q": "Needle 044"})
        self.assertEqual([m["id"] for m in last.data["results"]], [extra[-1].id])
        ids = []
        for page in range(1, 6):
            result = self.client.get(url, {**params, "page": page})
            ids.extend(m["id"] for m in result.data["results"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {m.id for m in extra})

    def test_market_type_is_applied_before_pagination(self):
        self.client.force_authenticate(self.user)
        kind = MarketType.objects.create(classification=self.local_market.classification, name_ar="قسم", name_en="Type")
        self.local_market.market_types.add(kind)
        response = self.client.get(f"{HOME_BASE}/store-list/", {"classification_id": self.local_market.classification_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_type_id"], kind.id)
        self.assertTrue(all(kind.id in m["market_type_ids"] for m in response.data["results"]))

    def test_paged_search_keeps_legacy_size_and_pages_side_results_independently(self):
        self.client.force_authenticate(self.user)
        storefront_tests.StorefrontPaginationTests.grow_catalog(self, 300)
        url = f"{HOME_BASE}/search/"
        legacy = self.client.get(url, {"q": "Bulk"})
        self.assertEqual(len(legacy.data["results"]), 4)
        first = self.client.get(url, {"q": "Bulk", "include": "all", "paged": "true"})
        self.assertEqual(len(first.data["results"]), 30)
        for i in range(35):
            self._create_market(f"Needle {i:03}", self.local_market.classification, self.local_area)
        side = self.client.get(url, {"q": "Needle", "include": "all", "paged": "true", "section": "markets", "page": 2})
        self.assertEqual(side.status_code, 200)
        self.assertEqual(side.data["results"], [])
        self.assertEqual(len(side.data["markets"]), 5)
        self.assertIsNone(side.data["markets_next"])
