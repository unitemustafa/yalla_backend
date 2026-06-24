from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AdditionClassification

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
