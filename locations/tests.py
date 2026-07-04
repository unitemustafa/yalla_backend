from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from markets.models import Market, MarketClassification
from orders.models import Order

from .models import Address, DeliveryArea, ServiceCity
from .serializers import AddressSerializer


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

    def create_market(self):
        classification = MarketClassification.objects.create(name="Food")
        market = Market.objects.create(
            classification=classification,
            name="Address Market",
        )
        market.service_cities.add(self.service_city)
        market.delivery_areas.add(self.delivery_area)
        return market

    def create_order_for_address(self, address):
        return Order.objects.create(
            user=address.user,
            delivery_address=address,
            market=self.create_market(),
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Order.DeliveryType.FIXED_AREA,
            payment_method="cash_on_delivery",
            delivery_price=self.delivery_area.delivery_price,
            subtotal_price=Decimal("100.00"),
            total_price=Decimal("150.00"),
        )

    def test_client_can_create_address_with_address_model_fields(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Home street",
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
        self.assertEqual(response.data[0]["fullName"], "Home")
        self.assertEqual(response.data[0]["details"], "Home street")
        self.assertEqual(response.data[0]["line1"], "Home street")
        self.assertEqual(response.data[0]["street"], "Home street")
        self.assertEqual(response.data[0]["delivery_area"]["id"], self.delivery_area.id)
        self.assertEqual(response.data[0]["delivery_type"], Address.DeliveryType.FIXED_AREA)
        self.assertEqual(response.data[0]["delivery_price_preview"], "50.00")
        self.assertTrue(response.data[0]["is_default"])

    def test_client_can_create_other_address_without_delivery_area(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Other Area",
                "line1": "Other area street",
                "service_city_id": self.service_city.id,
                "delivery_area_id": None,
                "manual_area": "New district",
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        address = Address.objects.get(user=self.user)
        self.assertEqual(address.service_city_id, self.service_city.id)
        self.assertIsNone(address.delivery_area_id)
        self.assertEqual(address.manual_area, "New district")
        self.assertEqual(address.delivery_type, Address.DeliveryType.DELIVERY)
        self.assertIsNone(response.data[0]["delivery_area"])
        self.assertEqual(response.data[0]["manual_area"], "New district")
        self.assertEqual(response.data[0]["delivery_type"], Address.DeliveryType.DELIVERY)
        self.assertIsNone(response.data[0]["delivery_price_preview"])

    def test_general_user_can_create_manual_address_without_service_city(self):
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

        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Army street near hospital",
                "manual_city": "Mansoura",
                "manual_area": "University district",
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        address = Address.objects.get(user=self.user)
        self.assertIsNone(address.service_city_id)
        self.assertIsNone(address.delivery_area_id)
        self.assertIsNone(address.latitude)
        self.assertIsNone(address.longitude)
        self.assertEqual(address.manual_city, "Mansoura")
        self.assertEqual(address.manual_area, "University district")
        self.assertEqual(address.delivery_type, Address.DeliveryType.DELIVERY)
        self.assertIsNone(response.data[0]["service_city_id"])
        self.assertIsNone(response.data[0]["service_city_name"])
        self.assertIsNone(response.data[0]["delivery_area_id"])
        self.assertIsNone(response.data[0]["delivery_area_name"])
        self.assertIsNone(response.data[0]["delivery_area_price"])
        self.assertEqual(response.data[0]["manual_city"], "Mansoura")
        self.assertEqual(response.data[0]["manual_area"], "University district")

    def test_general_manual_address_requires_manual_city_and_area(self):
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

        missing_city = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Street",
                "manual_area": "Area",
            },
            format="json",
        )
        missing_area = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Street",
                "manual_city": "City",
            },
            format="json",
        )

        self.assertEqual(missing_city.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manual_city", missing_city.data)
        self.assertEqual(missing_area.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manual_area", missing_area.data)

    def test_general_address_rejects_delivery_area(self):
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

        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Street",
                "manual_city": "City",
                "manual_area": "Area",
                "delivery_area_id": self.delivery_area.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_area_id", response.data)

    def test_service_city_user_cannot_create_general_workaround_address(self):
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

        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Street",
                "manual_city": "City",
                "manual_area": "Area",
                "service_city_id": None,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service_city_id", response.data)

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
                "line1": "Wrong area street",
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
                "line1": "Work street",
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

    def test_name_and_line1_are_saved_separately(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "line1": "Army street near hospital",
                "service_city_id": self.service_city.id,
                "delivery_area_id": self.delivery_area.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        address = Address.objects.get(user=self.user)
        self.assertEqual(address.name, "Home")
        self.assertEqual(address.details, "Army street near hospital")
        self.assertEqual(response.data[0]["name"], "Home")
        self.assertEqual(response.data[0]["fullName"], "Home")
        self.assertEqual(response.data[0]["details"], "Army street near hospital")
        self.assertEqual(response.data[0]["line1"], "Army street near hospital")
        self.assertEqual(response.data[0]["street"], "Army street near hospital")

    def test_details_field_is_used_as_address_details(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "Home",
                "details": "Direct details street",
                "line1": "Ignored alias street",
                "service_city_id": self.service_city.id,
                "delivery_area_id": self.delivery_area.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        address = Address.objects.get(user=self.user)
        self.assertEqual(address.name, "Home")
        self.assertEqual(address.details, "Direct details street")
        self.assertEqual(response.data[0]["line1"], "Direct details street")
        self.assertEqual(response.data[0]["street"], "Direct details street")

    def test_legacy_line1_only_payload_is_still_accepted(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "line1": "Legacy client street",
                "service_city_id": self.service_city.id,
                "delivery_area_id": self.delivery_area.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        address = Address.objects.get(user=self.user)
        self.assertEqual(address.name, "Legacy client street")
        self.assertEqual(address.details, "Legacy client street")
        self.assertEqual(response.data[0]["line1"], "Legacy client street")

    def test_legacy_address_with_empty_details_serializes_line1_from_name(self):
        address = Address.objects.create(
            user=self.user,
            name="Tahrir street",
            details="",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )

        data = AddressSerializer(address).data

        self.assertEqual(data["name"], "Tahrir street")
        self.assertEqual(data["line1"], "Tahrir street")
        self.assertEqual(data["street"], "Tahrir street")

    def test_updating_line1_does_not_change_name(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Old street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )

        response = self.client.patch(
            f"/api/v1/addresses/{address.id}/",
            {"line1": "New street"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        address.refresh_from_db()
        self.assertEqual(address.name, "Home")
        self.assertEqual(address.details, "New street")
        self.assertEqual(response.data[0]["name"], "Home")
        self.assertEqual(response.data[0]["line1"], "New street")

    def test_updating_name_does_not_clear_details(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Saved street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )

        response = self.client.patch(
            f"/api/v1/addresses/{address.id}/",
            {"name": "Work"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        address.refresh_from_db()
        self.assertEqual(address.name, "Work")
        self.assertEqual(address.details, "Saved street")
        self.assertEqual(response.data[0]["name"], "Work")
        self.assertEqual(response.data[0]["line1"], "Saved street")

    def test_deleting_unused_address_hides_it_from_list(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Home street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )

        response = self.client.delete(f"/api/v1/addresses/{address.id}/")
        list_response = self.client.get("/api/v1/addresses/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertFalse(address.is_active)
        self.assertFalse(address.is_default)
        self.assertEqual(response.data, [])
        self.assertEqual(list_response.data, [])

    def test_deleting_order_address_soft_deletes_without_protected_error(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Home street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )
        order = self.create_order_for_address(address)

        response = self.client.delete(f"/api/v1/addresses/{address.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        address.refresh_from_db()
        order.refresh_from_db()
        self.assertFalse(address.is_active)
        self.assertEqual(order.delivery_address_id, address.id)
        self.assertTrue(Address.objects.filter(pk=address.id).exists())
        self.assertEqual(response.data, [])

    def test_deleted_address_is_hidden_from_default_endpoint(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Home street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )
        address.is_active = False
        address.is_default = False
        address.save(update_fields=["is_active", "is_default"])

        response = self.client.get("/api/v1/addresses/default/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

    def test_deleting_default_sets_newest_active_address_as_default(self):
        old_default = Address.objects.create(
            user=self.user,
            name="Old",
            details="Old street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )
        next_default = Address.objects.create(
            user=self.user,
            name="Newest",
            details="Newest street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )

        response = self.client.delete(f"/api/v1/addresses/{old_default.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        old_default.refresh_from_db()
        next_default.refresh_from_db()
        self.assertFalse(old_default.is_active)
        self.assertFalse(old_default.is_default)
        self.assertTrue(next_default.is_default)
        self.assertEqual([item["id"] for item in response.data], [next_default.id])

    def test_deleting_last_default_leaves_user_without_default(self):
        address = Address.objects.create(
            user=self.user,
            name="Only",
            details="Only street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_default=True,
        )

        response = self.client.delete(f"/api/v1/addresses/{address.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Address.objects.filter(user=self.user, is_default=True).exists())

    def test_cannot_patch_deleted_address(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Home street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_active=False,
        )

        response = self.client.patch(
            f"/api/v1/addresses/{address.id}/",
            {"name": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        address.refresh_from_db()
        self.assertEqual(address.name, "Home")

    def test_cannot_set_deleted_address_as_default(self):
        address = Address.objects.create(
            user=self.user,
            name="Home",
            details="Home street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            is_active=False,
        )

        response = self.client.patch(f"/api/v1/addresses/{address.id}/default/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        address.refresh_from_db()
        self.assertFalse(address.is_default)

    def test_cannot_delete_another_users_address(self):
        other_user = User.objects.create_user(
            username="other-client",
            email="other-client@example.com",
            phone="+201000000099",
            password="Passw0rd!",
            role=User.Role.CLIENT,
        )
        address = Address.objects.create(
            user=other_user,
            name="Other",
            details="Other street",
            service_city=self.service_city,
            delivery_area=self.delivery_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )

        response = self.client.delete(f"/api/v1/addresses/{address.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        address.refresh_from_db()
        self.assertTrue(address.is_active)


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
