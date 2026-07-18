import math

from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None or not isinstance(exc, Throttled):
        return response

    retry_after = max(1, math.ceil(exc.wait or 1))
    response.data = {
        "code": "rate_limited",
        "detail": "Too many requests. Try again later.",
        "retry_after_seconds": retry_after,
    }
    response.headers["Retry-After"] = str(retry_after)
    return response
