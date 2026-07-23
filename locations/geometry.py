from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity


EGYPT_BOUNDS = (22.0, 21.5, 37.0, 31.8)
ALLOWED_CITY_GEOMETRIES = {"Polygon", "MultiPolygon"}
ALLOWED_AREA_GEOMETRIES = {"Polygon"}


class GeometryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedGeometry:
    geojson: dict[str, Any]
    bbox: list[float]
    center_latitude: Decimal
    center_longitude: Decimal
    geometry: BaseGeometry


def parse_geometry(
    value: Any,
    *,
    allowed_types: set[str],
    field_name: str = "boundary_geojson",
) -> BaseGeometry:
    if not isinstance(value, dict):
        raise GeometryValidationError(f"{field_name} must be a GeoJSON object.")
    geometry_type = value.get("type")
    if geometry_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        raise GeometryValidationError(
            f"{field_name} must have one of these geometry types: {allowed}."
        )
    try:
        geometry = shape(value)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise GeometryValidationError(f"{field_name} is not valid GeoJSON.") from exc
    if geometry.is_empty:
        raise GeometryValidationError(f"{field_name} cannot be empty.")
    if not geometry.is_valid:
        raise GeometryValidationError(
            f"{field_name} is invalid: {explain_validity(geometry)}."
        )
    min_x, min_y, max_x, max_y = geometry.bounds
    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise GeometryValidationError(
            f"{field_name} contains coordinates outside WGS84 bounds."
        )
    return geometry


def normalize_geometry(
    value: Any,
    *,
    allowed_types: set[str],
    field_name: str = "boundary_geojson",
) -> NormalizedGeometry:
    geometry = parse_geometry(
        value,
        allowed_types=allowed_types,
        field_name=field_name,
    )
    min_x, min_y, max_x, max_y = geometry.bounds
    center = geometry.representative_point()
    return NormalizedGeometry(
        geojson=mapping(geometry),
        bbox=[min_x, min_y, max_x, max_y],
        center_latitude=Decimal(str(center.y)).quantize(Decimal("0.0000001")),
        center_longitude=Decimal(str(center.x)).quantize(Decimal("0.0000001")),
        geometry=geometry,
    )


def geometry_covers_point(value: Any, latitude: Any, longitude: Any) -> bool:
    geometry = parse_geometry(
        value,
        allowed_types=ALLOWED_CITY_GEOMETRIES,
    )
    return geometry.covers(Point(float(longitude), float(latitude)))


def geometry_covers_geometry(container: Any, candidate: Any) -> bool:
    container_geometry = parse_geometry(
        container,
        allowed_types=ALLOWED_CITY_GEOMETRIES,
    )
    candidate_geometry = parse_geometry(
        candidate,
        allowed_types=ALLOWED_CITY_GEOMETRIES,
    )
    return container_geometry.covers(candidate_geometry)


def geometries_have_forbidden_overlap(first: Any, second: Any) -> bool:
    first_geometry = parse_geometry(
        first,
        allowed_types=ALLOWED_CITY_GEOMETRIES,
    )
    second_geometry = parse_geometry(
        second,
        allowed_types=ALLOWED_CITY_GEOMETRIES,
    )
    intersection = first_geometry.intersection(second_geometry)
    return not intersection.is_empty and intersection.area > 0


def point_within_egypt_bounds(latitude: Any, longitude: Any) -> bool:
    west, south, east, north = EGYPT_BOUNDS
    lat = float(latitude)
    lng = float(longitude)
    return south <= lat <= north and west <= lng <= east
