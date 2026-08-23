import os

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

    ready = all(checks.values())
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )
