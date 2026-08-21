from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from .api_cache import ApiResponseCacheMiddleware, bump_user_cache_version


@override_settings(
    API_CACHE_ENABLED=True,
    API_CACHE_OBSERVABILITY=True,
    API_CATALOG_CACHE_TIMEOUT=60,
    API_LOGIN_SNAPSHOT_CACHE_TIMEOUT=30,
)
class ApiResponseCacheMiddlewareTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def test_public_login_snapshot_reports_miss_then_hit(self):
        calls = []

        def response(request):
            calls.append(request.path)
            return JsonResponse({"value": len(calls)})

        middleware = ApiResponseCacheMiddleware(response)
        path = "/api/v2/home/login-dashboard-snapshot/"

        first = middleware(self.factory.get(path))
        second = middleware(self.factory.get(path))

        self.assertEqual(first["X-Yalla-Cache"], "MISS")
        self.assertEqual(second["X-Yalla-Cache"], "HIT")
        self.assertEqual(len(calls), 1)

    @patch("config.api_cache.DatabaseStateJWTAuthentication.authenticate")
    def test_authenticated_cache_is_user_scoped_and_versioned(self, authenticate):
        calls = []

        def response(request):
            calls.append(request.user.pk)
            return JsonResponse({"user": request.user.pk, "call": len(calls)})

        middleware = ApiResponseCacheMiddleware(response)
        path = "/api/v2/home/"
        first_user = SimpleNamespace(
            pk=11,
            role="client",
            market_region_mode="general",
            market_region_service_city_id=None,
        )
        second_user = SimpleNamespace(
            pk=12,
            role="client",
            market_region_mode="general",
            market_region_service_city_id=None,
        )

        authenticate.return_value = (first_user, object())
        first = middleware(self.factory.get(path, HTTP_AUTHORIZATION="Bearer one"))
        hit = middleware(self.factory.get(path, HTTP_AUTHORIZATION="Bearer one"))
        authenticate.return_value = (second_user, object())
        other = middleware(self.factory.get(path, HTTP_AUTHORIZATION="Bearer two"))
        bump_user_cache_version(first_user.pk)
        authenticate.return_value = (first_user, object())
        invalidated = middleware(
            self.factory.get(path, HTTP_AUTHORIZATION="Bearer one")
        )

        self.assertEqual(first["X-Yalla-Cache"], "MISS")
        self.assertEqual(hit["X-Yalla-Cache"], "HIT")
        self.assertEqual(other["X-Yalla-Cache"], "MISS")
        self.assertEqual(invalidated["X-Yalla-Cache"], "MISS")
        self.assertEqual(calls, [11, 12, 11])
