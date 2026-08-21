import contextvars
import json
import logging
import re
import uuid
from datetime import UTC, datetime


request_id_context = contextvars.ContextVar("request_id", default="-")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SENSITIVE_VALUE = re.compile(
    r"(?i)(authorization|password|otp|refresh(?:_token)?|access(?:_token)?|token)"
    r"(\s*[=:]\s*)([^\s,;]+)"
)


def _redact(value):
    return _SENSITIVE_VALUE.sub(r"\1\2[REDACTED]", str(value))


class RequestContextMiddleware:
    """Attach a safe correlation id without logging request bodies or tokens."""

    header_name = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get(self.header_name, "").strip()
        request_id = (
            supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        )
        request.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response = self.get_response(request)
            response.headers[self.header_name] = request_id
            return response
        finally:
            request_id_context.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": _redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = _redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)
