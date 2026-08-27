from pathlib import Path

from django.test import SimpleTestCase


BASE_DIR = Path(__file__).resolve().parent.parent
NGINX_TEMPLATE = BASE_DIR / "deploy" / "nginx" / "default.conf.template"
COMPOSE_FILE = BASE_DIR / "compose.yaml"


class NginxProtectedMediaTests(SimpleTestCase):
    def test_nginx_is_recreated_for_each_deployment_revision(self):
        configuration = COMPOSE_FILE.read_text(encoding="utf-8")
        nginx_service = configuration.split("  nginx:", maxsplit=1)[1].split(
            "  django:",
            maxsplit=1,
        )[0]

        self.assertIn(
            "DEPLOYMENT_REVISION: ${DEPLOYMENT_REVISION:-unknown}",
            nginx_service,
        )

    def test_protected_media_preserves_djangos_validated_cors_origin(self):
        configuration = NGINX_TEMPLATE.read_text(encoding="utf-8")
        protected_media_location = configuration.split(
            "location /_protected-media/ {",
            maxsplit=1,
        )[1].split("}", maxsplit=1)[0]

        self.assertIn("internal;", protected_media_location)
        self.assertIn(
            "set $protected_media_cors_origin "
            "$upstream_http_access_control_allow_origin;",
            protected_media_location,
        )
        self.assertIn(
            "add_header Access-Control-Allow-Origin "
            "$protected_media_cors_origin always;",
            protected_media_location,
        )
        self.assertIn('add_header Vary "Origin" always;', protected_media_location)
