import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError

from tools.performance.auth_probe import persist_session, request


class AuthProbeTests(unittest.TestCase):
    def test_rotated_session_updates_only_the_sampled_private_fixture(self):
        first, reserved = (
            {"access": "old", "refresh": "old"},
            {"access": "reserved", "refresh": "reserved"},
        )
        manifest = {"accounts": [first, reserved]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.private.json"
            persist_session(
                path,
                manifest,
                first,
                {"accessToken": "new-access", "refreshToken": "new-refresh"},
            )
            stored = json.loads(path.read_text())
        self.assertEqual(stored["accounts"][0]["access"], "new-access")
        self.assertEqual(stored["accounts"][1], reserved)

    def test_external_target_and_endpoint_are_rejected_before_io(self):
        opener = MagicMock()
        for base, endpoint in [
            ("https://example.com", "/api/v1/auth/login/client"),
            ("http://127.0.0.1:18081", "@example.com"),
        ]:
            with self.assertRaises(ValueError):
                request(opener, base, endpoint, {})
        opener.open.assert_not_called()

    def test_success_exports_no_credentials_or_token_body(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = (
            b'{"accessToken":"secret-access","refreshToken":"secret-refresh"}'
        )
        data, row = request(
            opener,
            "http://127.0.0.1:18081",
            "/api/v1/auth/login/client",
            {"password": "secret-password"},
        )
        self.assertTrue(row["valid"])
        self.assertEqual(data["accessToken"], "secret-access")
        self.assertNotIn("secret", json.dumps(row))

    def test_rate_limit_is_recorded_without_response_body(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError(
            "http://127.0.0.1:18081",
            429,
            "limit",
            {},
            BytesIO(b'{"detail":"secret-private-body"}'),
        )
        _, row = request(
            opener, "http://127.0.0.1:18081", "/api/v1/auth/login/client", {}
        )
        self.assertEqual(row["status"], 429)
        self.assertFalse(row["valid"])
        self.assertNotIn("secret", json.dumps(row))


if __name__ == "__main__":
    unittest.main()
