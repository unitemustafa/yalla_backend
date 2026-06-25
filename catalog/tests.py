from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from markets.models import Market, MarketClassification

from .models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductCategory,
    ProductAttributeValue,
    ProductVariant,
    VariantAttributeValue,
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
        self.size_attribute = CategoryAttribute.objects.create(
            category=self.category,
            name="الحجم",
        )
        self.small_option = CategoryOption.objects.create(
            attribute=self.size_attribute,
            value="صغير",
        )
        self.large_option = CategoryOption.objects.create(
            attribute=self.size_attribute,
            value="كبير",
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

    def test_category_classification_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/category-classifications/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_category_classification(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{CATALOG_BASE}/category-classifications/",
            {"name": " مشروبات "},
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "مشروبات")
        classification_id = create_response.data["id"]

        list_response = self.client.get(f"{CATALOG_BASE}/category-classifications/")
        detail_response = self.client.get(
            f"{CATALOG_BASE}/category-classifications/{classification_id}/"
        )
        update_response = self.client.patch(
            f"{CATALOG_BASE}/category-classifications/{classification_id}/",
            {"name": "حلويات"},
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/category-classifications/{classification_id}/"
        )
        deleted_detail_response = self.client.get(
            f"{CATALOG_BASE}/category-classifications/{classification_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(classification_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "مشروبات")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "حلويات")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_category_classification_delete_rejects_used_classification(self):
        self.authenticate(self.admin)

        response = self.client.delete(
            f"{CATALOG_BASE}/category-classifications/"
            f"{self.category.classification_id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_product_category_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/product-categories/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_product_category(self):
        classification = CategoryClassification.objects.create(name="مشروبات")
        updated_classification = CategoryClassification.objects.create(
            name="حلويات"
        )
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{CATALOG_BASE}/product-categories/",
            {
                "classification_id": classification.id,
                "name": " عصائر ",
                "type": " beverage ",
                "description": "مشروبات طازجة",
            },
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "عصائر")
        self.assertEqual(create_response.data["type"], "beverage")
        self.assertEqual(
            create_response.data["classification"]["id"],
            classification.id,
        )
        category_id = create_response.data["id"]

        list_response = self.client.get(f"{CATALOG_BASE}/product-categories/")
        detail_response = self.client.get(
            f"{CATALOG_BASE}/product-categories/{category_id}/"
        )
        update_response = self.client.patch(
            f"{CATALOG_BASE}/product-categories/{category_id}/",
            {
                "classification_id": updated_classification.id,
                "name": "كيك",
                "description": "حلويات يومية",
            },
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/product-categories/{category_id}/"
        )
        deleted_detail_response = self.client.get(
            f"{CATALOG_BASE}/product-categories/{category_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(category_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "عصائر")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "كيك")
        self.assertEqual(
            update_response.data["classification"]["id"],
            updated_classification.id,
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_product_category_delete_rejects_used_category(self):
        self.authenticate(self.admin)

        response = self.client.delete(
            f"{CATALOG_BASE}/product-categories/{self.category.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_product_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/products/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_product(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "category_id": self.category.id,
                "is_available": True,
                "name": " طبق جديد ",
                "description": "طبق تجريبي",
                "discount": "10.00",
                "attribute_values": [
                    {
                        "attribute_id": self.size_attribute.id,
                        "option_id": self.small_option.id,
                    }
                ],
                "variants": [
                    {
                        "price": "500.00",
                        "sku": " MEAL-S ",
                        "attribute_values": [
                            {
                                "attribute_id": self.size_attribute.id,
                                "option_id": self.small_option.id,
                            }
                        ],
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "طبق جديد")
        self.assertEqual(create_response.data["market"]["id"], self.market.id)
        self.assertEqual(create_response.data["category"]["id"], self.category.id)
        self.assertEqual(
            create_response.data["attribute_values"][0]["option"]["id"],
            self.small_option.id,
        )
        self.assertEqual(create_response.data["variants"][0]["sku"], "MEAL-S")
        product_id = create_response.data["id"]

        self.assertTrue(
            ProductAttributeValue.objects.filter(
                product_id=product_id,
                attribute=self.size_attribute,
                option=self.small_option,
            ).exists()
        )
        variant = ProductVariant.objects.get(product_id=product_id)
        self.assertTrue(
            VariantAttributeValue.objects.filter(
                variant=variant,
                attribute=self.size_attribute,
                option=self.small_option,
            ).exists()
        )

        list_response = self.client.get(f"{CATALOG_BASE}/products/")
        detail_response = self.client.get(f"{CATALOG_BASE}/products/{product_id}/")
        update_response = self.client.patch(
            f"{CATALOG_BASE}/products/{product_id}/",
            {
                "name": "طبق محدث",
                "is_available": False,
                "attribute_values": [
                    {
                        "attribute_id": self.size_attribute.id,
                        "option_id": self.large_option.id,
                    }
                ],
                "variants": [
                    {
                        "price": "800.00",
                        "sku": "MEAL-L",
                        "attribute_values": [
                            {
                                "attribute_id": self.size_attribute.id,
                                "option_id": self.large_option.id,
                            }
                        ],
                    }
                ],
            },
            format="json",
        )
        delete_response = self.client.delete(f"{CATALOG_BASE}/products/{product_id}/")
        deleted_detail_response = self.client.get(
            f"{CATALOG_BASE}/products/{product_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(product_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail_response.data["category"]["attributes"][0]["options"][0]["id"],
            self.small_option.id,
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "طبق محدث")
        self.assertFalse(update_response.data["is_available"])
        self.assertEqual(
            update_response.data["attribute_values"][0]["option"]["id"],
            self.large_option.id,
        )
        self.assertEqual(update_response.data["variants"][0]["sku"], "MEAL-L")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_product_rejects_inconsistent_attribute_option(self):
        other_attribute = CategoryAttribute.objects.create(
            category=self.category,
            name="اللون",
        )
        other_option = CategoryOption.objects.create(
            attribute=other_attribute,
            value="أحمر",
        )
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "category_id": self.category.id,
                "name": "منتج غير صالح",
                "description": "",
                "discount": "0.00",
                "attribute_values": [
                    {
                        "attribute_id": self.size_attribute.id,
                        "option_id": other_option.id,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("attribute_values", response.data)

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
