import json

from django.test import RequestFactory, SimpleTestCase, override_settings

from .request_limits import RequestBodyLimitMiddleware


@override_settings(
    API_MAX_REQUEST_BODY_SIZE=100,
    API_SINGLE_UPLOAD_REQUEST_SIZE=200,
    API_PRODUCT_UPLOAD_REQUEST_SIZE=300,
)
class RequestBodyLimitMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = RequestBodyLimitMiddleware(
            lambda request: None
        )

    def test_rejects_oversized_json_before_body_parsing(self):
        request = self.factory.post(
            "/api/v1/orders/preview/",
            data=b"{}",
            content_type="application/json",
        )
        request.META["CONTENT_LENGTH"] = "101"

        response = self.middleware(request)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            json.loads(response.content)["code"],
            "request_too_large",
        )

    def test_product_multipart_uses_the_larger_explicit_limit(self):
        request = self.factory.post(
            "/api/v1/catalog/products/1/images/",
            data={},
        )
        request.META["CONTENT_TYPE"] = "multipart/form-data; boundary=test"
        request.META["CONTENT_LENGTH"] = "250"

        self.assertIsNone(self.middleware(request))

    def test_v2_product_multipart_uses_the_same_larger_limit(self):
        request = self.factory.post(
            "/api/v2/catalog/products/1/images/",
            data={},
        )
        request.META["CONTENT_TYPE"] = "multipart/form-data; boundary=test"
        request.META["CONTENT_LENGTH"] = "250"

        self.assertIsNone(self.middleware(request))

    def test_other_multipart_routes_use_the_single_upload_limit(self):
        request = self.factory.post(
            "/api/v1/offers/1/image/",
            data={},
        )
        request.META["CONTENT_TYPE"] = "multipart/form-data; boundary=test"
        request.META["CONTENT_LENGTH"] = "201"

        response = self.middleware(request)

        self.assertEqual(response.status_code, 413)
