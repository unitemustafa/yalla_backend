from decimal import Decimal
from importlib import import_module
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from PIL import Image
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
    ProductImage,
    ProductAddition,
    ProductCategory,
    ProductAttributeValue,
    ProductVariant,
    VariantAttributeValue,
)

User = get_user_model()
CATALOG_BASE = "/api/v1/catalog"


def product_image_upload(name="product.png", image_format="PNG", color="red"):
    content = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(content, format=image_format)
    mime_type = "image/jpeg" if image_format == "JPEG" else f"image/{image_format.lower()}"
    return SimpleUploadedFile(name, content.getvalue(), content_type=mime_type)


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

    def test_admin_can_list_addition_classifications(self):
        sauce = AdditionClassification.objects.create(name="صلصات")
        extras = AdditionClassification.objects.create(name="إضافات")
        self.authenticate(self.admin)

        response = self.client.get(f"{CATALOG_BASE}/addition-classifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [extras.id, sauce.id],
        )

    def test_client_can_toggle_product_like(self):
        self.authenticate(self.client_user)

        like_response = self.client.post(
            f"{CATALOG_BASE}/products/{self.product.id}/like/"
        )
        self.product.refresh_from_db()
        self.assertTrue(self.product.liked_by.filter(id=self.client_user.id).exists())

        unlike_response = self.client.post(
            f"{CATALOG_BASE}/products/{self.product.id}/like/"
        )
        self.product.refresh_from_db()

        self.assertEqual(like_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            like_response.data,
            {
                "product_id": self.product.id,
                "liked": True,
            },
        )
        self.assertFalse(self.product.liked_by.filter(id=self.client_user.id).exists())
        self.assertEqual(unlike_response.status_code, status.HTTP_200_OK)
        self.assertEqual(unlike_response.data["liked"], False)

    def test_client_can_list_liked_products(self):
        self.product.liked_by.add(self.client_user)
        ProductVariant.objects.create(
            product=self.product,
            price=Decimal("450.00"),
            sku="COUSCOUS-S",
        )
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/products/likes/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([product["id"] for product in response.data], [self.product.id])
        product = response.data[0]
        self.assertIn("market", product)
        self.assertNotIn("category", product)
        self.assertEqual(product["theme"], Product.Theme.OTHER)
        self.assertFalse(product["is_popular"])
        self.assertIn("variants", product)
        self.assertNotIn("attribute_values", product)
        self.assertNotIn("additions", product)
        self.assertNotIn("created_at", product)
        self.assertNotIn("updated_at", product)
        self.assertNotIn("attribute_values", product["variants"][0])
        self.assertNotIn("sku", product["variants"][0])

    def test_product_like_requires_client_role(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/products/{self.product.id}/like/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_can_unlike_product(self):
        self.product.liked_by.add(self.client_user)
        self.authenticate(self.client_user)

        response = self.client.delete(
            f"{CATALOG_BASE}/products/{self.product.id}/unlike/"
        )
        second_response = self.client.delete(
            f"{CATALOG_BASE}/products/{self.product.id}/unlike/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "product_id": self.product.id,
                "liked": False,
            },
        )
        self.assertFalse(self.product.liked_by.filter(id=self.client_user.id).exists())
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data["liked"], False)

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

    def test_admin_can_read_update_and_delete_addition_classification(self):
        classification = AdditionClassification.objects.create(name="إضافات")
        self.authenticate(self.admin)

        detail_response = self.client.get(
            f"{CATALOG_BASE}/addition-classifications/{classification.id}/"
        )
        update_response = self.client.patch(
            f"{CATALOG_BASE}/addition-classifications/{classification.id}/",
            {"name": " إضافات محدثة "},
            format="json",
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/addition-classifications/{classification.id}/"
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "إضافات محدثة")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            AdditionClassification.objects.filter(pk=classification.id).exists()
        )

    def test_addition_classification_delete_rejects_used_classification(self):
        classification = AdditionClassification.objects.create(name="إضافات")
        ProductAddition.objects.create(
            classification=classification,
            name_ar="جبن",
            name_en="Cheese",
            price="100.00",
        )
        self.authenticate(self.admin)

        response = self.client.delete(
            f"{CATALOG_BASE}/addition-classifications/{classification.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(
            AdditionClassification.objects.filter(pk=classification.id).exists()
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
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
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
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
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

    def test_category_attribute_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/category-attributes/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_category_attribute(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{CATALOG_BASE}/category-attributes/",
            {
                "category_id": self.category.id,
                "name": " اللون ",
            },
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "اللون")
        self.assertEqual(create_response.data["category"]["id"], self.category.id)
        attribute_id = create_response.data["id"]

        list_response = self.client.get(f"{CATALOG_BASE}/category-attributes/")
        detail_response = self.client.get(
            f"{CATALOG_BASE}/category-attributes/{attribute_id}/"
        )
        update_response = self.client.patch(
            f"{CATALOG_BASE}/category-attributes/{attribute_id}/",
            {"name": "النوع"},
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/category-attributes/{attribute_id}/"
        )
        deleted_detail_response = self.client.get(
            f"{CATALOG_BASE}/category-attributes/{attribute_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(attribute_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "اللون")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "النوع")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_category_attribute_duplicate_name_per_category_is_rejected(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/category-attributes/",
            {
                "category_id": self.category.id,
                "name": self.size_attribute.name,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["name"],
            ["This attribute already exists for this category."],
        )

    def test_category_attribute_delete_rejects_used_attribute(self):
        ProductAttributeValue.objects.create(
            product=self.product,
            attribute=self.size_attribute,
            option=self.small_option,
        )
        self.authenticate(self.admin)

        response = self.client.delete(
            f"{CATALOG_BASE}/category-attributes/{self.size_attribute.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_category_option_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/category-options/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_read_update_and_delete_category_option(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{CATALOG_BASE}/category-options/",
            {
                "attribute_id": self.size_attribute.id,
                "value": " متوسط ",
            },
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["value"], "متوسط")
        self.assertEqual(
            create_response.data["attribute"]["id"],
            self.size_attribute.id,
        )
        option_id = create_response.data["id"]

        list_response = self.client.get(f"{CATALOG_BASE}/category-options/")
        detail_response = self.client.get(
            f"{CATALOG_BASE}/category-options/{option_id}/"
        )
        update_response = self.client.patch(
            f"{CATALOG_BASE}/category-options/{option_id}/",
            {"value": "صغير جدا"},
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/category-options/{option_id}/"
        )
        deleted_detail_response = self.client.get(
            f"{CATALOG_BASE}/category-options/{option_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(option_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["value"], "متوسط")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["value"], "صغير جدا")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_category_option_duplicate_value_per_attribute_is_rejected(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/category-options/",
            {
                "attribute_id": self.size_attribute.id,
                "value": self.small_option.value,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["value"],
            ["This option already exists for this attribute."],
        )

    def test_category_option_delete_rejects_used_option(self):
        ProductAttributeValue.objects.create(
            product=self.product,
            attribute=self.size_attribute,
            option=self.small_option,
        )
        self.authenticate(self.admin)

        response = self.client.delete(
            f"{CATALOG_BASE}/category-options/{self.small_option.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_product_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{CATALOG_BASE}/products/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_available_product_without_variants_is_rejected(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "name": "Available without price",
                "is_available": True,
                "variants": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["variants"][0],
            "يجب إضافة سعر أو متغير صالح قبل إتاحة المنتج للبيع.",
        )

    def test_available_product_with_base_variant_is_created(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "name": "Available base product",
                "is_available": True,
                "variants": [{"price": "125.50", "sku": "BASE"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["variants"]), 1)
        self.assertEqual(response.data["variants"][0]["price"], "125.50")

    def test_unavailable_draft_without_variants_is_created(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "name": "Draft without price",
                "is_available": False,
                "variants": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["variants"], [])

    def test_patch_description_preserves_existing_variants(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            price="90.00",
            sku="PRESERVE",
        )
        self.authenticate(self.admin)

        response = self.client.patch(
            f"{CATALOG_BASE}/products/{self.product.id}/",
            {"description": "Updated description only"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], "Updated description only")
        self.assertEqual(response.data["variants"][0]["id"], variant.id)
        self.assertEqual(self.product.variants.count(), 1)

    def test_admin_can_create_read_update_and_delete_product(self):
        addition_classification = AdditionClassification.objects.create(
            name="إضافات الوجبات"
        )
        addition = ProductAddition.objects.create(
            classification=addition_classification,
            name_ar="جبن",
            name_en="Cheese",
            price="120.00",
        )
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
                "additions": [addition.id],
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
        self.assertEqual(create_response.data["additions"], [addition.id])
        product_id = create_response.data["id"]

        self.assertTrue(
            ProductAttributeValue.objects.filter(
                product_id=product_id,
                attribute=self.size_attribute,
                option=self.small_option,
            ).exists()
        )
        variant = ProductVariant.objects.get(product_id=product_id)
        self.assertTrue(addition.products.filter(id=product_id).exists())
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
                "additions": [],
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
        self.assertEqual(update_response.data["additions"], [])
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    @override_settings(MEDIA_ROOT="/tmp/yalla_catalog_legacy_image_test")
    def test_admin_can_create_product_with_image(self):
        self.authenticate(self.admin)
        image = product_image_upload("meal.png")

        response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "category_id": self.category.id,
                "name": "طبق بصورة",
                "description": "طبق تجريبي",
                "discount": "0.00",
                "is_available": False,
                "image": image,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product = Product.objects.get(id=response.data["id"])
        self.assertTrue(product.image.name.startswith("products/"))
        self.assertTrue(response.data["image"])
        self.assertEqual(len(response.data["images"]), 1)

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


@override_settings(MEDIA_ROOT="/tmp/yalla_product_image_tests")
class ProductImageAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="product_image_admin",
            email="product-images@example.com",
            phone="+213555499001",
            password="Password1!",
            role=User.Role.ADMIN,
            is_active=True,
        )
        classification = MarketClassification.objects.create(name="Images")
        self.market = Market.objects.create(
            classification=classification,
            name="Image market",
        )
        refresh = RefreshToken.for_user(self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def create_product(self, name="Image product"):
        return Product.objects.create(market=self.market, name=name)

    def create_product_response(self, images=None, image=None, **extra):
        payload = {
            "market_id": self.market.id,
            "name": extra.pop("name", "Image product"),
            "description": "",
            "discount": "0.00",
            **extra,
        }
        if images is not None:
            payload["images"] = images
        if image is not None:
            payload["image"] = image
        return self.client.post(
            f"{CATALOG_BASE}/products/",
            payload,
            format="multipart",
        )

    def test_create_product_with_three_images_and_primary_index(self):
        response = self.create_product_response(
            images=[
                product_image_upload("one.png", color="red"),
                product_image_upload("two.png", color="green"),
                product_image_upload("three.webp", "WEBP", "blue"),
            ],
            primary_image_index=1,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["images"]), 3)
        self.assertEqual(
            [image["sort_order"] for image in response.data["images"]],
            [0, 1, 2],
        )
        self.assertTrue(response.data["images"][1]["is_primary"])
        product = Product.objects.get(pk=response.data["id"])
        primary = product.images.get(is_primary=True)
        self.assertEqual(product.image.name, primary.image.name)

    def test_first_image_is_primary_and_legacy_image_stays_compatible(self):
        response = self.create_product_response(
            image=product_image_upload("legacy.jpg", "JPEG")
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["image"])
        self.assertEqual(len(response.data["images"]), 1)
        self.assertTrue(response.data["images"][0]["is_primary"])
        product = Product.objects.get(pk=response.data["id"])
        self.assertEqual(product.image.name, product.images.get().image.name)

    def test_add_images_and_set_another_primary(self):
        product = self.create_product()
        first = ProductImage.objects.create(
            product=product,
            image=product_image_upload("first.png", color="red"),
            is_primary=True,
        )
        product.image = first.image.name
        product.save(update_fields=("image", "updated_at"))

        upload_response = self.client.post(
            f"{CATALOG_BASE}/products/{product.id}/images/",
            {
                "images": [
                    product_image_upload("second.png", color="green"),
                    product_image_upload("third.png", color="blue"),
                ]
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(upload_response.data["images"]), 3)
        target = upload_response.data["images"][2]

        primary_response = self.client.patch(
            f"{CATALOG_BASE}/products/{product.id}/images/{target['id']}/",
            {"is_primary": True},
            format="json",
        )

        self.assertEqual(primary_response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        selected = ProductImage.objects.get(pk=target["id"])
        self.assertTrue(selected.is_primary)
        self.assertEqual(product.image.name, selected.image.name)
        self.assertEqual(ProductImage.objects.filter(product=product, is_primary=True).count(), 1)

    def test_delete_non_primary_then_primary_promotes_first_remaining(self):
        response = self.create_product_response(
            images=[
                product_image_upload("one.png", color="red"),
                product_image_upload("two.png", color="green"),
                product_image_upload("three.png", color="blue"),
            ]
        )
        product_id = response.data["id"]
        first_id, second_id, third_id = [item["id"] for item in response.data["images"]]

        non_primary_delete = self.client.delete(
            f"{CATALOG_BASE}/products/{product_id}/images/{third_id}/"
        )
        primary_delete = self.client.delete(
            f"{CATALOG_BASE}/products/{product_id}/images/{first_id}/"
        )

        self.assertEqual(non_primary_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(primary_delete.status_code, status.HTTP_204_NO_CONTENT)
        product = Product.objects.get(pk=product_id)
        remaining = product.images.get()
        self.assertEqual(remaining.id, second_id)
        self.assertTrue(remaining.is_primary)
        self.assertEqual(product.image.name, remaining.image.name)

    def test_reorder_images_requires_complete_unique_owned_ids(self):
        response = self.create_product_response(
            images=[
                product_image_upload("one.png", color="red"),
                product_image_upload("two.png", color="green"),
                product_image_upload("three.png", color="blue"),
            ]
        )
        product_id = response.data["id"]
        ids = [item["id"] for item in response.data["images"]]

        reorder = self.client.post(
            f"{CATALOG_BASE}/products/{product_id}/images/reorder/",
            {"image_ids": list(reversed(ids))},
            format="json",
        )
        duplicate = self.client.post(
            f"{CATALOG_BASE}/products/{product_id}/images/reorder/",
            {"image_ids": [ids[0], ids[0], ids[2]]},
            format="json",
        )

        self.assertEqual(reorder.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in reorder.data["images"]],
            list(reversed(ids)),
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            ProductImage.objects.get(pk=ids[0]).is_primary,
            True,
        )

    def test_rejects_more_than_ten_invalid_type_and_oversized_image(self):
        too_many = self.create_product_response(
            images=[
                product_image_upload(f"image-{index}.png", color=(index, 0, 0))
                for index in range(11)
            ]
        )
        gif = BytesIO()
        Image.new("RGB", (2, 2), color="red").save(gif, format="GIF")
        invalid_type = self.create_product_response(
            name="GIF product",
            images=[
                SimpleUploadedFile(
                    "invalid.gif",
                    gif.getvalue(),
                    content_type="image/gif",
                )
            ],
        )
        oversized = product_image_upload("large.png")
        oversized = SimpleUploadedFile(
            oversized.name,
            oversized.read() + b"0" * (5 * 1024 * 1024),
            content_type="image/png",
        )
        oversized_response = self.create_product_response(
            name="Large product",
            images=[oversized],
        )

        self.assertEqual(too_many.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_type.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(oversized_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_operate_on_an_image_from_another_product(self):
        first_product = self.create_product("First")
        second_product = self.create_product("Second")
        image = ProductImage.objects.create(
            product=second_product,
            image=product_image_upload("owned.png"),
            is_primary=True,
        )

        patch_response = self.client.patch(
            f"{CATALOG_BASE}/products/{first_product.id}/images/{image.id}/",
            {"is_primary": True},
            format="json",
        )
        delete_response = self.client.delete(
            f"{CATALOG_BASE}/products/{first_product.id}/images/{image.id}/"
        )

        self.assertEqual(patch_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(ProductImage.objects.filter(pk=image.id).exists())

    def test_legacy_data_migration_reuses_the_stored_file_name(self):
        product = Product.objects.create(
            market=self.market,
            name="Legacy migration",
            image=product_image_upload("migration.png"),
        )
        stored_name = product.image.name
        migration = import_module("catalog.migrations.0004_productimage")

        migration.copy_legacy_product_images(import_module("django.apps").apps, None)
        migration.copy_legacy_product_images(import_module("django.apps").apps, None)

        product_image = ProductImage.objects.get(product=product)
        self.assertEqual(product_image.image.name, stored_name)
        self.assertTrue(product_image.is_primary)
        self.assertEqual(ProductImage.objects.filter(product=product).count(), 1)

    def test_storage_cleanup_preserves_a_shared_reference(self):
        first_product = self.create_product("Shared one")
        second_product = self.create_product("Shared two")
        first = ProductImage.objects.create(
            product=first_product,
            image=product_image_upload("shared.png"),
            is_primary=True,
        )
        second = ProductImage.objects.create(
            product=second_product,
            image=first.image.name,
            is_primary=True,
        )
        storage = first.image.storage
        stored_name = first.image.name

        with self.captureOnCommitCallbacks(execute=True):
            first.delete()

        self.assertTrue(ProductImage.objects.filter(pk=second.id).exists())
        self.assertTrue(storage.exists(stored_name))

    def test_product_list_image_prefetch_does_not_grow_queries(self):
        product = self.create_product("Query one")
        ProductImage.objects.create(
            product=product,
            image=product_image_upload("query-one.png", color="red"),
            is_primary=True,
        )
        with CaptureQueriesContext(connection) as one_product_queries:
            response = self.client.get(f"{CATALOG_BASE}/products/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        for index, color in enumerate(("green", "blue", "yellow"), start=2):
            product = self.create_product(f"Query {index}")
            ProductImage.objects.create(
                product=product,
                image=product_image_upload(f"query-{index}.png", color=color),
                is_primary=True,
            )
        with CaptureQueriesContext(connection) as many_product_queries:
            response = self.client.get(f"{CATALOG_BASE}/products/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(one_product_queries), len(many_product_queries))
