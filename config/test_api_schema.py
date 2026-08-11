from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


class ProtectedApiSchemaTests(APITestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="schema_client",
            email="schema-client@example.com",
            phone="+201000000070",
            password="StrongPassword123!",
            role=User.Role.CLIENT,
        )
        self.admin = User.objects.create_user(
            username="schema_admin",
            email="schema-admin@example.com",
            phone="+201000000071",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )

    def test_schema_is_not_public(self):
        response = self.client.get(reverse("api-schema"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_cannot_read_schema(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.get(reverse("api-schema"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_generate_schema(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("api-schema"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("openapi", response.data)
