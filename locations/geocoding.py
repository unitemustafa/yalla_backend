import hashlib
import json
import math

import requests
from django.conf import settings
from django.core.cache import caches

from config.rate_limit import evaluate_rate_limit, rate_limit_mode


AUTOCOMPLETE_URL = "https://api.geoapify.com/v1/geocode/autocomplete"
FORWARD_URL = "https://api.geoapify.com/v1/geocode/search"
REVERSE_URL = "https://api.geoapify.com/v1/geocode/reverse"
AUTOCOMPLETE_CACHE_SECONDS = 5 * 60
CITY_COVERAGE_CACHE_SECONDS = 30 * 24 * 60 * 60
REVERSE_CACHE_SECONDS = 24 * 60 * 60
EARTH_RADIUS_KM = 6371.0088


class GeoapifyUnavailable(Exception):
    pass


class GeoapifyRateLimited(Exception):
    def __init__(self, retry_after_seconds=1):
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__("Geoapify request rate limit exceeded.")


def autocomplete(*, query, latitude, longitude, language, request):
    normalized_query = " ".join(query.strip().split())
    cache_key = _cache_key(
        "autocomplete",
        {
            "q": normalized_query.casefold(),
            "lat": round(float(latitude), 5),
            "lon": round(float(longitude), 5),
            "lang": language,
        },
    )
    cached = caches["geocoding"].get(cache_key)
    if cached is not None:
        return cached

    payload = _provider_get(
        AUTOCOMPLETE_URL,
        {
            "text": normalized_query,
            "format": "json",
            "filter": "countrycode:eg",
            "bias": f"proximity:{float(longitude)},{float(latitude)}",
            "lang": language,
            "limit": 5,
        },
        request=request,
    )
    results = [_normalize_result(item) for item in payload.get("results", [])[:5]]
    caches["geocoding"].set(
        cache_key,
        results,
        timeout=AUTOCOMPLETE_CACHE_SECONDS,
    )
    return results


def reverse(*, latitude, longitude, language, request):
    rounded_latitude = round(float(latitude), 5)
    rounded_longitude = round(float(longitude), 5)
    cache_key = _cache_key(
        "reverse",
        {
            "lat": rounded_latitude,
            "lon": rounded_longitude,
            "lang": language,
        },
    )
    cached = caches["geocoding"].get(cache_key)
    if cached is not None:
        return cached.get("location")

    payload = _provider_get(
        REVERSE_URL,
        {
            "lat": float(latitude),
            "lon": float(longitude),
            "format": "json",
            "lang": language,
            "limit": 1,
        },
        request=request,
    )
    raw_results = payload.get("results", [])
    location = _normalize_result(raw_results[0]) if raw_results else None
    caches["geocoding"].set(
        cache_key,
        {"location": location},
        timeout=REVERSE_CACHE_SECONDS,
    )
    return location


def city_coverage(*, query, language, request):
    normalized_query = " ".join(query.strip().split())
    cache_key = _cache_key(
        "city-coverage",
        {
            "q": normalized_query.casefold(),
            "lang": language,
        },
    )
    cached = caches["geocoding"].get(cache_key)
    if cached is not None:
        return cached.get("coverage")

    payload = _provider_get(
        FORWARD_URL,
        {
            "text": normalized_query,
            "type": "city",
            "format": "json",
            "filter": "countrycode:eg",
            "lang": language,
            "limit": 5,
        },
        request=request,
    )
    coverage = None
    for item in payload.get("results", []):
        coverage = _city_coverage_from_result(item)
        if coverage is not None:
            break

    caches["geocoding"].set(
        cache_key,
        {"coverage": coverage},
        timeout=CITY_COVERAGE_CACHE_SECONDS,
    )
    return coverage


def _provider_get(url, params, *, request):
    decision = evaluate_rate_limit(request, ("geocoding_global",))
    if not decision.allowed and rate_limit_mode() == "enforce":
        raise GeoapifyRateLimited(decision.retry_after_seconds)

    api_key = settings.GEOAPIFY_API_KEY
    if not api_key:
        raise GeoapifyUnavailable("GEOAPIFY_API_KEY is not configured.")

    try:
        response = requests.get(
            url,
            params={**params, "apiKey": api_key},
            timeout=(
                settings.GEOAPIFY_CONNECT_TIMEOUT,
                settings.GEOAPIFY_READ_TIMEOUT,
            ),
        )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                retry_after = int(retry_after)
            except (TypeError, ValueError):
                retry_after = 1
            raise GeoapifyRateLimited(retry_after)
        response.raise_for_status()
        payload = response.json()
    except GeoapifyRateLimited:
        raise
    except (requests.RequestException, ValueError, TypeError) as error:
        raise GeoapifyUnavailable() from error

    if not isinstance(payload, dict) or not isinstance(
        payload.get("results", []),
        list,
    ):
        raise GeoapifyUnavailable()
    return payload


def _normalize_result(item):
    rank = item.get("rank") if isinstance(item.get("rank"), dict) else {}
    distance = item.get("distance", rank.get("distance"))
    return {
        "place_id": _optional_text(item.get("place_id")),
        "formatted_address": _optional_text(item.get("formatted")),
        "address_line1": _optional_text(item.get("address_line1")),
        "address_line2": _optional_text(item.get("address_line2")),
        "latitude": _optional_float(item.get("lat")),
        "longitude": _optional_float(item.get("lon")),
        "result_type": _optional_text(item.get("result_type")),
        "distance_meters": _optional_float(distance),
    }


def _city_coverage_from_result(item):
    bbox = item.get("bbox")
    if not isinstance(bbox, dict):
        return None
    try:
        west = float(bbox["lon1"])
        south = float(bbox["lat1"])
        east = float(bbox["lon2"])
        north = float(bbox["lat2"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (
        -180 <= west <= 180
        and -180 <= east <= 180
        and -90 <= south <= 90
        and -90 <= north <= 90
        and west < east
        and south < north
    ):
        return None

    latitude = (south + north) / 2
    longitude = (west + east) / 2
    radius_km = max(
        _haversine_km(latitude, longitude, corner_latitude, corner_longitude)
        for corner_latitude in (south, north)
        for corner_longitude in (west, east)
    )
    return {
        "name": _optional_text(item.get("city") or item.get("name")),
        "formatted_address": _optional_text(item.get("formatted")),
        "latitude": round(latitude, 7),
        "longitude": round(longitude, 7),
        "radius_km": round(max(radius_km, 0.1), 2),
        "bounding_box": {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        },
        "source": "Geoapify / OpenStreetMap",
    }


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


def _optional_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _optional_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cache_key(kind, payload):
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"geoapify:{kind}:v1:{digest}"
