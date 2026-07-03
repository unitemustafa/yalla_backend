from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Address, DeliveryArea, ServiceCity


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
        self.service_city = ServiceCity.objects.create(name="Cairo")
        self.delivery_area = DeliveryArea.objects.create(
            service_city=self.service_city,
            name="Maadi",
            delivery_price=Decimal("50.00"),
        )
        self.client.force_authenticate(self.user)

    def test_client_can_create_address_with_address_model_fields(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "service_city_id": self.service_city.id,
                "delivery_area_id": self.delivery_area.id,
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
        self.assertEqual(address.service_city_id, self.service_city.id)
        self.assertEqual(address.delivery_area_id, self.delivery_area.id)
        self.assertEqual(address.delivery_type, Address.DeliveryType.FIXED_AREA)
        self.assertTrue(address.is_default)

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], address.id)
        self.assertEqual(response.data[0]["name"], "Home")
        self.assertEqual(response.data[0]["delivery_area"]["id"], self.delivery_area.id)
        self.assertEqual(response.data[0]["delivery_type"], Address.DeliveryType.FIXED_AREA)
        self.assertEqual(response.data[0]["delivery_price_preview"], "50.00")
        self.assertTrue(response.data[0]["is_default"])

    def test_client_can_create_other_address_without_delivery_area(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Other Area",
                "service_city_id": self.service_city.id,
                "delivery_area_id": None,
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        address = Address.objects.get(user=self.user)
        self.assertEqual(address.service_city_id, self.service_city.id)
        self.assertIsNone(address.delivery_area_id)
        self.assertEqual(address.delivery_type, Address.DeliveryType.DELIVERY)
        self.assertIsNone(response.data[0]["delivery_area"])
        self.assertEqual(response.data[0]["delivery_type"], Address.DeliveryType.DELIVERY)
        self.assertIsNone(response.data[0]["delivery_price_preview"])

    def test_client_cannot_use_delivery_area_from_another_city(self):
        other_city = ServiceCity.objects.create(name="Giza")
        other_area = DeliveryArea.objects.create(
            service_city=other_city,
            name="Dokki",
            delivery_price=Decimal("40.00"),
        )

        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Wrong Area",
                "service_city_id": self.service_city.id,
                "delivery_area_id": other_area.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_area_id", response.data)

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
                "service_city_id": self.service_city.id,
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


class LocationManagementAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="locations_admin",
            email="locations-admin@example.com",
            phone="+201000000011",
            password="Passw0rd!",
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(self.admin)

    def test_admin_can_crud_service_cities(self):
        create_response = self.client.post(
            "/api/v1/locations/service-cities/",
            {
                "name": " Algiers ",
                "center_latitude": "36.7525000",
                "center_longitude": "3.0420000",
                "radius_km": "25.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        city_id = create_response.data["id"]
        self.assertEqual(create_response.data["name"], "Algiers")

        list_response = self.client.get("/api/v1/locations/service-cities/")
        detail_response = self.client.get(
            f"/api/v1/locations/service-cities/{city_id}/"
        )
        update_response = self.client.patch(
            f"/api/v1/locations/service-cities/{city_id}/",
            {"radius_km": "30.00", "is_active": False},
            format="json",
        )
        delete_response = self.client.delete(
            f"/api/v1/locations/service-cities/{city_id}/"
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["radius_km"], "30.00")
        self.assertFalse(update_response.data["is_active"])
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ServiceCity.objects.filter(pk=city_id).exists())

    def test_admin_can_crud_and_filter_delivery_areas(self):
        city = ServiceCity.objects.create(
            name="Oran",
            center_latitude=Decimal("35.6971000"),
            center_longitude=Decimal("-0.6308000"),
            radius_km=Decimal("30.00"),
        )
        create_response = self.client.post(
            "/api/v1/locations/delivery-areas/",
            {
                "service_city_id": city.id,
                "name": "Oran Center",
                "delivery_price": "200.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        area_id = create_response.data["id"]
        filtered_response = self.client.get(
            f"/api/v1/locations/delivery-areas/?service_city_id={city.id}"
        )
        detail_response = self.client.get(
            f"/api/v1/locations/delivery-areas/{area_id}/"
        )
        update_response = self.client.patch(
            f"/api/v1/locations/delivery-areas/{area_id}/",
            {"delivery_price": "250.00"},
            format="json",
        )
        delete_response = self.client.delete(
            f"/api/v1/locations/delivery-areas/{area_id}/"
        )

        self.assertEqual(len(filtered_response.data), 1)
        self.assertEqual(detail_response.data["service_city_id"], city.id)
        self.assertEqual(update_response.data["delivery_price"], "250.00")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DeliveryArea.objects.filter(pk=area_id).exists())

    def test_delivery_area_validates_price_active_city_and_duplicate_active_name(self):
        city = ServiceCity.objects.create(name="Alexandria")
        inactive_city = ServiceCity.objects.create(name="Inactive", is_active=False)

        negative_response = self.client.post(
            "/api/v1/locations/delivery-areas/",
            {
                "service_city_id": city.id,
                "name": "Corniche",
                "delivery_price": "-1.00",
            },
            format="json",
        )
        inactive_response = self.client.post(
            "/api/v1/locations/delivery-areas/",
            {
                "service_city_id": inactive_city.id,
                "name": "Closed",
                "delivery_price": "20.00",
            },
            format="json",
        )
        create_response = self.client.post(
            "/api/v1/locations/delivery-areas/",
            {
                "service_city_id": city.id,
                "name": "Corniche",
                "delivery_price": "30.00",
            },
            format="json",
        )
        duplicate_response = self.client.post(
            "/api/v1/locations/delivery-areas/",
            {
                "service_city_id": city.id,
                "name": "corniche",
                "delivery_price": "35.00",
            },
            format="json",
        )

        self.assertEqual(negative_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_price", negative_response.data)
        self.assertEqual(inactive_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service_city_id", inactive_response.data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", duplicate_response.data)

    def test_client_can_list_only_active_delivery_areas_for_service_city(self):
        city = ServiceCity.objects.create(name="Client City")
        active_area = DeliveryArea.objects.create(
            service_city=city,
            name="Active Area",
            delivery_price=Decimal("30.00"),
        )
        DeliveryArea.objects.create(
            service_city=city,
            name="Inactive Area",
            delivery_price=Decimal("35.00"),
            is_active=False,
        )
        client_user = User.objects.create_user(
            username="area_client",
            email="area-client@example.com",
            phone="+201000000013",
            password="Passw0rd!",
            role=User.Role.CLIENT,
        )
        self.client.force_authenticate(client_user)

        response = self.client.get(
            f"/api/v1/locations/delivery-areas/?service_city_id={city.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [active_area.id])

    def test_client_cannot_manage_service_cities(self):
        client_user = User.objects.create_user(
            username="locations_client",
            email="locations-client@example.com",
            phone="+201000000012",
            password="Passw0rd!",
            role=User.Role.CLIENT,
        )
        self.client.force_authenticate(client_user)

        response = self.client.get("/api/v1/locations/service-cities/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
