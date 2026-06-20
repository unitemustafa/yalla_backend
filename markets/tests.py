from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import (
    CategoryClassification,
    Product,
    ProductCategory,
    ProductVariant,
)
from locations.models import Address, DeliveryArea
from offers.models import Offer

from .models import Market, MarketClassification

User = get_user_model()


class HomeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="home_user",
            email="home@example.com",
            phone="+213555200001",
            password="Password1!",
        )
        self.default_address = Address.objects.create(
            user=self.user,
            name="Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0419000"),
            is_default=True,
        )
        self.local_area = DeliveryArea.objects.create(
            name="Local",
            delivery_price=Decimal("250.00"),
            center_latitude=Decimal("36.7538000"),
            center_longitude=Decimal("3.0588000"),
            radius_km=Decimal("8.00"),
        )
        self.remote_area = DeliveryArea.objects.create(
            name="Remote",
            delivery_price=Decimal("280.00"),
            center_latitude=Decimal("35.6969000"),
            center_longitude=Decimal("-0.6331000"),
            radius_km=Decimal("7.00"),
        )

        self.local_classification = MarketClassification.objects.create(
            name="Local supermarkets"
        )
        self.second_local_classification = MarketClassification.objects.create(
            name="Local restaurants"
        )
        self.remote_classification = MarketClassification.objects.create(
            name="Remote bakeries"
        )
        self.local_market = self._create_market(
            "Local Market",
            self.local_classification,
            self.local_area,
        )
        self.second_local_market = self._create_market(
            "Local Kitchen",
            self.second_local_classification,
            self.local_area,
        )
        self.remote_market = self._create_market(
            "Remote Market",
            self.remote_classification,
            self.remote_area,
        )

        category_classification = CategoryClassification.objects.create(
            name="Home test"
        )
        self.category = ProductCategory.objects.create(
            classification=category_classification,
            name="Test category",
            type="test",
        )

        self.local_products = [
            self._create_product(
                f"Local Product {index}",
                self.local_market
                if index % 2
                else self.second_local_market,
                index,
            )
            for index in range(1, 11)
        ]
        self.remote_product = self._create_product(
            "Remote Product",
            self.remote_market,
            99,
        )

        now = timezone.now()
        self.local_offers = [
            self._create_offer(
                f"Local Offer {index}",
                self.local_market
                if index % 2
                else self.second_local_market,
                self.local_products[index - 1],
                now,
            )
            for index in range(1, 6)
        ]
        self.remote_offer = self._create_offer(
            "Remote Offer",
            self.remote_market,
            self.remote_product,
            now,
        )

    def authenticate(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def test_home_requires_authentication(self):
        response = self.client.get("/api/home/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_home_requires_user_address(self):
        self.default_address.delete()
        self.authenticate()

        response = self.client.get("/api/home/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "A user address is required before loading the home page.",
        )

    def test_home_returns_limited_content_from_user_location_only(self):
        self.authenticate()

        response = self.client.get("/api/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["location"]["name"], "Home")
        self.assertEqual(len(response.data["offers"]), 4)
        self.assertEqual(len(response.data["products"]), 8)
        self.assertEqual(len(response.data["market_classifications"]), 2)

        local_market_ids = {self.local_market.id, self.second_local_market.id}
        self.assertTrue(
            all(
                product["market"]["id"] in local_market_ids
                for product in response.data["products"]
            )
        )
        self.assertTrue(
            all(
                offer["market"]["id"] in local_market_ids
                for offer in response.data["offers"]
            )
        )
        self.assertNotIn(
            self.remote_classification.id,
            {
                classification["id"]
                for classification in response.data[
                    "market_classifications"
                ]
            },
        )
        self.assertTrue(
            all(
                product["category"]["id"] == self.category.id
                for product in response.data["products"]
            )
        )

    def _create_market(self, name, classification, area):
        market = Market.objects.create(
            name=name,
            branch=name,
            classification=classification,
        )
        market.delivery_areas.add(area)
        return market

    def _create_product(self, name, market, index):
        product = Product.objects.create(
            market=market,
            category=self.category,
            name=name,
            description=f"Description for {name}",
        )
        ProductVariant.objects.create(
            product=product,
            price=Decimal(index * 100),
            sku=f"HOME-{index}",
        )
        return product

    def _create_offer(self, title, market, product, now):
        offer = Offer.objects.create(
            market=market,
            title=title,
            description=f"Description for {title}",
            type=Offer.OfferType.DISCOUNT,
            discount=Decimal("10.00"),
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=10),
            status=Offer.Status.ACTIVE,
        )
        offer.products.add(product)
        return offer
