from decimal import Decimal

from rest_framework.test import APITestCase

from accounts.models import User
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from orders.models import Order
from orders.serializers import CourierOrderListSerializer


class AddressRegionConsistencyTests(APITestCase):
    def setUp(self):
        self.city = ServiceCity.objects.create(
            name="Address review city",
            center_latitude=10,
            center_longitude=10,
            radius_km=50,
            boundary_bbox={"west": 9.9, "south": 9.9, "east": 10.1, "north": 10.1},
        )
        self.other_city = ServiceCity.objects.create(name="Other review city")
        self.customer = User.objects.create_user(
            username="address-review-client",
            role=User.Role.CLIENT,
            email="address-review-client@example.test",
            phone="01000000001",
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city=self.city,
        )
        self.admin = User.objects.create_user(
            username="address-review-admin",
            role=User.Role.ADMIN,
            email="address-review-admin@example.test",
            phone="01000000002",
        )
        self.area = DeliveryArea.objects.create(
            name="Old area",
            service_city=self.city,
            delivery_price=25,
        )
        self.address = Address.objects.create(
            user=self.customer,
            name="Home",
            details="Old destination",
            street="Old street",
            service_city=self.city,
            delivery_area=self.area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
            latitude=10,
            longitude=10,
        )
        classification = MarketClassification.objects.create(name="Address review")
        self.market = Market.objects.create(
            name="Address review market",
            classification=classification,
        )
        self.market.service_cities.add(self.city)
        self.client.force_authenticate(self.customer)

    def create_order(self):
        return Order.objects.create(
            user=self.customer,
            market=self.market,
            delivery_address=self.address,
            service_city=self.city,
            order_scope=Order.Scope.SERVICE_CITY,
            delivery_area=self.area,
            delivery_type=Order.DeliveryType.FIXED_AREA,
            payment_method="cash",
            delivery_price=25,
            total_price=25,
        )

    def test_replacing_order_address_updates_dashboard_and_courier_snapshot(self):
        order = self.create_order()
        new_area = DeliveryArea.objects.create(
            name="New area",
            service_city=self.city,
            delivery_price=40,
        )
        address = Address.objects.create(
            user=self.customer,
            name="Office",
            details="New destination",
            street="New street",
            building_name="Building 7",
            company_name="Office",
            floor="4",
            apartment_number="12",
            recipient_phone="01111111111",
            additional_instructions="Call at gate",
            latitude=Decimal("10.01"),
            longitude=Decimal("10.01"),
            service_city=self.city,
            delivery_area=new_area,
            delivery_type=Address.DeliveryType.FIXED_AREA,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/orders/{order.id}/",
            {"delivery_address_id": address.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        destination = response.data["delivery_address"]
        self.assertEqual(destination["id"], address.id)
        self.assertEqual(destination["street"], "New street")
        self.assertEqual(destination["company_name"], "Office")
        self.assertEqual(destination["recipient_phone"], "01111111111")
        self.assertEqual(destination["latitude"], 10.01)
        self.assertEqual(destination["delivery_area"]["id"], new_area.id)
        self.assertEqual(order.delivery_address_snapshot, destination)
        self.assertEqual(
            CourierOrderListSerializer(order).data["delivery_address"], destination
        )

    def test_other_order_edits_and_reselecting_same_address_keep_frozen_snapshot(self):
        order = self.create_order()
        original = order.delivery_address_snapshot
        self.address.street = "Changed address book street"
        self.address.save(update_fields=["street"])
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/orders/{order.id}/",
            {"description": "Order note", "delivery_address_id": self.address.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["delivery_address"], original)

    def test_clearing_order_address_clears_its_snapshot(self):
        order = self.create_order()
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/orders/{order.id}/",
            {"delivery_address_id": None},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.delivery_address_snapshot, {})
        self.assertIsNone(response.data["delivery_address"])

    def test_saved_service_city_address_can_be_edited_after_browsing_switch(self):
        for city in (self.other_city, None):
            with self.subTest(city=city):
                self.customer.market_region_service_city = city
                self.customer.market_region_mode = (
                    User.MarketRegionMode.SERVICE_CITY
                    if city
                    else User.MarketRegionMode.GENERAL
                )
                self.customer.save()
                response = self.client.patch(
                    f"/api/v1/addresses/{self.address.id}/",
                    {"additional_instructions": "New instructions"},
                    format="json",
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.address.refresh_from_db()
                self.assertEqual(self.address.service_city_id, self.city.id)
                self.assertEqual(
                    self.address.additional_instructions, "New instructions"
                )

    def test_saved_general_address_can_be_edited_in_service_city_browsing(self):
        address = Address.objects.create(
            user=self.customer,
            name="Family",
            details="Family street",
            manual_city="Manual city",
            manual_area="Manual area",
        )
        response = self.client.patch(
            f"/api/v1/addresses/{address.id}/",
            {"additional_instructions": "Call first"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        address.refresh_from_db()
        self.assertIsNone(address.service_city_id)
        self.assertEqual(address.manual_city, "Manual city")

    def test_new_address_still_requires_selected_region(self):
        response = self.client.post(
            "/api/v1/addresses/",
            {
                "name": "New",
                "details": "Street",
                "service_city_id": self.other_city.id,
                "manual_area": "Area",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_region_options_and_selection_include_configured_boundaries(self):
        for path in ("/api/v1/market-region/options/", "/api/v1/market-region/me/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.data["current_selection"]["service_city"]["boundary_bbox"],
                self.city.boundary_bbox,
            )
        option = next(
            item["service_city"]
            for item in self.client.get("/api/v1/market-region/options/").data[
                "options"
            ]
            if item["service_city"] and item["service_city"]["id"] == self.city.id
        )
        self.assertEqual(option["boundary_bbox"], self.city.boundary_bbox)
        self.assertIn("boundary_geojson", option)

    def test_gps_does_not_select_city_outside_its_bbox(self):
        response = self.client.post(
            "/api/v1/market-region/detect/",
            {"latitude": "10.2000000", "longitude": "10.0000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["action"], "unsupported_location")

    def test_gps_accepts_polygon_only_city_and_rejects_its_hole(self):
        polygon_city = ServiceCity.objects.create(
            name="Polygon only city",
            boundary_geojson={
                "type": "Polygon",
                "coordinates": [
                    [[19, 19], [21, 19], [21, 21], [19, 21], [19, 19]],
                    [
                        [19.9, 19.9],
                        [20.1, 19.9],
                        [20.1, 20.1],
                        [19.9, 20.1],
                        [19.9, 19.9],
                    ],
                ],
            },
        )
        response = self.client.post(
            "/api/v1/market-region/detect/",
            {"latitude": "20.5000000", "longitude": "20.0000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["detected_region"]["service_city"]["id"], polygon_city.id
        )
        response = self.client.post(
            "/api/v1/market-region/detect/",
            {"latitude": "20.0000000", "longitude": "20.0000000"},
            format="json",
        )
        self.assertEqual(response.data["action"], "unsupported_location")
