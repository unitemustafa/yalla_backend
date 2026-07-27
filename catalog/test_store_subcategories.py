from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from markets.models import Market, MarketClassification, MarketSubcategory
from markets.serializers import (
    AdminMarketSerializer,
    MarketWithStoreProductsSerializer,
)

from .models import Product, StoreSubcategory
from .serializers import AdminProductSerializer


User = get_user_model()
CATALOG_BASE = "/api/v1/catalog"
HOME_BASE = "/api/v1/home"


class StoreSubcategoryAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="subcategory_admin",
            email="subcategory-admin@example.com",
            phone="+213555910001",
            password="Password1!",
            role=User.Role.ADMIN,
            is_active=True,
        )
        self.client_user = User.objects.create_user(
            username="subcategory_client",
            email="subcategory-client@example.com",
            phone="+213555910002",
            password="Password1!",
            role=User.Role.CLIENT,
            is_active=True,
        )
        self.classification = MarketClassification.objects.create(
            name="Restaurants",
        )
        self.drinks = StoreSubcategory.objects.create(
            name_ar="مشروبات",
            name_en="Drinks",
            description_ar="المشروبات المتاحة",
            description_en="Available drinks",
        )
        self.meals = StoreSubcategory.objects.create(
            name_ar="وجبات",
            name_en="Meals",
        )

    def authenticate(self, user=None):
        refresh = RefreshToken.for_user(user or self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def create_market(self):
        market = Market.objects.create(
            classification=self.classification,
            name="Test Store",
            scope=Market.Scope.GENERAL,
        )
        MarketSubcategory.objects.create(
            market=market,
            subcategory=self.drinks,
            sort_order=0,
        )
        MarketSubcategory.objects.create(
            market=market,
            subcategory=self.meals,
            sort_order=1,
        )
        return market

    def test_admin_can_create_list_and_update_subcategories(self):
        self.authenticate()
        create_response = self.client.post(
            f"{CATALOG_BASE}/store-subcategories/",
            {
                "name_ar": "حلويات",
                "name_en": "Desserts",
                "description_ar": "",
                "description_en": "",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["market_count"], 0)
        self.assertEqual(create_response.data["product_count"], 0)

        list_response = self.client.get(
            f"{CATALOG_BASE}/store-subcategories/"
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 4)

        update_response = self.client.patch(
            (
                f"{CATALOG_BASE}/store-subcategories/"
                f"{create_response.data['id']}/"
            ),
            {"description_en": "Sweet picks", "is_active": False},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["description_en"], "Sweet picks")
        self.assertFalse(update_response.data["is_active"])

    def test_subcategory_management_requires_admin(self):
        self.authenticate(self.client_user)
        response = self.client.get(
            f"{CATALOG_BASE}/store-subcategories/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_market_requires_ordered_active_subcategories(self):
        serializer = AdminMarketSerializer(
            data={
                "classification_id": self.classification.id,
                "name": "Ordered Store",
                "scope": Market.Scope.GENERAL,
                "subcategory_ids": [self.meals.id, self.drinks.id],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        market = serializer.save()
        assignments = list(
            market.subcategory_assignments.order_by("sort_order").values_list(
                "subcategory_id",
                flat=True,
            )
        )
        self.assertEqual(assignments, [self.meals.id, self.drinks.id])

        missing = AdminMarketSerializer(
            data={
                "classification_id": self.classification.id,
                "name": "Missing Categories",
                "scope": Market.Scope.GENERAL,
            }
        )
        self.assertFalse(missing.is_valid())
        self.assertIn("subcategory_ids", missing.errors)

        remove_all = AdminMarketSerializer(
            market,
            data={"subcategory_ids": []},
            partial=True,
        )
        self.assertFalse(remove_all.is_valid())
        self.assertIn("subcategory_ids", remove_all.errors)

    def test_product_requires_active_subcategory_assigned_to_market(self):
        market = self.create_market()
        unassigned = StoreSubcategory.objects.create(
            name_ar="مخبوزات",
            name_en="Bakery",
        )
        invalid = AdminProductSerializer(
            data={
                "market_id": market.id,
                "subcategory_id": unassigned.id,
                "name": "Bread",
                "is_available": False,
            }
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn("subcategory_id", invalid.errors)

        valid = AdminProductSerializer(
            data={
                "market_id": market.id,
                "subcategory_id": self.meals.id,
                "name": "Meal",
                "is_available": False,
            }
        )
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.save().subcategory_id, self.meals.id)

    def test_used_subcategory_cannot_be_unassigned_and_is_archived_on_delete(self):
        market = self.create_market()
        product = Product.objects.create(
            market=market,
            subcategory=self.drinks,
            name="Juice",
            is_available=False,
        )

        serializer = AdminMarketSerializer(
            market,
            data={"subcategory_ids": [self.meals.id]},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("subcategory_ids", serializer.errors)

        self.authenticate()
        list_response = self.client.get(
            f"{CATALOG_BASE}/store-subcategories/"
        )
        drinks_payload = next(
            item
            for item in list_response.data
            if item["id"] == self.drinks.id
        )
        self.assertEqual(drinks_payload["market_count"], 1)
        self.assertEqual(drinks_payload["product_count"], 1)
        response = self.client.delete(
            f"{CATALOG_BASE}/store-subcategories/{self.drinks.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["action"], "archived")
        self.assertEqual(response.data["product_count"], 1)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.drinks.refresh_from_db()
        self.assertFalse(self.drinks.is_active)

    def test_inactive_subcategory_stays_on_existing_product_but_rejects_new_use(self):
        market = self.create_market()
        product = Product.objects.create(
            market=market,
            subcategory=self.drinks,
            name="Juice",
            is_available=False,
        )
        self.drinks.is_active = False
        self.drinks.save(update_fields=("is_active",))

        unchanged = AdminProductSerializer(
            product,
            data={
                "subcategory_id": self.drinks.id,
                "description": "Updated",
            },
            partial=True,
        )
        self.assertTrue(unchanged.is_valid(), unchanged.errors)

        new_product = AdminProductSerializer(
            data={
                "market_id": market.id,
                "subcategory_id": self.drinks.id,
                "name": "Another Juice",
                "is_available": False,
            }
        )
        self.assertFalse(new_product.is_valid())
        self.assertIn("subcategory_id", new_product.errors)

    def test_store_payload_hides_inactive_chip_but_keeps_its_product_in_all(self):
        market = self.create_market()
        product = Product.objects.create(
            market=market,
            subcategory=self.drinks,
            name="Legacy Juice",
            is_available=True,
        )
        self.drinks.is_active = False
        self.drinks.save(update_fields=("is_active",))

        payload = MarketWithStoreProductsSerializer(
            market,
            context={"products_by_market": {market.id: [product]}},
        ).data

        self.assertEqual(
            [item["id"] for item in payload["subcategories"]],
            [self.meals.id],
        )
        self.assertEqual(len(payload["products"]), 1)
        self.assertEqual(
            payload["products"][0]["subcategory"]["id"],
            self.drinks.id,
        )
