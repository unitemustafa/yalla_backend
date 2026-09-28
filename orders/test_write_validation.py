from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase
from rest_framework import serializers

from locations.models import Address
from markets.models import Market
from markets.region import (
    GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE,
    MIXED_MARKET_SCOPE_MESSAGE,
    MIXED_SERVICE_CITY_MARKETS_MESSAGE,
    SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE,
)

from .models import Order
from .write_validation import OrderWriteValidationMixin


class ValidationProbe(OrderWriteValidationMixin):
    instance = None


class OrderWriteValidationBranchTests(SimpleTestCase):
    def setUp(self):
        self.probe = ValidationProbe()
        self.city = SimpleNamespace(id=4, pk=4)
        self.area = SimpleNamespace(
            is_active=True, service_city_id=4, delivery_price=Decimal("12.50")
        )

    def test_assignment_requires_approval_matching_courier_and_profile(self):
        representative = SimpleNamespace(courier_profile=SimpleNamespace(service_city_id=4))
        attrs = {"assigned_representative": representative}
        with self.assertRaisesMessage(serializers.ValidationError, "approved"):
            self.probe._validate_assignment(attrs, representative, Order.Scope.SERVICE_CITY, self.city)

        attrs["review_status"] = Order.ReviewStatus.APPROVED
        with self.assertRaisesMessage(serializers.ValidationError, "courier profile"):
            self.probe._validate_assignment(
                attrs, SimpleNamespace(courier_profile=None), Order.Scope.SERVICE_CITY, self.city
            )

        with self.assertRaises(serializers.ValidationError):
            self.probe._validate_assignment(
                attrs, SimpleNamespace(courier_profile=SimpleNamespace(service_city_id=9)),
                Order.Scope.SERVICE_CITY, self.city,
            )

        self.probe._validate_assignment(attrs, representative, Order.Scope.SERVICE_CITY, self.city)
        self.assertEqual(attrs["status"], Order.Status.ASSIGNED)
        self.assertIsNotNone(attrs["assigned_at"])

    def test_unassignment_clears_assignment_and_restores_confirmed_status(self):
        self.probe.instance = SimpleNamespace(assigned_representative_id=7)
        attrs = {"assigned_representative": None}
        self.probe._validate_assignment(attrs, None, Order.Scope.GENERAL, None)
        self.assertIsNone(attrs["assigned_at"])
        self.assertEqual(attrs["status"], Order.Status.CONFIRMED)

    def test_delivery_area_must_be_active_and_in_selected_city(self):
        attrs = {"delivery_area": self.area}
        self.probe._normalize_delivery_fields(attrs, None, self.city, Order.Scope.SERVICE_CITY)
        self.assertEqual(attrs["delivery_type"], Order.DeliveryType.FIXED_AREA)
        self.assertEqual(attrs["delivery_price"], Decimal("12.50"))

        self.area.is_active = False
        with self.assertRaisesMessage(serializers.ValidationError, "active"):
            self.probe._normalize_delivery_fields(
                {"delivery_area": self.area}, None, self.city, Order.Scope.SERVICE_CITY
            )
        self.area.is_active = True
        with self.assertRaisesMessage(serializers.ValidationError, "service city"):
            self.probe._normalize_delivery_fields({"delivery_area": self.area}, None,
                                                  SimpleNamespace(id=8), Order.Scope.SERVICE_CITY)

    def test_fixed_area_delivery_needs_an_area_and_general_resets_area(self):
        with self.assertRaisesMessage(serializers.ValidationError, "required"):
            self.probe._normalize_delivery_fields(
                {"delivery_type": Order.DeliveryType.FIXED_AREA},
                None, self.city, Order.Scope.SERVICE_CITY,
            )
        attrs = {"delivery_area": self.area}
        self.probe._normalize_delivery_fields(attrs, None, None, Order.Scope.GENERAL)
        self.assertIsNone(attrs["delivery_area"])
        self.assertIsNone(attrs["delivery_price"])

    def test_scope_errors_distinguish_general_and_city_offers(self):
        general_market = SimpleNamespace(scope=Market.Scope.GENERAL)
        city_market = SimpleNamespace(scope=Market.Scope.SERVICE_CITY)
        self.assertEqual(
            self.probe._market_scope_error_message(city_market, Order.Scope.GENERAL, None),
            MIXED_MARKET_SCOPE_MESSAGE,
        )
        self.assertEqual(
            self.probe._market_scope_error_message(general_market, Order.Scope.SERVICE_CITY, self.city),
            MIXED_MARKET_SCOPE_MESSAGE,
        )
        self.assertEqual(
            self.probe._market_scope_error_message(city_market, Order.Scope.SERVICE_CITY, self.city),
            MIXED_SERVICE_CITY_MARKETS_MESSAGE,
        )
        offer = SimpleNamespace(show_in_general=False, service_cities=Mock())
        self.assertEqual(
            self.probe._offer_scope_error_message(offer, Order.Scope.GENERAL, None),
            SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE,
        )
        offer.service_cities.filter.return_value.exists.return_value = False
        self.assertEqual(
            self.probe._offer_scope_error_message(offer, Order.Scope.SERVICE_CITY, self.city),
            GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE,
        )

    def test_address_delivery_type_is_not_needed_for_manual_city(self):
        address = SimpleNamespace(
            delivery_type=Address.DeliveryType.DELIVERY, delivery_area_id=None
        )
        attrs = {}
        self.probe._normalize_delivery_fields(attrs, address, self.city, Order.Scope.SERVICE_CITY)
        self.assertIsNone(attrs["delivery_area"])
        self.assertEqual(attrs["delivery_type"], Order.DeliveryType.DELIVERY)

    def test_region_is_derived_from_order_lines_and_market_city(self):
        market = SimpleNamespace(scope=Market.Scope.SERVICE_CITY, service_cities=Mock())
        market.service_cities.filter.return_value.first.return_value = self.city
        items = [{"variant": SimpleNamespace(product=SimpleNamespace(market=market))}]
        attrs = {}
        resolved = self.probe._resolve_order_region(
            attrs, None, None, None, items, None, None
        )
        self.assertEqual(resolved, (market, self.city, Order.Scope.SERVICE_CITY))
        self.assertEqual(attrs["service_city"], self.city)

        general = SimpleNamespace(scope=Market.Scope.GENERAL)
        attrs = {}
        resolved = self.probe._resolve_order_region(
            attrs, None, general, self.city, None, None, None
        )
        self.assertEqual(resolved[1:], (None, Order.Scope.GENERAL))
        self.assertIsNone(attrs["service_city"])

    def test_address_scope_rejects_missing_or_mismatched_city(self):
        with self.assertRaisesMessage(serializers.ValidationError, "required"):
            self.probe._validate_address_region(None, None, Order.Scope.SERVICE_CITY)

        general_address = SimpleNamespace(
            service_city_id=None, delivery_area_id=None,
            manual_city="", manual_area="",
        )
        with self.assertRaisesMessage(serializers.ValidationError, "manual general address"):
            self.probe._validate_address_region(general_address, None, Order.Scope.GENERAL)

        city_address = SimpleNamespace(
            service_city_id=None, delivery_area_id=None,
            manual_city="", manual_area="",
        )
        with self.assertRaisesMessage(serializers.ValidationError, "belong to the service city"):
            self.probe._validate_address_region(city_address, self.city, Order.Scope.SERVICE_CITY)

        city_address.service_city_id = 9
        with self.assertRaisesMessage(serializers.ValidationError, "match the delivery address"):
            self.probe._validate_address_region(city_address, self.city, Order.Scope.SERVICE_CITY)

        city_address.service_city_id = 4
        inactive_city = SimpleNamespace(id=4, is_active=False)
        with self.assertRaisesMessage(serializers.ValidationError, "must be active"):
            self.probe._validate_address_region(city_address, inactive_city, Order.Scope.SERVICE_CITY)

    def test_offer_scope_rejects_a_market_outside_the_order_scope(self):
        market = SimpleNamespace(scope=Market.Scope.GENERAL, service_cities=Mock())
        offer = SimpleNamespace(
            show_in_general=True, market=market,
            service_cities=Mock(), products=Mock(),
        )
        offer.products.select_related.return_value.all.return_value = []
        self.assertTrue(self.probe._offer_matches_order_scope(offer, Order.Scope.GENERAL, None))
        offer.show_in_general = False
        self.assertFalse(self.probe._offer_matches_order_scope(offer, Order.Scope.GENERAL, None))
        offer.service_cities.filter.return_value.exists.return_value = False
        self.assertFalse(self.probe._offer_matches_order_scope(offer, Order.Scope.SERVICE_CITY, self.city))
