from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from markets.models import Market, MarketClassification

from .models import (
    AdditionClassification,
    CategoryClassification,
    Product,
    ProductAddition,
    ProductCategory,
)

User = get_user_model()
CATALOG_BASE = "/api/v1/catalog"


class AdditionClassificationAPITests(APITestCase):
    password = "Password1!"

    def setUp(self):
        self.admin = User.objects.create_user(
            username="catalog_admin",
            email="catalog-admin@example.com",
            phone="+213555400001",
            password=self.password,
            role=User.Role.ADMIN,
            is_active=True,
        )
        self.client_user = User.objects.create_user(
            username="catalog_client",
            email="catalog-client@example.com",
            phone="+213555400002",
            password=self.password,
            role=User.Role.CLIENT,
            is_active=True,
        )
        market_classification = MarketClassification.objects.create(
            name="مطعم"
        )
        self.market = Market.objects.create(
            classification=market_classification,
            name="مطعم الاختبار",
        )
        category_classification = CategoryClassification.objects.create(
            name="وجبات"
        )
        self.category = ProductCategory.objects.create(
            classification=category_classification,
            name="وجبات رئيسية",
        )
        self.product = Product.objects.create(
            market=self.market,
            category=self.category,
            name="كسكس",
            description="طبق كسكس",
        )

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def test_addition_classification_create_requires_authentication(self):
        response = self.client.post(
            f"{CATALOG_BASE}/addition-classifications/",
            {"name": "صلصات"},
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_addition_classification_create_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.post(
            f"{CATALOG_BASE}/addition-classifications/",
            {"name": "صلصات"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["detail"],
            "Only admin users can manage catalog data.",
        )

    def test_admin_can_create_addition_classification(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/addition-classifications/",
            {"name": " صلصات "},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "صلصات")
        self.assertTrue(
            AdditionClassification.objects.filter(name="صلصات").exists()
        )

    def test_duplicate_addition_classification_name_is_rejected(self):
        AdditionClassification.objects.create(name="صلصات")
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/addition-classifications/",
            {"name": "صلصات"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["name"],
            ["An addition classification with this name already exists."],
        )

    def test_product_addition_create_requires_authentication(self):
        classification = AdditionClassification.objects.create(name="إضافات")

        response = self.client.post(
            f"{CATALOG_BASE}/product-additions/",
            {
                "classification_id": classification.id,
                "name_ar": "جبن",
                "name_en": "Cheese",
                "price": "120.00",
                "is_active": True,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_product_addition_create_requires_admin_role(self):
        classification = AdditionClassification.objects.create(name="إضافات")
        self.authenticate(self.client_user)

        response = self.client.post(
            f"{CATALOG_BASE}/product-additions/",
            {
                "classification_id": classification.id,
                "name_ar": "جبن",
                "name_en": "Cheese",
                "price": "120.00",
                "is_active": True,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_product_addition(self):
        classification = AdditionClassification.objects.create(name="إضافات")
        updated_classification = AdditionClassification.objects.create(
            name="صلصات"
        )
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{CATALOG_BASE}/product-additions/",
            {
                "classification_id": classification.id,
                "name_ar": " جبن ",
                "name_en": " Cheese ",
                "price": "120.00",
                "is_active": True,
            },
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name_ar"], "جبن")
        self.assertEqual(create_response.data["name_en"], "Cheese")
        self.assertEqual(create_response.data["price"], "120.00")
        self.assertEqual(
            create_response.data["classification"]["id"],
            classification.id,
        )
        self.assertEqual(create_response.data["products"], [])

        addition = ProductAddition.objects.get(id=create_response.data["id"])
        self.assertEqual(addition.price, Decimal("120.00"))
        addition.products.add(self.product)

        list_response = self.client.get(f"{CATALOG_BASE}/product-additions/")
        detail_response = self.client.get(
            f"{CATALOG_BASE}/product-additions/{addition.id}/"
        )
        update_response = self.client.patch(
            f"{CATALOG_BASE}/product-additions/{addition.id}/",
            {
                "classification_id": updated_classification.id,
                "name_ar": "صلصة حارة",
                "price": "150.00",
                "is_active": False,
            },
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/product-additions/{addition.id}/"
        )
        deleted_detail_response = self.client.get(
            f"{CATALOG_BASE}/product-additions/{addition.id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(addition.id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail_response.data["products"],
            [self.product.id],
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name_ar"], "صلصة حارة")
        self.assertEqual(update_response.data["price"], "150.00")
        self.assertFalse(update_response.data["is_active"])
        self.assertEqual(
            update_response.data["classification"]["id"],
            updated_classification.id,
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertFalse(ProductAddition.objects.filter(id=addition.id).exists())
