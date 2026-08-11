from django.utils import timezone
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


class OrderWriteValidationMixin:
    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        address = attrs.get(
            "delivery_address",
            getattr(self.instance, "delivery_address", None),
        )
        market = attrs.get("market", getattr(self.instance, "market", None))
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        representative = attrs.get(
            "assigned_representative",
            getattr(self.instance, "assigned_representative", None),
        )
        items = attrs.get("items")
        offers = attrs.get("order_offers")
        order_scope = attrs.get(
            "order_scope",
            getattr(self.instance, "order_scope", None),
        )

        self._validate_address_owner(address, user)
        market, service_city, order_scope = self._resolve_order_region(
            attrs,
            address,
            market,
            service_city,
            items,
            offers,
            order_scope,
        )
        self._validate_address_region(address, service_city, order_scope)
        if self._delivery_fields_need_normalization(attrs):
            self._normalize_delivery_fields(
                attrs,
                address,
                service_city,
                order_scope,
            )
        self._validate_content_scope(
            market,
            items,
            offers,
            order_scope,
            service_city,
        )
        self._validate_assignment(
            attrs,
            representative,
            order_scope,
            service_city,
        )
        return attrs

    @staticmethod
    def _validate_address_owner(address, user):
        if address and user and address.user_id != user.id:
            raise serializers.ValidationError(
                {"delivery_address_id": "Address does not belong to the order user."}
            )

    def _resolve_order_region(
        self,
        attrs,
        address,
        market,
        service_city,
        items,
        offers,
        order_scope,
    ):
        if market is None:
            market = self._first_market_from_lines(items, offers)
            if market is not None:
                attrs["market"] = market
        if order_scope is None and market is not None:
            order_scope = (
                Order.Scope.GENERAL
                if market.scope == Market.Scope.GENERAL
                else Order.Scope.SERVICE_CITY
            )
            attrs["order_scope"] = order_scope
        if (
            service_city is None
            and order_scope == Order.Scope.SERVICE_CITY
            and address is not None
            and address.service_city_id
        ):
            service_city = address.service_city
            attrs["service_city"] = service_city
        if (
            service_city is None
            and order_scope == Order.Scope.SERVICE_CITY
            and market is not None
        ):
            service_city = market.service_cities.filter(is_active=True).first()
            if service_city is not None:
                attrs["service_city"] = service_city
        if order_scope == Order.Scope.GENERAL:
            service_city = None
            attrs["service_city"] = None
        return market, service_city, order_scope

    @staticmethod
    def _validate_address_region(address, service_city, order_scope):
        if order_scope == Order.Scope.SERVICE_CITY and service_city is None:
            raise serializers.ValidationError(
                {"service_city_id": "Service city is required."}
            )
        if address is not None:
            if order_scope == Order.Scope.GENERAL and not (
                address.service_city_id is None
                and address.delivery_area_id is None
                and bool((address.manual_city or "").strip())
                and bool((address.manual_area or "").strip())
            ):
                raise serializers.ValidationError(
                    {
                        "delivery_address_id": (
                            "General orders require a manual general address."
                        )
                    }
                )
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and address.service_city_id is None
            ):
                raise serializers.ValidationError(
                    {
                        "delivery_address_id": (
                            "Delivery address must belong to the service city."
                        )
                    }
                )
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and address.service_city_id != service_city.id
            ):
                raise serializers.ValidationError(
                    {
                        "service_city_id": (
                            "Service city must match the delivery address service city."
                        )
                    }
                )
        if service_city is not None and not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        if (
            order_scope == Order.Scope.SERVICE_CITY
            and address is not None
            and address.service_city_id
            and address.service_city_id != service_city.id
        ):
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "Service city must match the delivery address service city."
                    )
                }
            )

    def _delivery_fields_need_normalization(self, attrs):
        return self.instance is None or any(
            field in attrs
            for field in (
                "delivery_address",
                "service_city",
                "delivery_area",
                "delivery_type",
                "delivery_price",
            )
        )

    def _validate_content_scope(
        self,
        market,
        items,
        offers,
        order_scope,
        service_city,
    ):
        if market and not self._market_matches_order_scope(
            market,
            order_scope,
            service_city,
        ):
            raise serializers.ValidationError(
                {
                    "market_id": self._market_scope_error_message(
                        market,
                        order_scope,
                        service_city,
                    )
                }
            )
        if items is not None:
            self._validate_item_scopes(items, order_scope, service_city)
        if offers is not None:
            self._validate_offer_scopes(offers, order_scope, service_city)

    def _validate_item_scopes(self, items, order_scope, service_city):
        invalid_market = next(
            (
                item["variant"].product.market
                for item in items
                if not self._market_matches_order_scope(
                    item["variant"].product.market,
                    order_scope,
                    service_city,
                )
            ),
            None,
        )
        if invalid_market is not None:
            raise serializers.ValidationError(
                {
                    "items": self._market_scope_error_message(
                        invalid_market,
                        order_scope,
                        service_city,
                    )
                }
            )

    def _validate_offer_scopes(self, offers, order_scope, service_city):
        invalid_offer = next(
            (
                item["offer"]
                for item in offers
                if not self._offer_matches_order_scope(
                    item["offer"],
                    order_scope,
                    service_city,
                )
            ),
            None,
        )
        if invalid_offer is not None:
            raise serializers.ValidationError(
                {
                    "offers": self._offer_scope_error_message(
                        invalid_offer,
                        order_scope,
                        service_city,
                    )
                }
            )

    def _validate_assignment(
        self,
        attrs,
        representative,
        order_scope,
        service_city,
    ):
        if "assigned_representative" not in attrs:
            return
        if not representative:
            attrs["assigned_at"] = None
            if self.instance and self.instance.assigned_representative_id:
                attrs["status"] = Order.Status.CONFIRMED
            return

        review_status = attrs.get(
            "review_status",
            getattr(
                self.instance,
                "review_status",
                Order.ReviewStatus.PENDING_REVIEW,
            ),
        )
        if review_status != Order.ReviewStatus.APPROVED:
            raise serializers.ValidationError(
                {
                    "assigned_representative_id": (
                        "Order must be approved before assignment."
                    )
                }
            )
        profile = getattr(representative, "courier_profile", None)
        if profile is None:
            raise serializers.ValidationError(
                {
                    "assigned_representative_id": (
                        "Representative must have a courier profile."
                    )
                }
            )
        courier_service_city = self._courier_service_city_for_order(
            order_scope,
            service_city,
            attrs.get(
                "delivery_area",
                getattr(self.instance, "delivery_area", None),
            ),
        )
        if (
            courier_service_city is not None
            and profile.service_city_id != courier_service_city.id
        ):
            raise serializers.ValidationError(
                {
                    "assigned_representative_id": (
                        "هذا المندوب لا يعمل في نفس مدينة الطلب."
                    )
                }
            )
        attrs["status"] = Order.Status.ASSIGNED
        if not attrs.get("assigned_at"):
            attrs["assigned_at"] = timezone.now()

    def _normalize_delivery_fields(self, attrs, address, service_city, order_scope):
        if order_scope == Order.Scope.GENERAL:
            attrs["service_city"] = None
            attrs["delivery_area"] = None
            attrs["delivery_type"] = Order.DeliveryType.DELIVERY
            attrs["delivery_price"] = None
            return

        if address is not None:
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and address.delivery_type == Address.DeliveryType.FIXED_AREA
                and address.delivery_area_id
            ):
                delivery_area = address.delivery_area
                if (
                    delivery_area.is_active
                    and service_city is not None
                    and delivery_area.service_city_id == service_city.id
                ):
                    attrs["delivery_area"] = delivery_area
                    attrs["delivery_type"] = Order.DeliveryType.FIXED_AREA
                    attrs["delivery_price"] = delivery_area.delivery_price
                    return

            attrs["delivery_area"] = None
            attrs["delivery_type"] = Order.DeliveryType.DELIVERY
            attrs["delivery_price"] = None
            return

        delivery_area = attrs.get(
            "delivery_area",
            getattr(self.instance, "delivery_area", None),
        )
        delivery_type = attrs.get(
            "delivery_type",
            getattr(self.instance, "delivery_type", Order.DeliveryType.DELIVERY),
        )
        if delivery_area is not None:
            if order_scope == Order.Scope.SERVICE_CITY and service_city is None:
                raise serializers.ValidationError(
                    {
                        "service_city_id": "Service city is required for fixed-area delivery."
                    }
                )
            if not delivery_area.is_active:
                raise serializers.ValidationError(
                    {"delivery_area_id": "Delivery area must be active."}
                )
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and delivery_area.service_city_id != service_city.id
            ):
                raise serializers.ValidationError(
                    {
                        "delivery_area_id": (
                            "Delivery area must belong to the service city."
                        )
                    }
                )
            attrs["delivery_area"] = delivery_area
            attrs["delivery_type"] = Order.DeliveryType.FIXED_AREA
            attrs["delivery_price"] = delivery_area.delivery_price
            return

        if delivery_type == Order.DeliveryType.FIXED_AREA:
            raise serializers.ValidationError(
                {
                    "delivery_area_id": "Delivery area is required for fixed-area delivery."
                }
            )
        attrs["delivery_area"] = None
        attrs["delivery_type"] = Order.DeliveryType.DELIVERY
        attrs["delivery_price"] = None

    def _market_matches_order_scope(self, market, order_scope, service_city):
        if market is None or order_scope is None:
            return False
        if order_scope == Order.Scope.GENERAL:
            return market.scope == Market.Scope.GENERAL
        return (
            market.scope in [Market.Scope.GENERAL, Market.Scope.SERVICE_CITY]
            and service_city is not None
            and market.service_cities.filter(
                pk=service_city.pk,
                is_active=True,
            ).exists()
        )

    def _offer_matches_order_scope(self, offer, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            if not offer.show_in_general:
                return False
        elif order_scope == Order.Scope.SERVICE_CITY:
            if (
                service_city is None
                or not offer.service_cities.filter(
                    pk=service_city.id,
                    is_active=True,
                ).exists()
            ):
                return False
        else:
            return False

        if not self._market_matches_order_scope(
            offer.market,
            order_scope,
            service_city,
        ):
            return False
        return all(
            self._market_matches_order_scope(
                product.market,
                order_scope,
                service_city,
            )
            for product in offer.products.select_related("market").all()
        )

    def _market_scope_error_message(self, market, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            return MIXED_MARKET_SCOPE_MESSAGE
        if market.scope == Market.Scope.GENERAL:
            return MIXED_MARKET_SCOPE_MESSAGE
        return MIXED_SERVICE_CITY_MARKETS_MESSAGE

    def _offer_scope_error_message(self, offer, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            if not offer.show_in_general:
                return SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE
            return MIXED_MARKET_SCOPE_MESSAGE
        if (
            service_city is None
            or not offer.service_cities.filter(
                pk=service_city.id,
                is_active=True,
            ).exists()
        ):
            return GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE
        return MIXED_SERVICE_CITY_MARKETS_MESSAGE

    @staticmethod
    def _courier_service_city_for_order(order_scope, service_city, delivery_area):
        if order_scope == Order.Scope.SERVICE_CITY:
            return service_city
        return None

    @staticmethod
    def _first_market_from_lines(items, offers):
        if items:
            return items[0]["variant"].product.market
        if offers:
            return offers[0]["offer"].market
        return None
