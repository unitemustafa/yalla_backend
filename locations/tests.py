from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Address


User = get_user_model()


class AddressAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="client",
            email="client@example.com",
            phone="+201000000001",
            password="Passw0rd!",
            role=User.Role.CLIENT,
        )
        self.client.force_authenticate(self.user)

    def test_client_can_create_address_with_address_model_fields(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "latitude": "30.0444000",
                "longitude": "31.2357000",
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = Address.objects.get(user=self.user)
        self.assertEqual(address.name, "Home")
        self.assertEqual(address.latitude, Decimal("30.0444000"))
        self.assertEqual(address.longitude, Decimal("31.2357000"))
        self.assertTrue(address.is_default)

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], address.id)
        self.assertEqual(response.data[0]["name"], "Home")
        self.assertTrue(response.data[0]["is_default"])

    def test_creating_default_address_unsets_existing_default(self):
        old_address = Address.objects.create(
            user=self.user,
            name="Old Home",
            latitude=Decimal("30.0000000"),
            longitude=Decimal("31.0000000"),
            is_default=True,
        )

        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Work",
                "latitude": "30.1000000",
                "longitude": "31.1000000",
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        old_address.refresh_from_db()
        self.assertFalse(old_address.is_default)
        self.assertTrue(Address.objects.get(name="Work").is_default)
