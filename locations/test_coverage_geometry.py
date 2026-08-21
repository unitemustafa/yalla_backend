from types import SimpleNamespace

from django.test import TestCase

from .coverage import (
    _point_in_bbox,
    _point_in_geojson,
    contains_point,
    coverage_is_configured,
    matching_delivery_area,
)
from .models import DeliveryArea, ServiceCity


SQUARE = [
    [
        [30.0, 29.0],
        [32.0, 29.0],
        [32.0, 31.0],
        [30.0, 31.0],
        [30.0, 29.0],
    ]
]


class CoverageGeometryTests(TestCase):
    def test_legacy_scope_without_geometry_remains_usable(self):
        scope = SimpleNamespace(
            boundary_geojson=None,
            boundary_bbox=None,
            center_latitude=None,
            center_longitude=None,
            radius_km=None,
        )
        self.assertFalse(coverage_is_configured(scope))
        self.assertTrue(contains_point(scope, latitude=30, longitude=31))

    def test_radius_accepts_nearby_and_rejects_far_points(self):
        scope = SimpleNamespace(
            boundary_geojson=None,
            boundary_bbox=None,
            center_latitude=30,
            center_longitude=31,
            radius_km=5,
        )
        self.assertTrue(coverage_is_configured(scope))
        self.assertTrue(contains_point(scope, latitude=30.01, longitude=31.01))
        self.assertFalse(contains_point(scope, latitude=31, longitude=32))

    def test_bbox_supports_dict_and_list_and_fails_safely(self):
        self.assertTrue(_point_in_bbox(30, 31, [30, 29, 32, 31]))
        self.assertTrue(
            _point_in_bbox(
                30,
                31,
                {"west": 30, "south": 29, "east": 32, "north": 31},
            )
        )
        self.assertTrue(_point_in_bbox(30, 31, {"broken": True}))
        scope = SimpleNamespace(
            boundary_geojson=None,
            boundary_bbox=[30, 29, 32, 31],
            center_latitude=None,
            center_longitude=None,
            radius_km=None,
        )
        self.assertFalse(contains_point(scope, latitude=40, longitude=40))

    def test_geojson_feature_collection_and_multipolygon(self):
        feature = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": SQUARE},
        }
        collection = {"type": "FeatureCollection", "features": [feature]}
        multi = {"type": "MultiPolygon", "coordinates": [SQUARE]}
        self.assertTrue(_point_in_geojson(30, 31, collection))
        self.assertTrue(_point_in_geojson(30, 31, multi))
        self.assertIsNone(_point_in_geojson(30, 31, "invalid"))
        self.assertIsNone(
            _point_in_geojson(30, 31, {"type": "Point", "coordinates": []})
        )

    def test_polygon_hole_excludes_point(self):
        hole = [
            [30.5, 29.5],
            [31.5, 29.5],
            [31.5, 30.5],
            [30.5, 30.5],
            [30.5, 29.5],
        ]
        polygon = {"type": "Polygon", "coordinates": [SQUARE[0], hole]}
        self.assertFalse(_point_in_geojson(30, 31, polygon))
        self.assertTrue(_point_in_geojson(29.25, 30.25, polygon))

    def test_known_cairo_city_cap_rejects_distant_coordinates(self):
        scope = SimpleNamespace(
            name="Cairo",
            slug="cairo",
            delivery_areas=object(),
            boundary_geojson=None,
            boundary_bbox=None,
            center_latitude=None,
            center_longitude=None,
            radius_km=None,
        )
        self.assertTrue(contains_point(scope, latitude=30.0444, longitude=31.2357))
        self.assertFalse(contains_point(scope, latitude=31.2, longitude=29.9))

    def test_matching_delivery_area_uses_only_active_unarchived_geometry(self):
        city = ServiceCity.objects.create(name="Geometry City")
        expected = DeliveryArea.objects.create(
            service_city=city,
            name="Center",
            delivery_price=10,
            center_latitude=30,
            center_longitude=31,
            radius_km=5,
        )
        DeliveryArea.objects.create(
            service_city=city,
            name="Inactive",
            delivery_price=10,
            center_latitude=30,
            center_longitude=31,
            radius_km=5,
            is_active=False,
        )
        self.assertEqual(
            matching_delivery_area(city, latitude=30.01, longitude=31.01),
            expected,
        )

