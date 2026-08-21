import os

from django.conf import settings
from django.core.cache import caches
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def liveness(request):
    return JsonResponse(
        {
            "status": "ok",
            "deployment_revision": os.environ.get(
                "DEPLOYMENT_REVISION",
                "unknown",
            ),
        }
    )


@require_safe
def readiness(request):
    checks = {"database": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True
    except Exception:
        pass

    redis_required = bool(settings.RATE_LIMIT_REDIS_URL)
    if redis_required:
        checks["rate_limit_redis"] = False
        try:
            cache = caches["rate_limit"]
            cache.set("readiness", "ok", timeout=5)
            checks["rate_limit_redis"] = cache.get("readiness") == "ok"
        except Exception:
            pass

    if settings.CACHE_REDIS_URL:
        checks["cache_redis"] = False
        try:
            cache = caches["default"]
            cache.set("readiness", "ok", timeout=5)
            checks["cache_redis"] = cache.get("readiness") == "ok"
        except Exception:
            pass

    ready = all(checks.values())
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )
