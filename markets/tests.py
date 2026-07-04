from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductAttributeValue,
    ProductCategory,
    ProductVariant,
    VariantAttributeValue,
)
from locations.models import Address, DeliveryArea, ServiceCity
from offers.models import Offer

from .models import Market, MarketClassification

User = get_user_model()
HOME_BASE = "/api/v1/home"


class HomeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="home_user",
            email="home@example.com",
            phone="+213555200001",
            password="Password1!",
        )
        self.admin = User.objects.create_user(
            username="market_admin",
            email="market-admin@example.com",
            phone="+213555200002",
            password="Password1!",
            role=User.Role.ADMIN,
            is_active=True,
        )
        self.default_address = Address.objects.create(
            user=self.user,
            name="Home",
            latitude=Decimal("36.7525000"),
            longitude=Decimal("3.0419000"),
            is_default=True,
        )
        self.service_city = ServiceCity.objects.create(
            name="Algiers",
            center_latitude=Decimal("36.7525000"),
            center_longitude=Decimal("3.0419000"),
            radius_km=Decimal("30.00"),
        )
        self.remote_city = ServiceCity.objects.create(
            name="Remote City",
            center_latitude=Decimal("35.6969000"),
            center_longitude=Decimal("-0.6331000"),
            radius_km=Decimal("30.00"),
        )
        self.default_address.service_city = self.service_city
        self.default_address.save(update_fields=["service_city"])
        self.user.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        self.user.market_region_service_city = self.service_city
        self.user.market_region_updated_at = timezone.now()
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.local_area = DeliveryArea.objects.create(
            service_city=self.service_city,
            name="Local",
            delivery_price=Decimal("250.00"),
            center_latitude=Decimal("36.7538000"),
            center_longitude=Decimal("3.0588000"),
            radius_km=Decimal("8.00"),
        )
        self.remote_area = DeliveryArea.objects.create(
            service_city=self.remote_city,
            name="Remote",
            delivery_price=Decimal("280.00"),
            center_latitude=Decimal("35.6969000"),
            center_longitude=Decimal("-0.6331000"),
            radius_km=Decimal("7.00"),
        )

        self.local_classification = MarketClassification.objects.create(
            name="Local supermarkets",
            classification_type=MarketClassification.ClassificationType.POPULAR,
        )
        self.second_local_classification = MarketClassification.objects.create(
            name="Local restaurants",
            classification_type=MarketClassification.ClassificationType.FEATURED,
        )
        self.remote_classification = MarketClassification.objects.create(
            name="Remote bakeries",
            classification_type=MarketClassification.ClassificationType.NORMAL,
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

    def authenticate(self, user=None):
        refresh = RefreshToken.for_user(user or self.user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def select_general_region(self):
        self.user.market_region_mode = User.MarketRegionMode.GENERAL
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = timezone.now()
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )

    def test_home_requires_authentication(self):
        response = self.client.get(f"{HOME_BASE}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_market_region_options_me_and_patch(self):
        self.authenticate()

        options_response = self.client.get("/api/v1/market-region/options/")
        me_response = self.client.get("/api/v1/market-region/me/")
        general_response = self.client.patch(
            "/api/v1/market-region/me/",
            {"mode": User.MarketRegionMode.GENERAL},
            format="json",
        )
        city_response = self.client.patch(
            "/api/v1/market-region/me/",
            {
                "mode": User.MarketRegionMode.SERVICE_CITY,
                "service_city_id": self.service_city.id,
            },
            format="json",
        )

        self.assertEqual(options_response.status_code, status.HTTP_200_OK)
        self.assertEqual(options_response.data["options"][0]["mode"], "general")
        self.assertIn(
            self.service_city.id,
            [
                option["service_city"]["id"]
                for option in options_response.data["options"]
                if option["service_city"] is not None
            ],
        )
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            me_response.data["current_selection"]["service_city"]["id"],
            self.service_city.id,
        )
        self.assertEqual(general_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            general_response.data["current_selection"]["mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertIsNone(
            general_response.data["current_selection"]["service_city"]
        )
        self.assertEqual(city_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            city_response.data["current_selection"]["service_city"]["id"],
            self.service_city.id,
        )

    def test_market_region_patch_rejects_inactive_city(self):
        inactive_city = ServiceCity.objects.create(
            name="Inactive City",
            is_active=False,
        )
        self.authenticate()

        response = self.client.patch(
            "/api/v1/market-region/me/",
            {
                "mode": User.MarketRegionMode.SERVICE_CITY,
                "service_city_id": inactive_city.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["service_city_id"][0],
            "Service city must be active.",
        )

    def test_market_region_detect_same_region(self):
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "36.7525000",
                "longitude": "3.0419000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "same_region")
        self.assertEqual(
            response.data["current_selection"]["service_city"]["id"],
            self.service_city.id,
        )
        self.assertEqual(
            response.data["detected_region"]["service_city"]["id"],
            self.service_city.id,
        )
        self.assertNotIn(
            "delivery_price",
            response.data["detected_region"]["service_city"],
        )

    def test_market_region_detect_different_city_suggests_switch(self):
        self.user.market_region_service_city = self.remote_city
        self.user.save(update_fields=["market_region_service_city"])
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "36.7525000",
                "longitude": "3.0419000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "suggest_switch")
        self.assertEqual(
            response.data["current_selection"]["service_city"]["id"],
            self.remote_city.id,
        )
        self.assertEqual(
            response.data["detected_region"]["service_city"]["id"],
            self.service_city.id,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.market_region_service_city_id, self.remote_city.id)

    def test_market_region_detect_general_region_suggests_switch(self):
        self.select_general_region()
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "36.7525000",
                "longitude": "3.0419000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "suggest_switch")
        self.assertEqual(
            response.data["current_selection"]["mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertIsNone(response.data["current_selection"]["service_city"])
        self.assertEqual(
            response.data["detected_region"]["service_city"]["id"],
            self.service_city.id,
        )

    def test_market_region_detect_general_unsupported_location_x_same_region(self):
        self.select_general_region()
        selected_at = self.user.market_region_updated_at
        city_count = ServiceCity.objects.count()
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "0.0000000",
                "longitude": "0.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "same_region")
        self.assertEqual(
            response.data["current_selection"]["mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertEqual(
            response.data["detected_region"]["mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertIsNone(response.data["detected_region"]["service_city"])
        self.assertEqual(ServiceCity.objects.count(), city_count)
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.market_region_mode,
            User.MarketRegionMode.GENERAL,
        )
        self.assertIsNone(self.user.market_region_service_city_id)
        self.assertEqual(self.user.market_region_updated_at, selected_at)

    def test_market_region_detect_general_unsupported_location_y_same_region(self):
        self.select_general_region()
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "-20.0000000",
                "longitude": "120.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "same_region")
        self.assertEqual(
            response.data["detected_region"]["mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertIsNone(response.data["detected_region"]["service_city"])

    def test_market_region_detect_general_unsupported_locations_share_region(self):
        self.select_general_region()
        city_count = ServiceCity.objects.count()
        self.authenticate()

        responses = [
            self.client.post(
                "/api/v1/market-region/detect/",
                {"latitude": latitude, "longitude": longitude},
                format="json",
            )
            for latitude, longitude in (
                ("0.0000000", "0.0000000"),
                ("-20.0000000", "120.0000000"),
            )
        ]

        self.assertTrue(
            all(response.status_code == status.HTTP_200_OK for response in responses)
        )
        self.assertTrue(
            all(response.data["action"] == "same_region" for response in responses)
        )
        self.assertEqual(
            responses[0].data["detected_region"],
            responses[1].data["detected_region"],
        )
        self.assertEqual(ServiceCity.objects.count(), city_count)

    def test_market_region_detect_no_selection_selects_detected_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "36.7525000",
                "longitude": "3.0419000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "select_detected_region")
        self.assertIsNone(response.data["current_selection"])
        self.assertEqual(
            response.data["detected_region"]["service_city"]["id"],
            self.service_city.id,
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.market_region_mode)
        self.assertIsNone(self.user.market_region_service_city_id)

    def test_market_region_detect_unsupported_location(self):
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "0.0000000",
                "longitude": "0.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "unsupported_location")
        self.assertIsNone(response.data["detected_region"])
        self.assertEqual(
            response.data["current_selection"]["service_city"]["id"],
            self.service_city.id,
        )

    def test_market_region_detect_rejects_invalid_latitude(self):
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "91.0000000",
                "longitude": "3.0419000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.data)

    def test_market_region_detect_rejects_invalid_longitude(self):
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "36.7525000",
                "longitude": "181.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", response.data)

    def test_market_region_detect_ignores_inactive_service_city(self):
        ServiceCity.objects.create(
            name="Inactive GPS City",
            center_latitude=Decimal("10.0000000"),
            center_longitude=Decimal("10.0000000"),
            radius_km=Decimal("50.00"),
            is_active=False,
        )
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "10.0000000",
                "longitude": "10.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "unsupported_location")
        self.assertIsNone(response.data["detected_region"])

    def test_market_region_detect_ignores_service_city_without_geo_fields(self):
        ServiceCity.objects.create(name="No Geo City")
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "10.0000000",
                "longitude": "10.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "unsupported_location")
        self.assertIsNone(response.data["detected_region"])

    def test_market_region_detect_returns_nearest_matching_service_city(self):
        farther_city = ServiceCity.objects.create(
            name="Farther GPS City",
            center_latitude=Decimal("10.0500000"),
            center_longitude=Decimal("10.0000000"),
            radius_km=Decimal("10.00"),
        )
        nearer_city = ServiceCity.objects.create(
            name="Nearer GPS City",
            center_latitude=Decimal("10.0100000"),
            center_longitude=Decimal("10.0000000"),
            radius_km=Decimal("10.00"),
        )
        self.authenticate()

        response = self.client.post(
            "/api/v1/market-region/detect/",
            {
                "latitude": "10.0000000",
                "longitude": "10.0000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "suggest_switch")
        self.assertEqual(
            response.data["detected_region"]["service_city"]["id"],
            nearer_city.id,
        )
        self.assertNotEqual(
            response.data["detected_region"]["service_city"]["id"],
            farther_city.id,
        )

    def test_home_requires_saved_market_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])
        self.assertIsNone(response.data["current_selection"])

    def test_home_returns_limited_content_from_user_location_only(self):
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/")

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

    def test_home_returns_general_region_content_only(self):
        general_classification = MarketClassification.objects.create(
            name="General stores"
        )
        general_market = Market.objects.create(
            name="General Market",
            branch="Online",
            scope=Market.Scope.GENERAL,
            classification=general_classification,
        )
        general_market.service_cities.add(self.service_city)
        general_product = self._create_product(
            "General Product",
            general_market,
            1000,
        )
        general_offer = Offer.objects.create(
            market=general_market,
            scope=Offer.Scope.GENERAL,
            service_city=None,
            title="General Offer",
            description="General offer",
            type=Offer.OfferType.DISCOUNT,
            discount=Decimal("5.00"),
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1),
            status=Offer.Status.ACTIVE,
        )
        general_offer.products.set([general_product])
        self.select_general_region()
        self.authenticate()

        first_detect_response = self.client.post(
            "/api/v1/market-region/detect/",
            {"latitude": "0.0000000", "longitude": "0.0000000"},
            format="json",
        )
        second_detect_response = self.client.post(
            "/api/v1/market-region/detect/",
            {"latitude": "-20.0000000", "longitude": "120.0000000"},
            format="json",
        )
        response = self.client.get(f"{HOME_BASE}/")

        self.assertEqual(
            first_detect_response.data["action"],
            "same_region",
        )
        self.assertEqual(
            second_detect_response.data["action"],
            "same_region",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["current_selection"]["mode"],
            User.MarketRegionMode.GENERAL,
        )
        self.assertEqual(
            {product["id"] for product in response.data["products"]},
            {general_product.id},
        )
        self.assertEqual(
            {offer["id"] for offer in response.data["offers"]},
            {general_offer.id},
        )

    def test_market_classification_crud_requires_admin_role(self):
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/market-classifications/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["detail"],
            "Only admin users can manage markets.",
        )

    def test_admin_can_create_read_update_and_delete_market_classification(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{HOME_BASE}/market-classifications/",
            {"name": " صيدليات "},
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "صيدليات")
        self.assertEqual(
            create_response.data["classification_type"],
            MarketClassification.ClassificationType.NORMAL,
        )
        classification_id = create_response.data["id"]

        list_response = self.client.get(f"{HOME_BASE}/market-classifications/")
        detail_response = self.client.get(
            f"{HOME_BASE}/market-classifications/{classification_id}/"
        )
        update_response = self.client.patch(
            f"{HOME_BASE}/market-classifications/{classification_id}/",
            {
                "name": "محلات",
                "classification_type": MarketClassification.ClassificationType.POPULAR,
            },
        )
        delete_response = self.client.delete(
            f"{HOME_BASE}/market-classifications/{classification_id}/"
        )
        deleted_detail_response = self.client.get(
            f"{HOME_BASE}/market-classifications/{classification_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(classification_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "صيدليات")
        self.assertEqual(
            detail_response.data["classification_type"],
            MarketClassification.ClassificationType.NORMAL,
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "محلات")
        self.assertEqual(
            update_response.data["classification_type"],
            MarketClassification.ClassificationType.POPULAR,
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_admin_can_create_market_classifications_with_each_type(self):
        self.authenticate(self.admin)

        normal_response = self.client.post(
            f"{HOME_BASE}/market-classifications/",
            {
                "name": "Normal classification",
                "classification_type": MarketClassification.ClassificationType.NORMAL,
            },
            format="json",
        )
        popular_response = self.client.post(
            f"{HOME_BASE}/market-classifications/",
            {
                "name": "Popular classification",
                "classification_type": MarketClassification.ClassificationType.POPULAR,
            },
            format="json",
        )
        featured_response = self.client.post(
            f"{HOME_BASE}/market-classifications/",
            {
                "name": "Featured classification",
                "classification_type": MarketClassification.ClassificationType.FEATURED,
            },
            format="json",
        )

        self.assertEqual(normal_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(popular_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(featured_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            normal_response.data["classification_type"],
            MarketClassification.ClassificationType.NORMAL,
        )
        self.assertEqual(
            popular_response.data["classification_type"],
            MarketClassification.ClassificationType.POPULAR,
        )
        self.assertEqual(
            featured_response.data["classification_type"],
            MarketClassification.ClassificationType.FEATURED,
        )

    def test_admin_market_classification_rejects_invalid_type(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{HOME_BASE}/market-classifications/",
            {
                "name": "Invalid type classification",
                "classification_type": "invalid",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("classification_type", response.data)

    def test_market_classification_defaults_to_normal_type(self):
        classification = MarketClassification.objects.create(name="Default Type")

        self.assertEqual(
            classification.classification_type,
            MarketClassification.ClassificationType.NORMAL,
        )

    def test_market_classification_delete_rejects_used_classification(self):
        self.authenticate(self.admin)

        response = self.client.delete(
            f"{HOME_BASE}/market-classifications/"
            f"{self.local_classification.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_market_crud_requires_admin_role(self):
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/markets/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_market(self):
        classification = MarketClassification.objects.create(name="صيدليات")
        updated_classification = MarketClassification.objects.create(name="محلات")
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{HOME_BASE}/markets/",
            {
                "classification_id": classification.id,
                "name": " سوق جديد ",
                "branch": " فرع أول ",
                "status": Market.Status.ACTIVE,
                "delivery_areas": [self.local_area.id],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "سوق جديد")
        self.assertEqual(create_response.data["branch"], "فرع أول")
        self.assertEqual(
            create_response.data["classification"]["id"],
            classification.id,
        )
        self.assertEqual(
            [area["id"] for area in create_response.data["delivery_areas"]],
            [self.local_area.id],
        )
        market_id = create_response.data["id"]

        list_response = self.client.get(f"{HOME_BASE}/markets/")
        detail_response = self.client.get(f"{HOME_BASE}/markets/{market_id}/")
        update_response = self.client.patch(
            f"{HOME_BASE}/markets/{market_id}/",
            {
                "classification_id": updated_classification.id,
                "name": "سوق محدث",
                "status": Market.Status.INACTIVE,
                "delivery_areas": [self.remote_area.id],
            },
            format="json",
        )
        delete_response = self.client.delete(f"{HOME_BASE}/markets/{market_id}/")
        deleted_detail_response = self.client.get(f"{HOME_BASE}/markets/{market_id}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(market_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "سوق جديد")
        listed_market = next(
            item for item in list_response.data if item["id"] == market_id
        )
        self.assertEqual(
            [area["id"] for area in listed_market["delivery_areas"]],
            [self.local_area.id],
        )
        self.assertEqual(
            [area["id"] for area in detail_response.data["delivery_areas"]],
            [self.local_area.id],
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "سوق محدث")
        self.assertEqual(update_response.data["status"], Market.Status.INACTIVE)
        self.assertEqual(
            update_response.data["classification"]["id"],
            updated_classification.id,
        )
        self.assertEqual(
            [area["id"] for area in update_response.data["delivery_areas"]],
            [self.remote_area.id],
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_classification_summary_requires_authentication(self):
        response = self.client.get(f"{HOME_BASE}/classifications/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_classification_summary_requires_saved_market_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/classifications/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_classification_summary_returns_common_and_all_counts(self):
        busiest_classification = MarketClassification.objects.create(
            name="Busiest local"
        )
        medium_classification = MarketClassification.objects.create(
            name="Medium local"
        )
        quiet_classification = MarketClassification.objects.create(
            name="Quiet local"
        )
        busiest_market = self._create_market(
            "Busiest Market",
            busiest_classification,
            self.local_area,
        )
        medium_market = self._create_market(
            "Medium Market",
            medium_classification,
            self.local_area,
        )
        quiet_market = self._create_market(
            "Quiet Market",
            quiet_classification,
            self.local_area,
        )
        extra_busiest_markets = [
            self._create_market(
                f"Busiest Extra Market {index}",
                busiest_classification,
                self.local_area,
            )
            for index in range(6)
        ]
        for index in range(6):
            self._create_product(
                f"Busiest Product {index}",
                busiest_market,
                200 + index,
            )
        for index, market in enumerate(extra_busiest_markets):
            self._create_product(
                f"Busiest Extra Product {index}",
                market,
                250 + index,
            )
        for index in range(4):
            self._create_product(
                f"Medium Product {index}",
                medium_market,
                300 + index,
            )
        for index in range(2):
            self._create_product(
                f"Quiet Product {index}",
                quiet_market,
                400 + index,
            )

        self.authenticate()
        response = self.client.get(f"{HOME_BASE}/classifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.keys(),
            {"common_market_classifications", "market_classifications"},
        )
        self.assertEqual(len(response.data["common_market_classifications"]), 4)

        common_by_name = {
            classification["name"]: classification["product_count"]
            for classification in response.data["common_market_classifications"]
        }
        self.assertEqual(common_by_name["Busiest local"], 12)
        self.assertEqual(common_by_name["Local restaurants"], 5)
        self.assertEqual(common_by_name["Local supermarkets"], 5)
        self.assertEqual(common_by_name["Medium local"], 4)
        self.assertNotIn("Quiet local", common_by_name)
        self.assertNotIn("Remote bakeries", common_by_name)

        all_by_name = {
            classification["name"]: classification
            for classification in response.data["market_classifications"]
        }
        self.assertEqual(
            all_by_name["Local supermarkets"]["classification_type"],
            MarketClassification.ClassificationType.POPULAR,
        )
        self.assertEqual(
            all_by_name["Local restaurants"]["classification_type"],
            MarketClassification.ClassificationType.FEATURED,
        )
        self.assertEqual(all_by_name["Busiest local"]["product_count"], 12)
        self.assertEqual(all_by_name["Local restaurants"]["product_count"], 5)
        self.assertEqual(all_by_name["Local supermarkets"]["product_count"], 5)
        self.assertEqual(all_by_name["Medium local"]["product_count"], 4)
        self.assertEqual(all_by_name["Quiet local"]["product_count"], 2)
        self.assertNotIn("Remote bakeries", all_by_name)
        self.assertEqual(len(all_by_name["Busiest local"]["markets"]), 5)
        self.assertEqual(len(all_by_name["Quiet local"]["markets"]), 1)
        busiest_market_payload = all_by_name["Busiest local"]["markets"][0]
        self.assertIn("product_count", busiest_market_payload)
        self.assertIn("products", busiest_market_payload)
        self.assertNotIn("delivery_areas", busiest_market_payload)
        self.assertGreaterEqual(busiest_market_payload["product_count"], 1)
        self.assertGreaterEqual(len(busiest_market_payload["products"]), 1)
        self.assertTrue(
            all(
                "market" not in product and "variants" not in product
                for market in all_by_name["Busiest local"]["markets"]
                for product in market["products"]
            )
        )

    def test_typed_classification_endpoints_return_only_requested_type(self):
        normal_classification = MarketClassification.objects.create(
            name="Normal local",
            classification_type=MarketClassification.ClassificationType.NORMAL,
        )
        normal_market = self._create_market(
            "Normal Market",
            normal_classification,
            self.local_area,
        )
        self._create_product("Normal Product", normal_market, 700)
        self.authenticate()

        featured_response = self.client.get(f"{HOME_BASE}/classifications/featured/")
        popular_response = self.client.get(f"{HOME_BASE}/classifications/popular/")
        normal_response = self.client.get(f"{HOME_BASE}/classifications/normal/")

        self.assertEqual(featured_response.status_code, status.HTTP_200_OK)
        self.assertEqual(popular_response.status_code, status.HTTP_200_OK)
        self.assertEqual(normal_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {
                item["classification_type"]
                for item in featured_response.data["classifications"]
            },
            {MarketClassification.ClassificationType.FEATURED},
        )
        self.assertEqual(
            {
                item["classification_type"]
                for item in popular_response.data["classifications"]
            },
            {MarketClassification.ClassificationType.POPULAR},
        )
        self.assertEqual(
            {
                item["classification_type"]
                for item in normal_response.data["classifications"]
            },
            {MarketClassification.ClassificationType.NORMAL},
        )
        self.assertEqual(
            [item["id"] for item in featured_response.data["classifications"]],
            [self.second_local_classification.id],
        )
        self.assertIn(
            self.local_classification.id,
            [item["id"] for item in popular_response.data["classifications"]],
        )
        self.assertEqual(
            [item["id"] for item in normal_response.data["classifications"]],
            [normal_classification.id],
        )
        self.assertEqual(
            featured_response.data["current_selection"]["service_city"]["id"],
            self.service_city.id,
        )
        self.assertTrue(normal_response.data["classifications"][0]["markets"])

    def test_typed_classification_endpoint_requires_saved_market_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/classifications/featured/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_classification_endpoints_filter_general_region_markets(self):
        general_classification = MarketClassification.objects.create(
            name="General featured",
            classification_type=MarketClassification.ClassificationType.FEATURED,
        )
        general_market = Market.objects.create(
            classification=general_classification,
            name="General Featured Market",
            scope=Market.Scope.GENERAL,
        )
        general_market.service_cities.add(self.service_city)
        self._create_product("General Featured Product", general_market, 701)
        self.user.market_region_mode = User.MarketRegionMode.GENERAL
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = timezone.now()
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        all_response = self.client.get(f"{HOME_BASE}/classifications/")
        featured_response = self.client.get(f"{HOME_BASE}/classifications/featured/")

        self.assertEqual(all_response.status_code, status.HTTP_200_OK)
        self.assertEqual(featured_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in all_response.data["market_classifications"]],
            [general_classification.id],
        )
        self.assertEqual(
            [item["id"] for item in featured_response.data["classifications"]],
            [general_classification.id],
        )
        self.assertEqual(
            featured_response.data["classifications"][0]["markets"][0]["id"],
            general_market.id,
        )

    def test_classification_markets_requires_authentication(self):
        response = self.client.get(
            f"{HOME_BASE}/classifications/"
            f"{self.local_classification.id}/markets/"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_classification_markets_returns_covered_markets_with_products(self):
        for index in range(3):
            self._create_product(
                f"Extra Local Product {index}",
                self.local_market,
                500 + index,
            )

        self.authenticate()
        response = self.client.get(
            f"{HOME_BASE}/classifications/"
            f"{self.local_classification.id}/markets/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["classification"],
            {
                "id": self.local_classification.id,
                "name": self.local_classification.name,
                "classification_type": (
                    MarketClassification.ClassificationType.POPULAR
                ),
            },
        )
        self.assertEqual(len(response.data["markets"]), 1)

        market = response.data["markets"][0]
        self.assertEqual(market["id"], self.local_market.id)
        self.assertEqual(len(market["products"]), 3)
        self.assertNotIn("variants", market["products"][0])
        self.assertNotIn("market", market["products"][0])

    def test_classification_markets_excludes_remote_markets(self):
        self.authenticate()
        response = self.client.get(
            f"{HOME_BASE}/classifications/"
            f"{self.remote_classification.id}/markets/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["markets"], [])

    def test_classification_markets_returns_not_found_for_unknown_id(self):
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/classifications/99999/markets/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_search_requires_authentication(self):
        response = self.client.get(f"{HOME_BASE}/search/", {"q": "Local"})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_product_search_requires_saved_market_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/search/", {"q": "Local"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_product_search_matches_product_market_and_classification(self):
        unique_product = self._create_product(
            "Unique Search Item",
            self.local_market,
            700,
        )
        self.authenticate()

        product_response = self.client.get(
            f"{HOME_BASE}/search/",
            {"q": unique_product.name},
        )
        market_response = self.client.get(
            f"{HOME_BASE}/search/",
            {"q": "Local Kitchen"},
        )
        classification_response = self.client.get(
            f"{HOME_BASE}/search/",
            {"q": "Local restaurants"},
        )

        self.assertEqual(product_response.status_code, status.HTTP_200_OK)
        self.assertEqual(market_response.status_code, status.HTTP_200_OK)
        self.assertEqual(classification_response.status_code, status.HTTP_200_OK)

        self.assertEqual(product_response.data["count"], 1)
        self.assertEqual(
            product_response.data["results"][0]["name"],
            unique_product.name,
        )

        self.assertEqual(market_response.data["count"], 5)
        self.assertTrue(
            all(
                product["market"]["id"] == self.second_local_market.id
                for product in market_response.data["results"]
            )
        )
        self.assertEqual(classification_response.data["count"], 5)
        self.assertTrue(
            all(
                product["market"]["classification_id"]
                == self.second_local_classification.id
                for product in classification_response.data["results"]
            )
        )

    def test_product_search_is_limited_to_user_address_and_paginated(self):
        for index in range(11):
            self._create_product(
                f"Paged Local Product {index}",
                self.local_market,
                600 + index,
            )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/search/", {"q": "Product"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 21)
        self.assertEqual(len(response.data["results"]), 4)
        self.assertIsNotNone(response.data["next"])
        self.assertTrue(
            all(
                product["market"]["id"]
                in {self.local_market.id, self.second_local_market.id}
                for product in response.data["results"]
            )
        )
        self.assertTrue(
            all(
                product["name"] != self.remote_product.name
                for product in response.data["results"]
            )
        )

    def test_address_products_requires_client_role(self):
        self.authenticate(self.admin)

        response = self.client.get(f"{HOME_BASE}/products/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["detail"],
            "Only client users can access address products.",
        )

    def test_address_products_requires_saved_market_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/products/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_address_products_returns_user_address_products_paginated_by_four(self):
        unavailable_product = self.local_products[0]
        unavailable_product.is_available = False
        unavailable_product.save(update_fields=["is_available"])
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/products/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 9)
        self.assertEqual(len(response.data["results"]), 4)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        local_market_ids = {self.local_market.id, self.second_local_market.id}
        self.assertTrue(
            all(
                product["market"]["id"] in local_market_ids
                for product in response.data["results"]
            )
        )
        self.assertNotIn(
            self.remote_product.id,
            {product["id"] for product in response.data["results"]},
        )
        self.assertNotIn(
            unavailable_product.id,
            {product["id"] for product in response.data["results"]},
        )

    def test_address_products_second_page_uses_page_size_four(self):
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/products/", {"page": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 10)
        self.assertEqual(len(response.data["results"]), 4)
        self.assertIsNotNone(response.data["previous"])

    def test_address_products_can_order_by_name(self):
        self.authenticate()

        response = self.client.get(
            f"{HOME_BASE}/products/",
            {"order_by_name": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [product["name"] for product in response.data["results"]],
            [
                "Local Product 1",
                "Local Product 10",
                "Local Product 2",
                "Local Product 3",
            ],
        )

    def test_address_products_can_order_by_high_price(self):
        self.authenticate()

        response = self.client.get(
            f"{HOME_BASE}/products/",
            {"order_by_high_price": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [product["name"] for product in response.data["results"]],
            [
                "Local Product 10",
                "Local Product 9",
                "Local Product 8",
                "Local Product 7",
            ],
        )

    def test_address_products_can_order_by_low_price(self):
        self.authenticate()

        response = self.client.get(
            f"{HOME_BASE}/products/",
            {"order_by_low_price": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [product["name"] for product in response.data["results"]],
            [
                "Local Product 1",
                "Local Product 2",
                "Local Product 3",
                "Local Product 4",
            ],
        )

    def test_address_products_can_order_by_latest(self):
        self.authenticate()

        response = self.client.get(
            f"{HOME_BASE}/products/",
            {"order_by_latest": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [product["name"] for product in response.data["results"]],
            [
                "Local Product 10",
                "Local Product 9",
                "Local Product 8",
                "Local Product 7",
            ],
        )

    def test_address_products_rejects_multiple_order_params(self):
        self.authenticate()

        response = self.client.get(
            f"{HOME_BASE}/products/",
            {
                "order_by_name": "true",
                "order_by_low_price": "true",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Use only one order parameter at a time.",
        )

    def test_product_detail_requires_authentication(self):
        response = self.client.get(f"{HOME_BASE}/products/{self.local_products[0].id}/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_product_detail_requires_saved_market_region(self):
        self.user.market_region_mode = None
        self.user.market_region_service_city = None
        self.user.market_region_updated_at = None
        self.user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/products/{self.local_products[0].id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_product_detail_returns_all_product_information(self):
        product = self.local_products[0]
        attribute = CategoryAttribute.objects.create(
            category=self.category,
            name="Size",
        )
        option = CategoryOption.objects.create(
            attribute=attribute,
            value="Large",
        )
        ProductAttributeValue.objects.create(
            product=product,
            attribute=attribute,
            option=option,
        )
        variant = product.variants.first()
        VariantAttributeValue.objects.create(
            variant=variant,
            attribute=attribute,
            option=option,
        )
        addition_classification = AdditionClassification.objects.create(
            name="Extras"
        )
        addition = ProductAddition.objects.create(
            classification=addition_classification,
            name_ar="جبن",
            name_en="Cheese",
            price=Decimal("120.00"),
        )
        addition.products.add(product)
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], product.id)
        self.assertEqual(response.data["market"]["id"], self.local_market.id)
        self.assertEqual(response.data["category"]["id"], self.category.id)
        self.assertEqual(response.data["attribute_values"][0]["attribute_name"], "Size")
        self.assertEqual(response.data["attribute_values"][0]["option_value"], "Large")
        self.assertEqual(response.data["variants"][0]["id"], variant.id)
        self.assertEqual(
            response.data["variants"][0]["attribute_values"][0]["option_value"],
            "Large",
        )
        self.assertEqual(response.data["additions"][0]["name_en"], "Cheese")
        self.assertEqual(
            response.data["additions"][0]["classification_name"],
            "Extras",
        )
        self.assertIn("created_at", response.data)
        self.assertIn("updated_at", response.data)

    def test_product_detail_returns_not_found_for_remote_product(self):
        self.authenticate()

        response = self.client.get(f"{HOME_BASE}/products/{self.remote_product.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def _create_market(self, name, classification, area):
        market = Market.objects.create(
            name=name,
            branch=name,
            classification=classification,
        )
        market.delivery_areas.add(area)
        market.service_cities.add(area.service_city)
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
            scope=Offer.Scope.SERVICE_CITY,
            service_city=market.service_cities.filter(is_active=True).first(),
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
