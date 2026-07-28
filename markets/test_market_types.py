from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import StoreSubcategory

from .models import Market, MarketClassification, MarketType
from .serializers import HomeMarketSerializer


User = get_user_model()


def image_upload(name="type.png", color="orange"):
    content = BytesIO()
    Image.new("RGB", (4, 4), color=color).save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT="/tmp/yalla-market-type-tests")
class MarketTypeAPITests(APITestCase):
    list_url = "/api/v1/home/market-types/"

    def setUp(self):
        self.admin = User.objects.create_user(
            username="market_type_admin",
            email="market-type-admin@example.com",
            phone="+213555981001",
            password="Password1!",
            role=User.Role.ADMIN,
        )
        self.classification = MarketClassification.objects.create(
            name="Restaurants"
        )
        self.other_classification = MarketClassification.objects.create(
            name="Furniture"
        )
        self.market = Market.objects.create(
            classification=self.classification,
            name="Mixed Kitchen",
            scope=Market.Scope.GENERAL,
        )
        self.subcategory = StoreSubcategory.objects.create(
            name_ar="الوجبات",
            name_en="Meals",
        )
        self.market.subcategories.add(self.subcategory)
        self.client.force_authenticate(self.admin)

    def create_type(self, *, classification=None, name_ar="برجر", name_en="Burger"):
        return MarketType.objects.create(
            classification=classification or self.classification,
            name_ar=name_ar,
            name_en=name_en,
            image=image_upload(f"{name_en}.png"),
        )

    def test_admin_can_create_list_update_and_delete_market_type(self):
        response = self.client.post(
            self.list_url,
            {
                "classification_id": self.classification.id,
                "name_ar": "برجر",
                "name_en": "Burger",
                "image": image_upload(),
                "sort_order": 2,
                "is_active": True,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        market_type_id = response.data["id"]
        self.assertEqual(response.data["classification_id"], self.classification.id)

        list_response = self.client.get(
            self.list_url,
            {"classification_id": self.classification.id},
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in list_response.data], [market_type_id])

        update_response = self.client.patch(
            f"{self.list_url}{market_type_id}/",
            {"name_en": "Burgers", "sort_order": 1},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name_en"], "Burgers")

        delete_response = self.client.delete(f"{self.list_url}{market_type_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MarketType.objects.filter(id=market_type_id).exists())

    def test_names_are_unique_per_classification_only(self):
        self.create_type()

        duplicate = self.client.post(
            self.list_url,
            {
                "classification_id": self.classification.id,
                "name_ar": "بـرجر".replace("ـ", ""),
                "name_en": "burger",
                "image": image_upload("duplicate.png"),
            },
            format="multipart",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        other_classification = self.client.post(
            self.list_url,
            {
                "classification_id": self.other_classification.id,
                "name_ar": "برجر",
                "name_en": "Burger",
                "image": image_upload("other.png"),
            },
            format="multipart",
        )
        self.assertEqual(other_classification.status_code, status.HTTP_201_CREATED)

    def test_market_accepts_multiple_active_types_from_its_classification(self):
        burger = self.create_type()
        grills = self.create_type(name_ar="مشويات", name_en="Grills")

        response = self.client.patch(
            f"/api/v1/home/markets/{self.market.id}/",
            {"market_type_ids": [burger.id, grills.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data["market_types"]},
            {burger.id, grills.id},
        )
        self.assertEqual(
            set(
                HomeMarketSerializer(
                    self.market,
                    context={"request": response.wsgi_request},
                ).data["market_type_ids"]
            ),
            {burger.id, grills.id},
        )

    def test_market_rejects_type_from_another_classification(self):
        furniture_type = self.create_type(
            classification=self.other_classification,
            name_ar="غرف نوم",
            name_en="Bedrooms",
        )

        response = self.client.patch(
            f"/api/v1/home/markets/{self.market.id}/",
            {"market_type_ids": [furniture_type.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("market_type_ids", response.data)

    def test_market_rejects_inactive_type(self):
        inactive_type = self.create_type()
        inactive_type.is_active = False
        inactive_type.save(update_fields=("is_active",))

        response = self.client.patch(
            f"/api/v1/home/markets/{self.market.id}/",
            {"market_type_ids": [inactive_type.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("market_type_ids", response.data)
