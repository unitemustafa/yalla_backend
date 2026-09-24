import os

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe

from .redis_client import check_redis_health


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
    checks = {"database": False, "redis": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True
    except Exception:
        pass

    redis_ok, _, _ = check_redis_health("cache")
    checks["redis"] = redis_ok

    ready = all(checks.values())
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )
