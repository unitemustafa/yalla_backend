from types import SimpleNamespace

from django.test import TestCase

from locations.models import DeliveryArea, ServiceCity

from .models import Market, MarketClassification
from .services import markets_covering_address


class MarketCoverageSelectorTests(TestCase):
    def setUp(self):
        self.classification = MarketClassification.objects.create(name="Coverage")

    def market(self, name, **kwargs):
        return Market.objects.create(
            classification=self.classification,
            name=name,
            **kwargs,
        )

    def test_service_city_address_uses_active_market_membership(self):
        city = ServiceCity.objects.create(name="City")
        active = self.market("Active")
        inactive = self.market("Inactive", status=Market.Status.INACTIVE)
        active.service_cities.add(city)
        inactive.service_cities.add(city)
        address = SimpleNamespace(
            service_city_id=city.id,
            latitude=None,
            longitude=None,
        )
        self.assertEqual(markets_covering_address(address), [active.id])

    def test_coordinate_free_legacy_address_uses_general_markets(self):
        general = self.market("General", scope=Market.Scope.GENERAL)
        self.market("City", scope=Market.Scope.SERVICE_CITY)
        address = SimpleNamespace(
            service_city_id=None,
            latitude=None,
            longitude=None,
        )
        self.assertEqual(markets_covering_address(address), [general.id])

    def test_legacy_coordinates_use_delivery_area_radius(self):
        city = ServiceCity.objects.create(name="Legacy City")
        area = DeliveryArea.objects.create(
            service_city=city,
            name="Legacy Area",
            delivery_price=10,
            center_latitude=30,
            center_longitude=31,
            radius_km=5,
        )
        market = self.market("Legacy Market")
        market.delivery_areas.add(area)
        near = SimpleNamespace(
            service_city_id=None,
            latitude=30.01,
            longitude=31.01,
        )
        far = SimpleNamespace(
            service_city_id=None,
            latitude=35,
            longitude=35,
        )
        self.assertEqual(markets_covering_address(near), [market.id])
        self.assertEqual(markets_covering_address(far), [])
