import json
import logging

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from .observability import JsonFormatter, RequestContextMiddleware


class RequestContextMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = RequestContextMiddleware(
            lambda request: JsonResponse({"request_id": request.request_id})
        )

    def test_preserves_a_safe_caller_request_id(self):
        response = self.middleware(
            self.factory.get("/health/", HTTP_X_REQUEST_ID="mobile-123")
        )

        self.assertEqual(response.headers["X-Request-ID"], "mobile-123")
        self.assertEqual(json.loads(response.content)["request_id"], "mobile-123")

    def test_replaces_unsafe_request_id(self):
        response = self.middleware(
            self.factory.get("/health/", HTTP_X_REQUEST_ID="bad\nheader")
        )

        self.assertNotEqual(response.headers["X-Request-ID"], "bad\nheader")
        self.assertEqual(len(response.headers["X-Request-ID"]), 32)

    def test_json_logs_redact_common_credentials(self):
        record = logging.LogRecord(
            "security",
            logging.WARNING,
            __file__,
            1,
            "password=secret token:abc otp=123456",
            (),
            None,
        )

        payload = json.loads(JsonFormatter().format(record))

        self.assertNotIn("secret", payload["message"])
        self.assertNotIn("abc", payload["message"])
        self.assertNotIn("123456", payload["message"])

