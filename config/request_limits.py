from django.conf import settings
from django.http import JsonResponse


MULTIPART_CONTENT_TYPES = (
    "multipart/form-data",
    "application/x-www-form-urlencoded",
)


class RequestBodyLimitMiddleware:
    """Reject declared oversized request bodies before Django parses them."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = self._limit_for_request(request)
        content_length = self._content_length(request)
        if content_length is not None and content_length > limit:
            return JsonResponse(
                {
                    "code": "request_too_large",
                    "detail": "Request body is too large.",
                    "max_bytes": limit,
                },
                status=413,
            )
        return self.get_response(request)

    @staticmethod
    def _content_length(request):
        raw_value = request.META.get("CONTENT_LENGTH")
        if raw_value in (None, ""):
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        return max(0, value)

    @staticmethod
    def _limit_for_request(request):
        content_type = (request.META.get("CONTENT_TYPE") or "").lower()
        is_multipart = content_type.startswith(MULTIPART_CONTENT_TYPES)
        if not is_multipart:
            return settings.API_MAX_REQUEST_BODY_SIZE

        path = request.path_info.rstrip("/") + "/"
        if path.startswith((
            "/api/v1/catalog/products/",
            "/api/v2/catalog/products/",
        )):
            return settings.API_PRODUCT_UPLOAD_REQUEST_SIZE
        return settings.API_SINGLE_UPLOAD_REQUEST_SIZE
