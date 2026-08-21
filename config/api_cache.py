import hashlib
import json
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException

from accounts.authentication import DatabaseStateJWTAuthentication


CATALOG_VERSION_KEY = "api-cache:catalog-version"
USER_VERSION_KEY = "api-cache:user-version:{user_id}"
CACHEABLE_PREFIXES = (
    "/api/v1/catalog/",
    "/api/v2/catalog/",
    "/api/v1/home/",
    "/api/v2/home/",
    "/api/v1/offers/",
    "/api/v2/offers/",
)
PUBLIC_CACHEABLE_SUFFIXES = ("/home/login-dashboard-snapshot/",)
INVALIDATING_APPS = frozenset(
    {"catalog", "dashboard", "locations", "markets", "offers"}
)
STORED_HEADERS = (
    "Content-Language",
    "Content-Type",
    "ETag",
    "Last-Modified",
)


def _version(key):
    value = cache.get(key)
    if value is not None:
        return value
    value = uuid4().hex
    cache.add(key, value, timeout=None)
    return cache.get(key) or value


def _increment(key):
    cache.set(key, uuid4().hex, timeout=None)


def bump_catalog_cache_version():
    _increment(CATALOG_VERSION_KEY)


def bump_user_cache_version(user_id):
    if user_id:
        _increment(USER_VERSION_KEY.format(user_id=user_id))


def _is_cacheable_path(path):
    return path.startswith(CACHEABLE_PREFIXES)


def _is_public_cacheable_path(path):
    return path.endswith(PUBLIC_CACHEABLE_SUFFIXES)


def _cache_timeout(path):
    if path.endswith("/home/login-dashboard-snapshot/"):
        return settings.API_LOGIN_SNAPSHOT_CACHE_TIMEOUT
    return settings.API_CATALOG_CACHE_TIMEOUT


def _cache_key(request, user):
    user_id = user.pk if user is not None else "anonymous"
    role = user.role if user is not None else "anonymous"
    region = (
        f"{user.market_region_mode}:{user.market_region_service_city_id}"
        if user is not None
        else "public"
    )
    user_version = (
        _version(USER_VERSION_KEY.format(user_id=user_id))
        if user is not None
        else 1
    )
    material = "|".join(
        (
            request.get_host(),
            request.get_full_path(),
            request.headers.get("Accept-Language", ""),
            str(user_id),
            role,
            region,
            str(_version(CATALOG_VERSION_KEY)),
            str(user_version),
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"api-cache:response:{digest}"


class ApiResponseCacheMiddleware:
    """Short, user-scoped caching for catalog GET responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not settings.API_CACHE_ENABLED
            or not _is_cacheable_path(request.path_info)
        ):
            return self.get_response(request)

        if request.method != "GET":
            response = self.get_response(request)
            if (
                request.method not in {"HEAD", "OPTIONS"}
                and 200 <= response.status_code < 400
            ):
                bump_catalog_cache_version()
            return response

        user = None
        if not _is_public_cacheable_path(request.path_info):
            try:
                auth_result = DatabaseStateJWTAuthentication().authenticate(
                    request
                )
            except APIException:
                auth_result = None
            if auth_result is None:
                return self.get_response(request)
            user, _ = auth_result
            request._yalla_auth_result = auth_result
            request.user = user

        key = _cache_key(request, user)
        cached = cache.get(key)
        if cached is not None:
            response = HttpResponse(
                content=cached["content"],
                status=cached["status"],
            )
            for name, value in cached["headers"].items():
                response[name] = value
            patch_vary_headers(response, ("Authorization", "Accept-Language"))
            response["Cache-Control"] = "private, max-age=0"
            if settings.API_CACHE_OBSERVABILITY:
                response["X-Yalla-Cache"] = "HIT"
            return response

        response = self.get_response(request)
        if self._can_store(response):
            cache.set(
                key,
                {
                    "content": bytes(response.content),
                    "status": response.status_code,
                    "headers": {
                        name: response[name]
                        for name in STORED_HEADERS
                        if name in response
                    },
                },
                timeout=_cache_timeout(request.path_info),
            )
        patch_vary_headers(response, ("Authorization", "Accept-Language"))
        response["Cache-Control"] = "private, max-age=0"
        if settings.API_CACHE_OBSERVABILITY:
            response["X-Yalla-Cache"] = "MISS"
        return response

    @staticmethod
    def _can_store(response):
        if response.status_code != 200 or getattr(response, "streaming", False):
            return False
        content_type = response.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            return False
        try:
            json.loads(response.content)
        except (TypeError, ValueError):
            return False
        return "no-store" not in response.get("Cache-Control", "").lower()


def _invalidate_catalog(sender, **kwargs):
    if sender._meta.app_label in INVALIDATING_APPS:
        bump_catalog_cache_version()


def _invalidate_personalized_m2m(
    sender,
    instance,
    action,
    pk_set,
    reverse,
    **kwargs,
):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    model_name = sender._meta.model_name
    if model_name not in {"product_liked_by", "market_liked_by"}:
        if sender._meta.app_label in INVALIDATING_APPS:
            bump_catalog_cache_version()
        return
    if action == "post_clear":
        bump_catalog_cache_version()
        return
    user_ids = {instance.pk} if reverse else set(pk_set or ())
    for user_id in user_ids:
        bump_user_cache_version(user_id)


def _invalidate_user_region(sender, instance, created, update_fields, **kwargs):
    if created or update_fields is None or {
        "market_region_mode",
        "market_region_service_city",
        "market_region_service_city_id",
    }.intersection(update_fields):
        bump_user_cache_version(instance.pk)


def register_api_cache_signals():
    from accounts.models import User

    post_save.connect(
        _invalidate_catalog,
        dispatch_uid="api-cache-catalog-save",
        weak=False,
    )
    post_delete.connect(
        _invalidate_catalog,
        dispatch_uid="api-cache-catalog-delete",
        weak=False,
    )
    m2m_changed.connect(
        _invalidate_personalized_m2m,
        dispatch_uid="api-cache-personalized-m2m",
        weak=False,
    )
    post_save.connect(
        _invalidate_user_region,
        sender=User,
        dispatch_uid="api-cache-user-region",
        weak=False,
    )
