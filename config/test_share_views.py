from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import (
    Product,
    ProductAttribute,
    ProductAttributeOption,
    ProductVariant,
    StoreSubcategory,
    VariantAttributeValue,
)
from markets.models import Market, MarketClassification
from offers.models import Offer


@override_settings(ANDROID_APP_STORE_URL="", IOS_APP_STORE_URL="")
class ShareLandingViewTests(TestCase):
    def setUp(self):
        classification = MarketClassification.objects.create(name="Popular")
        self.market = Market.objects.create(
            classification=classification,
            name="Share Market",
        )
        subcategory = StoreSubcategory.objects.create(
            name_ar="مشاركة",
            name_en="Sharing",
        )
        self.market.subcategories.add(subcategory)
        self.product = Product.objects.create(
            market=self.market,
            subcategory=subcategory,
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
        response = self.client.get(reverse("product-share", args=[self.product.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"yallamarket://products/{self.product.id}",
        )
        self.assertContains(response, "Shared product")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_expired_offer_share_page_returns_not_found(self):
        self.offer.end_time = timezone.now() - timedelta(minutes=1)
        self.offer.save(update_fields=["end_time"])

        response = self.client.get(reverse("offer-share", args=[self.offer.id]))

        self.assertEqual(response.status_code, 404)

    def test_archived_or_inactive_shared_content_returns_not_found(self):
        self.product.archived_at = timezone.now()
        self.product.save(update_fields=["archived_at"])
        self.market.status = Market.Status.INACTIVE
        self.market.save(update_fields=["status"])

        self.assertEqual(
            self.client.get(
                reverse("product-share", args=[self.product.id])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("market-share", args=[self.market.id])).status_code,
            404,
        )

    def test_market_share_page_opens_the_market_deep_link(self):
        response = self.client.get(reverse("market-share", args=[self.market.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"yallamarket://markets/{self.market.id}",
        )
        self.assertContains(response, self.market.name)

    def test_share_page_escapes_product_content(self):
        self.product.name = '<script>alert("unsafe")</script>'
        self.product.save(update_fields=["name"])

        response = self.client.get(reverse("product-share", args=[self.product.id]))
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
        self.assertEqual(
            self.client.get(reverse("market-share", args=[999999])).status_code,
            404,
        )

    def test_prelaunch_page_shows_details_without_automatic_app_redirect(self):
        response = self.client.get(reverse("product-share", args=[self.product.id]))

        self.assertContains(response, "<p>Shared safely</p>")
        self.assertContains(response, self.market.name)
        self.assertContains(response, "التطبيق غير متاح على المتاجر حاليًا")
        self.assertNotContains(response, "play.google.com")
        self.assertNotContains(response, "apps.apple.com")
        self.assertNotContains(response, "<script>")
        self.assertContains(response, 'property="og:url"')
        self.assertNotIn(
            "script-src 'unsafe-inline'", response.headers["Content-Security-Policy"]
        )

    def test_selected_variant_is_preserved_and_its_attributes_are_shown(self):
        variant = ProductVariant.objects.create(product=self.product, price="125.00")
        attribute = ProductAttribute.objects.create(product=self.product, name="المقاس")
        option = ProductAttributeOption.objects.create(
            attribute=attribute, value="كبير"
        )
        VariantAttributeValue.objects.create(
            variant=variant,
            product_attribute=attribute,
            product_attribute_option=option,
        )

        response = self.client.get(
            reverse("product-share", args=[self.product.id]),
            {"variant": variant.id, "tracking": "ignored"},
        )

        self.assertContains(
            response, f"yallamarket://products/{self.product.id}?variant={variant.id}"
        )
        self.assertContains(response, "المقاس: كبير")
        self.assertContains(
            response, f"/share/products/{self.product.id}/?variant={variant.id}"
        )
        self.assertNotContains(response, "tracking")

    def test_invalid_or_foreign_variants_fall_back_to_the_product(self):
        other_product = Product.objects.create(
            market=self.market, subcategory=self.product.subcategory, name="Other"
        )
        foreign = ProductVariant.objects.create(product=other_product, price="1.00")
        for value in [str(foreign.id), "0", "-1", "bad", "9" * 200, ["1", "2"]]:
            with self.subTest(variant=value):
                response = self.client.get(
                    reverse("product-share", args=[self.product.id]), {"variant": value}
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, f'href="yallamarket://products/{self.product.id}"'
                )
                self.assertNotContains(response, "?variant=")

    @override_settings(
        ANDROID_APP_STORE_URL="https://play.google.com/store/apps/details?id=com.yallamarket.app",
        IOS_APP_STORE_URL="https://apps.apple.com/app/id123456789",
    )
    def test_published_store_links_are_shown_only_when_configured(self):
        response = self.client.get(reverse("market-share", args=[self.market.id]))
        self.assertContains(response, "تحميل من Google Play")
        self.assertContains(response, "تحميل من App Store")
        self.assertNotContains(response, "غير متاح على المتاجر")

    @override_settings(
        ANDROID_APP_STORE_URL="javascript:alert(1)", IOS_APP_STORE_URL="https://[bad"
    )
    def test_invalid_store_configuration_never_becomes_a_download_link(self):
        response = self.client.get(reverse("product-share", args=[self.product.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "javascript:")
        self.assertNotContains(response, "https://[bad")


class AppAssociationTests(SimpleTestCase):
    @override_settings(ANDROID_APP_LINK_FINGERPRINTS=[], IOS_APP_LINK_APP_IDS=[])
    def test_unconfigured_apps_do_not_advertise_an_association(self):
        self.assertEqual(self.client.get(reverse("android-asset-links")).json(), [])
        self.assertEqual(
            self.client.get(reverse("apple-app-site-association")).json(),
            {"applinks": {"details": []}},
        )

    @override_settings(ANDROID_APP_LINK_FINGERPRINTS=[":".join(["AA"] * 32)])
    def test_android_association_has_the_app_signing_certificate(self):
        response = self.client.get("/.well-known/assetlinks.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        entry = response.json()[0]
        self.assertEqual(entry["target"]["package_name"], "com.yallamarket.app")
        self.assertEqual(
            entry["target"]["sha256_cert_fingerprints"], [":".join(["AA"] * 32)]
        )
        self.assertEqual(
            entry["relation"], ["delegate_permission/common.handle_all_urls"]
        )

    @override_settings(IOS_APP_LINK_APP_IDS=["ABC1234567.com.yallamarket.app"])
    def test_apple_association_only_handles_shared_content_paths(self):
        response = self.client.get("/.well-known/apple-app-site-association")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        detail = response.json()["applinks"]["details"][0]
        self.assertEqual(detail["appIDs"], ["ABC1234567.com.yallamarket.app"])
        self.assertEqual(
            detail["components"],
            [
                {"/": "/share/products/*"},
                {"/": "/share/offers/*"},
                {"/": "/share/markets/*"},
            ],
        )

    @override_settings(
        ANDROID_APP_LINK_FINGERPRINTS=["invalid"], IOS_APP_LINK_APP_IDS=["invalid"]
    )
    def test_invalid_signing_configuration_is_not_advertised(self):
        self.assertEqual(self.client.get(reverse("android-asset-links")).json(), [])
        self.assertEqual(
            self.client.get(reverse("apple-app-site-association")).json(),
            {"applinks": {"details": []}},
        )
