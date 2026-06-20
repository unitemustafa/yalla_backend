from math import asin, cos, radians, sin, sqrt

from .models import Market


EARTH_RADIUS_KM = 6371.0088


def markets_covering_address(address):
    market_ids = []
    markets = (
        Market.objects.filter(
            status=Market.Status.ACTIVE,
            delivery_areas__is_active=True,
        )
        .prefetch_related("delivery_areas")
        .distinct()
    )

    latitude = float(address.latitude)
    longitude = float(address.longitude)
    for market in markets:
        if any(
            _distance_km(
                latitude,
                longitude,
                float(area.center_latitude),
                float(area.center_longitude),
            )
            <= float(area.radius_km)
            for area in market.delivery_areas.all()
            if area.is_active
        ):
            market_ids.append(market.id)

    return market_ids


def _distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
    latitude_delta = radians(latitude_2 - latitude_1)
    longitude_delta = radians(longitude_2 - longitude_1)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(latitude_1))
        * cos(radians(latitude_2))
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))
