from math import asin, cos, radians, sin, sqrt

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from accounts.models import User
from catalog.models import Product
from locations.models import ServiceCity
from offers.models import Offer

from .models import Market


REGION_SELECTION_REQUIRED_MESSAGE = (
    "Select a market browsing region before loading market content."
)
MIXED_MARKET_SCOPE_MESSAGE = "لا يمكن دمج محلات عامة مع محلات مدينة في نفس الطلب"
SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE = "لا يمكن استخدام عرض مدينة داخل طلب عام"
GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE = "لا يمكن استخدام عرض عام داخل طلب مدينة"
MIXED_SERVICE_CITY_MARKETS_MESSAGE = "لا يمكن دمج منتجات من مدن مختلفة في نفس الطلب"
EARTH_RADIUS_KM = 6371.0088


def service_city_payload(service_city):
    if service_city is None:
        return None
    return {
        "id": service_city.id,
        "name": service_city.name,
        "delivery_price": service_city.delivery_price,
        "is_active": service_city.is_active,
    }


def compact_service_city_payload(service_city):
    if service_city is None:
        return None
    return {
        "id": service_city.id,
        "name": service_city.name,
    }


def compact_market_region_selection(user):
    selection = current_market_region_selection(user)
    if selection is None:
        return None
    if selection["mode"] == User.MarketRegionMode.GENERAL:
        return {
            "mode": User.MarketRegionMode.GENERAL,
            "label": User.MarketRegionMode.GENERAL.label,
            "service_city": None,
        }
    return {
        "mode": User.MarketRegionMode.SERVICE_CITY,
        "service_city": compact_service_city_payload(
            user.market_region_service_city
        ),
    }


def service_city_region_selection(service_city):
    return {
        "mode": User.MarketRegionMode.SERVICE_CITY,
        "service_city": compact_service_city_payload(service_city),
    }


def general_region_selection():
    return {
        "mode": User.MarketRegionMode.GENERAL,
        "label": User.MarketRegionMode.GENERAL.label,
        "service_city": None,
    }


def current_market_region_selection(user):
    mode = user.market_region_mode
    if mode == User.MarketRegionMode.GENERAL:
        return {
            "mode": User.MarketRegionMode.GENERAL,
            "label": User.MarketRegionMode.GENERAL.label,
            "service_city": None,
            "updated_at": user.market_region_updated_at,
        }

    service_city = getattr(user, "market_region_service_city", None)
    if (
        mode == User.MarketRegionMode.SERVICE_CITY
        and service_city is not None
        and service_city.is_active
    ):
        return {
            "mode": User.MarketRegionMode.SERVICE_CITY,
            "label": service_city.name,
            "service_city": service_city_payload(service_city),
            "updated_at": user.market_region_updated_at,
        }

    return None


def detect_service_city(latitude, longitude):
    matching_cities = []
    cities = ServiceCity.objects.filter(
        is_active=True,
        center_latitude__isnull=False,
        center_longitude__isnull=False,
        radius_km__isnull=False,
        radius_km__gt=0,
    ).order_by("id")

    for city in cities:
        distance_km = haversine_distance_km(
            latitude,
            longitude,
            city.center_latitude,
            city.center_longitude,
        )
        if distance_km <= float(city.radius_km):
            matching_cities.append((distance_km, city.id, city))

    if not matching_cities:
        return None
    return min(matching_cities, key=lambda item: (item[0], item[1]))[2]


def haversine_distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
    lat_1 = float(latitude_1)
    lon_1 = float(longitude_1)
    lat_2 = float(latitude_2)
    lon_2 = float(longitude_2)
    latitude_delta = radians(lat_2 - lat_1)
    longitude_delta = radians(lon_2 - lon_1)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(lat_1))
        * cos(radians(lat_2))
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))


def no_market_region_selection_data(message=REGION_SELECTION_REQUIRED_MESSAGE):
    return {
        "requires_region_selection": True,
        "message": message,
        "current_selection": None,
    }


def no_market_region_selection_response(
    message=REGION_SELECTION_REQUIRED_MESSAGE,
):
    return Response(
        no_market_region_selection_data(message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def visible_market_queryset(user):
    selection = current_market_region_selection(user)
    if selection is None:
        return Market.objects.none()

    markets = Market.objects.filter(status=Market.Status.ACTIVE)
    if selection["mode"] == User.MarketRegionMode.GENERAL:
        return markets.filter(scope=Market.Scope.GENERAL)

    service_city_id = selection["service_city"]["id"]
    return markets.filter(
        service_cities__id=service_city_id,
        service_cities__is_active=True,
        scope__in=[Market.Scope.GENERAL, Market.Scope.SERVICE_CITY],
    ).distinct()


def visible_product_queryset(user):
    return Product.objects.filter(market__in=visible_market_queryset(user))


def region_filtered_offer_queryset(queryset, user):
    selection = current_market_region_selection(user)
    if selection is None:
        return queryset.none()

    if selection["mode"] == User.MarketRegionMode.GENERAL:
        return queryset.filter(show_in_general=True)

    return queryset.filter(
        service_cities__id=selection["service_city"]["id"],
        service_cities__is_active=True,
    ).distinct()


def visible_offer_queryset(user):
    now = timezone.now()
    queryset = Offer.objects.filter(
        status=Offer.Status.ACTIVE,
        start_time__lte=now,
        end_time__gte=now,
    )
    return region_filtered_offer_queryset(queryset, user)


def market_matches_region(market, selection):
    if market is None or market.status != Market.Status.ACTIVE:
        return False
    if selection["mode"] == User.MarketRegionMode.GENERAL:
        return market.scope == Market.Scope.GENERAL
    return (
        market.scope in [Market.Scope.GENERAL, Market.Scope.SERVICE_CITY]
        and market.service_cities.filter(
            pk=selection["service_city"]["id"],
            is_active=True,
        ).exists()
    )


def address_matches_market_region(address, current_selection):
    if address is None or current_selection is None or not address.is_active:
        return False
    if current_selection["mode"] == User.MarketRegionMode.GENERAL:
        return (
            address.service_city_id is None
            and address.delivery_area_id is None
            and bool((address.manual_city or "").strip())
            and bool((address.manual_area or "").strip())
        )
    return address.service_city_id == current_selection["service_city"]["id"]


def product_matches_region(product, selection):
    return market_matches_region(product.market, selection)


def offer_matches_region(offer, selection):
    if selection["mode"] == User.MarketRegionMode.GENERAL:
        return offer.show_in_general
    return offer.service_cities.filter(
        pk=selection["service_city"]["id"],
        is_active=True,
    ).exists()


def order_region_validation_error(user, variants, offers):
    selection = current_market_region_selection(user)
    if selection is None:
        return no_market_region_selection_data(
            "Select a market browsing region before checkout."
        )

    errors = {}
    if selection["mode"] == User.MarketRegionMode.GENERAL:
        if any(
            variant.product.market.scope != Market.Scope.GENERAL
            for variant in variants
        ):
            errors["items"] = MIXED_MARKET_SCOPE_MESSAGE

        for offer in offers:
            offer_products = offer.products.select_related(
                "market",
                "market__classification",
            ).prefetch_related("market__service_cities")
            if not offer.show_in_general:
                errors["offers"] = SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE
                break
            if (
                offer.market.scope != Market.Scope.GENERAL
                or any(
                    product.market.scope != Market.Scope.GENERAL
                    for product in offer_products
                )
            ):
                errors["offers"] = MIXED_MARKET_SCOPE_MESSAGE
                break
        return errors or None

    if any(not product_matches_region(variant.product, selection) for variant in variants):
        errors["items"] = MIXED_SERVICE_CITY_MARKETS_MESSAGE

    for offer in offers:
        offer_products = offer.products.select_related(
            "market",
            "market__classification",
        ).prefetch_related("market__service_cities")
        if not offer_matches_region(offer, selection):
            errors["offers"] = GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE
            break
        if not offer_matches_region(offer, selection) or any(
            not product_matches_region(product, selection)
            for product in offer_products
        ):
            errors["offers"] = MIXED_SERVICE_CITY_MARKETS_MESSAGE
            break
    return errors or None
