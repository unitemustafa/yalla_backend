from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from markets.models import Market, MarketClassification
from offers.models import Offer


class ShareLandingViewTests(TestCase):
    def setUp(self):
        classification = MarketClassification.objects.create(name="Popular")
        self.market = Market.objects.create(
            classification=classification,
            name="Share Market",
        )
        self.product = Product.objects.create(
            market=self.market,
            name="Shared product",
            description="Shared safely",
        )
        now = timezone.now()
        self.offer = Offer.objects.create(
            market=self.market,
            title="Shared offer",
            description="Offer details",
            discount=Decimal("10.00"),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

    def test_product_share_page_opens_the_product_deep_link(self):
        response = self.client.get(
            reverse("product-share", args=[self.product.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"yallamarket://products/{self.product.id}",
        )
        self.assertContains(response, "Shared product")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_offer_share_page_keeps_opening_after_offer_expiry(self):
        self.offer.end_time = timezone.now() - timedelta(minutes=1)
        self.offer.save(update_fields=["end_time"])

        response = self.client.get(reverse("offer-share", args=[self.offer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"yallamarket://offers/{self.offer.id}",
        )

    def test_share_page_escapes_product_content(self):
        self.product.name = '<script>alert("unsafe")</script>'
        self.product.save(update_fields=["name"])

        response = self.client.get(
            reverse("product-share", args=[self.product.id])
        )
        body = response.content.decode()

        self.assertNotIn('<script>alert("unsafe")</script>', body)
        self.assertIn("&lt;script&gt;alert", body)

    def test_missing_shared_content_returns_not_found(self):
        self.assertEqual(
            self.client.get(reverse("product-share", args=[999999])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("offer-share", args=[999999])).status_code,
            404,
        )
