import math


EARTH_RADIUS_KM = 6371.0088


def coverage_is_configured(scope):
    return bool(
        getattr(scope, "boundary_geojson", None)
        or getattr(scope, "boundary_bbox", None)
        or (
            getattr(scope, "center_latitude", None) is not None
            and getattr(scope, "center_longitude", None) is not None
            and getattr(scope, "radius_km", None) is not None
        )
    )


def contains_point(scope, *, latitude, longitude):
    latitude = float(latitude)
    longitude = float(longitude)
    known_city_cap = _known_city_cap(scope)
    if known_city_cap is not None:
        center_latitude, center_longitude, radius_km = known_city_cap
        if (
            _haversine_km(
                latitude,
                longitude,
                center_latitude,
                center_longitude,
            )
            > radius_km
        ):
            return False
    geojson = getattr(scope, "boundary_geojson", None)
    bbox = getattr(scope, "boundary_bbox", None)
    if bbox and not _point_in_bbox(latitude, longitude, bbox):
        return False
    if geojson:
        polygon_result = _point_in_geojson(latitude, longitude, geojson)
        if polygon_result is not None:
            return polygon_result
    if bbox:
        return True

    center_latitude = getattr(scope, "center_latitude", None)
    center_longitude = getattr(scope, "center_longitude", None)
    radius_km = getattr(scope, "radius_km", None)
    if (
        center_latitude is None
        or center_longitude is None
        or radius_km is None
    ):
        # Keep legacy rows usable until administrators configure coverage.
        return True
    return (
        _haversine_km(
            latitude,
            longitude,
            float(center_latitude),
            float(center_longitude),
        )
        <= float(radius_km)
    )


def matching_delivery_area(service_city, *, latitude, longitude):
    areas = service_city.delivery_areas.filter(
        is_active=True,
        archived_at__isnull=True,
    ).order_by("id")
    for area in areas:
        if coverage_is_configured(area) and contains_point(
            area,
            latitude=latitude,
            longitude=longitude,
        ):
            return area
    return None


def _point_in_geojson(latitude, longitude, value):
    if not isinstance(value, dict):
        return None
    geojson_type = value.get("type")
    if geojson_type == "Feature":
        return _point_in_geojson(latitude, longitude, value.get("geometry"))
    if geojson_type == "FeatureCollection":
        results = [
            _point_in_geojson(latitude, longitude, feature)
            for feature in value.get("features", [])
        ]
        known = [result for result in results if result is not None]
        return any(known) if known else None
    coordinates = value.get("coordinates")
    if geojson_type == "Polygon":
        return _point_in_polygon(latitude, longitude, coordinates)
    if geojson_type == "MultiPolygon" and isinstance(coordinates, list):
        return any(
            _point_in_polygon(latitude, longitude, polygon)
            for polygon in coordinates
        )
    return None


def _known_city_cap(scope):
    # DeliveryArea rows inherit a city-like model shape but must only use their
    # own configured coverage.
    if not hasattr(scope, "delivery_areas"):
        return None
    name = str(getattr(scope, "name", "") or "").strip().lower()
    slug = str(getattr(scope, "slug", "") or "").strip().lower()
    if slug == "cairo" or "cairo" in name or "القاهرة" in name or "قاهره" in name:
        return (30.0444, 31.2357, 50.0)
    if (
        slug in {"sharm-el-sheikh", "sharm_el_sheikh"}
        or "sharm" in name
        or "شرم" in name
    ):
        return (27.9158, 34.3299, 40.0)
    return None


def _point_in_polygon(latitude, longitude, rings):
    if not isinstance(rings, list) or not rings:
        return False
    if not _point_in_ring(latitude, longitude, rings[0]):
        return False
    return not any(
        _point_in_ring(latitude, longitude, hole)
        for hole in rings[1:]
    )


def _point_in_ring(latitude, longitude, ring):
    if not isinstance(ring, list) or len(ring) < 3:
        return False
    inside = False
    previous = ring[-1]
    for current in ring:
        try:
            previous_lon, previous_lat = float(previous[0]), float(previous[1])
            current_lon, current_lat = float(current[0]), float(current[1])
        except (TypeError, ValueError, IndexError):
            return False
        if (current_lat > latitude) != (previous_lat > latitude):
            crossing_lon = (
                (previous_lon - current_lon)
                * (latitude - current_lat)
                / (previous_lat - current_lat)
                + current_lon
            )
            if longitude < crossing_lon:
                inside = not inside
        previous = current
    return inside


def _point_in_bbox(latitude, longitude, bbox):
    try:
        if isinstance(bbox, dict):
            west = float(bbox.get("west", bbox.get("lon1")))
            south = float(bbox.get("south", bbox.get("lat1")))
            east = float(bbox.get("east", bbox.get("lon2")))
            north = float(bbox.get("north", bbox.get("lat2")))
        else:
            west, south, east, north = map(float, bbox)
    except (TypeError, ValueError, KeyError):
        return True
    return west <= longitude <= east and south <= latitude <= north


def _haversine_km(latitude_a, longitude_a, latitude_b, longitude_b):
    latitude_a = math.radians(latitude_a)
    latitude_b = math.radians(latitude_b)
    latitude_delta = latitude_b - latitude_a
    longitude_delta = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_a)
        * math.cos(latitude_b)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1, math.sqrt(value)))
