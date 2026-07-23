from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from accounts.models import User

from .geometry import geometry_covers_point, point_within_egypt_bounds
from .models import Address, DeliveryArea, ServiceCity


@dataclass(frozen=True)
class PointResolution:
    allowed: bool
    reason_code: str | None
    service_city: ServiceCity | None
    delivery_area: DeliveryArea | None
    fulfillment_type: str | None
    delivery_price: Decimal | None
    eta_min_minutes: int | None
    eta_max_minutes: int | None

    def as_dict(self):
        city = self.service_city
        area = self.delivery_area
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "service_city": (
                {
                    "id": city.id,
                    "name": city.name,
                    "boundary_bbox": city.boundary_bbox,
                }
                if city is not None
                else None
            ),
            "delivery_area": (
                {
                    "id": area.id,
                    "name": area.name,
                    "delivery_price": f"{area.delivery_price:.2f}",
                    "eta_min_minutes": area.eta_min_minutes,
                    "eta_max_minutes": area.eta_max_minutes,
                }
                if area is not None
                else None
            ),
            "fulfillment_type": self.fulfillment_type,
            "delivery_price": (
                f"{self.delivery_price:.2f}"
                if self.delivery_price is not None
                else None
            ),
            "eta_min_minutes": self.eta_min_minutes,
            "eta_max_minutes": self.eta_max_minutes,
        }


def detect_service_city(latitude, longitude):
    cities = ServiceCity.objects.filter(
        is_active=True,
    ).order_by("id")
    for city in cities.filter(
        is_active=True,
        boundary_geojson__isnull=False,
    ):
        if geometry_covers_point(city.boundary_geojson, latitude, longitude):
            return city
    legacy_matches = []
    for city in cities.filter(
        boundary_geojson__isnull=True,
        center_latitude__isnull=False,
        center_longitude__isnull=False,
        radius_km__isnull=False,
        radius_km__gt=0,
    ):
        distance = _haversine_distance_km(
            latitude,
            longitude,
            city.center_latitude,
            city.center_longitude,
        )
        if distance <= float(city.radius_km):
            legacy_matches.append((distance, city.id, city))
    if legacy_matches:
        return min(legacy_matches, key=lambda item: (item[0], item[1]))[2]
    return None


def detect_delivery_area(service_city, latitude, longitude):
    if service_city is None:
        return None
    for area in DeliveryArea.objects.filter(
        service_city=service_city,
        service_city__is_active=True,
        is_active=True,
        boundary_geojson__isnull=False,
    ).order_by("id"):
        if geometry_covers_point(area.boundary_geojson, latitude, longitude):
            return area
    return None


def resolve_point_for_selection(*, user, latitude, longitude):
    mode = user.market_region_mode
    selected_city = user.market_region_service_city

    if mode == User.MarketRegionMode.SERVICE_CITY:
        if selected_city is None or not selected_city.is_active:
            return PointResolution(
                False, "selected_city_unavailable", None, None, None, None, None, None
            )
        if not selected_city.boundary_geojson:
            return PointResolution(
                False,
                "selected_city_boundary_missing",
                selected_city,
                None,
                None,
                None,
                None,
                None,
            )
        if not geometry_covers_point(
            selected_city.boundary_geojson,
            latitude,
            longitude,
        ):
            return PointResolution(
                False,
                "outside_selected_city",
                selected_city,
                None,
                None,
                None,
                None,
                None,
            )
        city = selected_city
    elif mode == User.MarketRegionMode.GENERAL:
        if not point_within_egypt_bounds(latitude, longitude):
            return PointResolution(
                False, "outside_egypt", None, None, None, None, None, None
            )
        city = detect_service_city(latitude, longitude)
    else:
        return PointResolution(
            False, "region_selection_required", None, None, None, None, None, None
        )

    area = detect_delivery_area(city, latitude, longitude)
    if area is not None:
        return PointResolution(
            True,
            None,
            city,
            area,
            Address.FulfillmentType.DIRECT,
            area.delivery_price,
            area.eta_min_minutes,
            area.eta_max_minutes,
        )
    return PointResolution(
        True,
        None,
        city,
        None,
        Address.FulfillmentType.EXTERNAL_SHIPPING,
        None,
        None,
        None,
    )

def _haversine_distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
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
    return 2 * 6371.0088 * asin(sqrt(haversine))
