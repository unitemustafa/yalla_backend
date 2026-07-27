from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from config.rate_limit import RateLimitDecision

User = get_user_model()


@override_settings(
    GEOAPIFY_API_KEY="backend-secret",
    RATE_LIMIT_MODE="off",
)
class GeocodingAPITests(TestCase):
    def setUp(self):
        caches["geocoding"].clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="geo-client",
            email="geo-client@example.com",
            phone="+201000000099",
            password="Passw0rd!",
            role=User.Role.CLIENT,
        )
        self.client.force_authenticate(self.user)

    def tearDown(self):
        caches["geocoding"].clear()

    def provider_response(self, results, *, status_code=200, headers=None):
        response = Mock()
        response.status_code = status_code
        response.headers = headers or {}
        response.json.return_value = {"results": results}
        response.raise_for_status.return_value = None
        return response

    def test_geocoding_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(
            "/api/v1/locations/geocoding/reverse/",
            {"latitude": 30.0444, "longitude": 31.2357},
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_autocomplete_filters_egypt_and_normalizes_results(self):
        upstream = self.provider_response(
            [
                {
                    "place_id": "cairo-id",
                    "formatted": "القاهرة، مصر",
                    "address_line1": "القاهرة",
                    "address_line2": "مصر",
                    "lat": 30.0444,
                    "lon": 31.2357,
                    "result_type": "city",
                    "distance": 125.4,
                }
            ]
        )
        with patch("locations.geocoding.requests.get", return_value=upstream) as get:
            response = self.client.get(
                "/api/v1/locations/geocoding/autocomplete/",
                {
                    "q": "القاهرة",
                    "latitude": 30.1,
                    "longitude": 31.2,
                    "lang": "ar",
                },
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["filter"], "countrycode:eg")
        self.assertEqual(params["bias"], "proximity:31.2,30.1")
        self.assertEqual(params["lang"], "ar")
        self.assertEqual(params["limit"], 5)
        self.assertEqual(params["apiKey"], "backend-secret")
        self.assertEqual(response.data["items"][0]["place_id"], "cairo-id")
        self.assertEqual(response.data["items"][0]["distance_meters"], 125.4)

    def test_autocomplete_requires_three_characters(self):
        response = self.client.get(
            "/api/v1/locations/geocoding/autocomplete/",
            {
                "q": "ab",
                "latitude": 30,
                "longitude": 31,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_autocomplete_cache_avoids_second_provider_request(self):
        upstream = self.provider_response([])
        with patch("locations.geocoding.requests.get", return_value=upstream) as get:
            for _ in range(2):
                response = self.client.get(
                    "/api/v1/locations/geocoding/autocomplete/",
                    {
                        "q": "Cairo",
                        "latitude": 30.0444,
                        "longitude": 31.2357,
                        "lang": "en",
                    },
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"items": []})
        get.assert_called_once()

    def test_reverse_cache_rounds_coordinates_to_five_places(self):
        upstream = self.provider_response(
            [{"formatted": "Cairo, Egypt", "lat": 30.0, "lon": 31.0}]
        )
        with patch("locations.geocoding.requests.get", return_value=upstream) as get:
            first = self.client.get(
                "/api/v1/locations/geocoding/reverse/",
                {"latitude": 30.123451, "longitude": 31.123451, "lang": "en"},
            )
            second = self.client.get(
                "/api/v1/locations/geocoding/reverse/",
                {"latitude": 30.123452, "longitude": 31.123452, "lang": "en"},
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["location"]["formatted_address"], "Cairo, Egypt")
        get.assert_called_once()

    def test_reverse_returns_null_for_empty_results(self):
        with patch(
            "locations.geocoding.requests.get",
            return_value=self.provider_response([]),
        ):
            response = self.client.get(
                "/api/v1/locations/geocoding/reverse/",
                {"latitude": 30, "longitude": 31},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["location"])

    def test_provider_failure_returns_service_unavailable(self):
        with patch(
            "locations.geocoding.requests.get",
            side_effect=__import__("requests").RequestException(),
        ):
            response = self.client.get(
                "/api/v1/locations/geocoding/reverse/",
                {"latitude": 30, "longitude": 31},
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "geocoding_unavailable")

    def test_provider_rate_limit_is_not_retried(self):
        upstream = self.provider_response(
            [],
            status_code=429,
            headers={"Retry-After": "7"},
        )
        with patch("locations.geocoding.requests.get", return_value=upstream) as get:
            response = self.client.get(
                "/api/v1/locations/geocoding/reverse/",
                {"latitude": 30, "longitude": 31},
            )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response["Retry-After"], "7")
        get.assert_called_once()

    def test_global_provider_rate_limit_stops_before_upstream_call(self):
        with (
            patch(
                "locations.geocoding.evaluate_rate_limit",
                return_value=RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=1,
                    blocked_scopes=("geocoding_global",),
                ),
            ),
            patch("locations.geocoding.rate_limit_mode", return_value="enforce"),
            patch("locations.geocoding.requests.get") as get,
        ):
            response = self.client.get(
                "/api/v1/locations/geocoding/reverse/",
                {"latitude": 30.5, "longitude": 31.5},
            )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        get.assert_not_called()

    def test_city_coverage_lookup_requires_admin(self):
        response = self.client.get(
            "/api/v1/locations/service-cities/coverage-lookup/",
            {"q": "القاهرة"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_city_coverage_lookup_calculates_circle_from_bbox(self):
        self.user.role = User.Role.ADMIN
        self.user.save(update_fields=("role",))
        upstream = self.provider_response(
            [
                {
                    "city": "القاهرة",
                    "formatted": "القاهرة، مصر",
                    "country_code": "eg",
                    "result_type": "city",
                    "lat": 30.0444,
                    "lon": 31.2357,
                    "bbox": {
                        "lon1": 30.5,
                        "lat1": 29.5,
                        "lon2": 31.5,
                        "lat2": 30.5,
                    },
                }
            ]
        )
        with patch("locations.geocoding.requests.get", return_value=upstream) as get:
            response = self.client.get(
                "/api/v1/locations/service-cities/coverage-lookup/",
                {"q": "القاهرة", "lang": "ar"},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        coverage = response.data["coverage"]
        self.assertEqual(coverage["latitude"], 30.0)
        self.assertEqual(coverage["longitude"], 31.0)
        self.assertGreater(coverage["radius_km"], 70)
        self.assertLess(coverage["radius_km"], 75)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["type"], "city")
        self.assertEqual(params["filter"], "countrycode:eg")
        self.assertEqual(params["format"], "json")
        self.assertEqual(params["limit"], 5)
        self.assertEqual(params["apiKey"], "backend-secret")

    def test_admin_city_coverage_lookup_returns_not_found_without_bbox(self):
        self.user.role = User.Role.ADMIN
        self.user.save(update_fields=("role",))
        upstream = self.provider_response(
            [{"city": "Unknown", "lat": 30.0, "lon": 31.0}]
        )
        with patch("locations.geocoding.requests.get", return_value=upstream):
            response = self.client.get(
                "/api/v1/locations/service-cities/coverage-lookup/",
                {"q": "Unknown"},
            )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "city_not_found")
