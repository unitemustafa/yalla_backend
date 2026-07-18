from unittest.mock import Mock, patch
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, override_settings
from redis.exceptions import ConnectionError, NoScriptError
from rest_framework.exceptions import Throttled
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from .api_exceptions import api_exception_handler
from . import rate_limit
from .rate_limit_checks import check_rate_limit_configuration
from .rate_limit import (
    RateLimitDecision,
    RateRule,
    YallaRateThrottle,
    client_ip,
    evaluate_rate_limit,
    is_rate_limit_exempt,
    parse_rate,
)


@override_settings(
    RATE_LIMIT_CLIENT_IP_HEADER="",
    RATE_LIMIT_REDIS_URL="redis://rate-limit.test.invalid/1",
)
class RateLimitSystemCheckTests(SimpleTestCase):
    def _check_ids(self):
        return {
            message.id
            for message in check_rate_limit_configuration(None)
        }

    @override_settings(
        RATE_LIMIT_MODE="off",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="django-test-secret",
    )
    def test_off_allows_the_default_secret_fallback(self):
        self.assertNotIn("rate_limit.E007", self._check_ids())

    @override_settings(
        RATE_LIMIT_MODE="observe",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="",
    )
    def test_observe_rejects_an_empty_rate_limit_secret(self):
        self.assertIn("rate_limit.E007", self._check_ids())

    @override_settings(
        RATE_LIMIT_MODE="observe",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="django-test-secret",
    )
    def test_observe_rejects_the_django_secret_key_fallback(self):
        self.assertIn("rate_limit.E007", self._check_ids())

    @override_settings(
        RATE_LIMIT_MODE="enforce",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="",
    )
    def test_enforce_rejects_an_empty_rate_limit_secret(self):
        self.assertIn("rate_limit.E007", self._check_ids())

    @override_settings(
        RATE_LIMIT_MODE="enforce",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="django-test-secret",
    )
    def test_enforce_rejects_the_django_secret_key_fallback(self):
        self.assertIn("rate_limit.E007", self._check_ids())

    @override_settings(
        RATE_LIMIT_MODE="observe",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="independent-test-rate-limit-secret",
    )
    def test_observe_accepts_an_independent_rate_limit_secret(self):
        self.assertNotIn("rate_limit.E007", self._check_ids())

    @override_settings(
        RATE_LIMIT_MODE="enforce",
        SECRET_KEY="django-test-secret",
        RATE_LIMIT_KEY_SECRET="independent-test-rate-limit-secret",
    )
    def test_enforce_accepts_an_independent_rate_limit_secret(self):
        self.assertNotIn("rate_limit.E007", self._check_ids())


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        RATE_LIMIT_CLIENT_IP_HEADER="DO-Connecting-IP",
        RATE_LIMIT_TRUSTED_PROXY_CIDRS=(),
    )
    def test_spoofed_header_is_ignored_without_a_trusted_proxy(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.10",
            HTTP_DO_CONNECTING_IP="203.0.113.20",
        )
        self.assertEqual(client_ip(request), "198.51.100.10")

    @override_settings(
        RATE_LIMIT_CLIENT_IP_HEADER="X-Forwarded-For",
        RATE_LIMIT_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
    )
    def test_trusted_proxy_chain_selects_the_first_untrusted_address(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.0.0.3",
            HTTP_X_FORWARDED_FOR="203.0.113.20, 10.0.0.2",
        )
        self.assertEqual(client_ip(request), "203.0.113.20")

    @override_settings(
        RATE_LIMIT_CLIENT_IP_HEADER="X-Forwarded-For",
        RATE_LIMIT_TRUSTED_PROXY_CIDRS=("2001:db8:1::/48",),
    )
    def test_ipv6_proxy_and_client_are_supported(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="2001:db8:1::2",
            HTTP_X_FORWARDED_FOR="2001:db8:2::9",
        )
        self.assertEqual(client_ip(request), "2001:db8:2::9")


class RateLimitCoreTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        rate_limit._script_sha = None

    def tearDown(self):
        rate_limit._script_sha = None

    def test_rate_parser_supports_multi_unit_windows(self):
        self.assertEqual(parse_rate("5/5m"), (5, 300_000))
        self.assertEqual(parse_rate("3/1d"), (3, 86_400_000))
        with self.assertRaises(ValueError):
            parse_rate("5/minute")

    def test_identifier_normalization_and_token_case_sensitivity(self):
        self.assertEqual(
            rate_limit._normalize_identifier("0100 123-4567"),
            "+201001234567",
        )
        self.assertEqual(
            rate_limit._normalize_identifier(" USER@Example.COM "),
            "user@example.com",
        )
        self.assertNotEqual(
            rate_limit._fingerprint("token", "AbC"),
            rate_limit._fingerprint("token", "abc"),
        )

    @override_settings(
        RATE_LIMIT_MODE="enforce",
        RATE_LIMIT_POLICY_RATES={
            "api_anon": ("2/1m",),
            "login_ip": ("1/1m",),
            "login_identifier": ("1/1m",),
        },
        RATE_LIMIT_TRUSTED_PROXY_CIDRS=(),
    )
    @patch("config.rate_limit._record_blocked_telemetry")
    @patch("config.rate_limit._execute_script")
    @patch("config.rate_limit._redis_client")
    def test_longest_wait_and_failed_scopes_are_returned(
        self, redis_client, execute_script, record_telemetry
    ):
        raw_request = self.factory.post(
            "/api/v1/auth/login/client/",
            {"identifier": "User@Example.com", "password": "secret"},
            format="json",
            REMOTE_ADDR="198.51.100.10",
        )
        request = Request(raw_request, parsers=[JSONParser()])
        request.user = AnonymousUser()
        client = redis_client.return_value
        # api_anon, login_ip, login_identifier; first and third failed.
        execute_script.return_value = [0, 42_001, 2, 1, 3]

        decision = evaluate_rate_limit(
            request,
            ("api_anon", "login_ip", "login_identifier"),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.retry_after_seconds, 43)
        self.assertEqual(
            decision.blocked_scopes,
            ("api_anon", "login_identifier"),
        )
        record_telemetry.assert_called_once_with(
            client,
            "enforce",
            ("api_anon", "login_identifier"),
        )

    @override_settings(
        RATE_LIMIT_MODE="enforce",
        RATE_LIMIT_POLICY_RATES={"api_anon": ("2/1m",)},
        RATE_LIMIT_TRUSTED_PROXY_CIDRS=(),
    )
    @patch("config.rate_limit._execute_script")
    @patch("config.rate_limit._redis_client")
    def test_redis_connection_errors_fail_open(
        self, redis_client, execute_script
    ):
        request = self.factory.get("/api/v1/test/", REMOTE_ADDR="127.0.0.1")
        request.user = AnonymousUser()
        execute_script.side_effect = ConnectionError("offline")

        decision = evaluate_rate_limit(request, ("api_anon",))

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.backend_error)
        redis_client.assert_called_once_with()

    @override_settings(
        RATE_LIMIT_MODE="enforce",
        RATE_LIMIT_ENFORCE_SCOPES=("login_ip",),
        RATE_LIMIT_POLICY_RATES={
            "api_anon": ("2/1m",),
            "login_ip": ("1/1m",),
        },
        RATE_LIMIT_TRUSTED_PROXY_CIDRS=(),
    )
    @patch("config.rate_limit._execute_script", return_value=[1, 0, 0])
    @patch("config.rate_limit._redis_client")
    def test_enforce_scope_allowlist_supports_staged_rollout(
        self, redis_client, execute_script
    ):
        request = self.factory.get("/api/v1/test/", REMOTE_ADDR="127.0.0.1")
        request.user = AnonymousUser()

        evaluate_rate_limit(request, ("api_anon", "login_ip"))

        rules = execute_script.call_args.args[1]
        self.assertEqual([rule.scope for rule in rules], ["login_ip"])

    def test_evalsha_reloads_once_after_noscript(self):
        client = Mock()
        client.script_load.side_effect = ["first-sha", "second-sha"]
        client.evalsha.side_effect = [NoScriptError(), [1, 0, 0]]
        rules = (
            RateRule("api_anon", "fixed", 2, 60_000, "test-key"),
        )

        result = rate_limit._execute_script(client, rules)

        self.assertEqual(result, [1, 0, 0])
        self.assertEqual(client.script_load.call_count, 2)
        self.assertEqual(client.evalsha.call_count, 2)

    @override_settings(
        RATE_LIMIT_EXEMPT_PATHS=("/health/",),
    )
    def test_options_and_health_checks_are_exempt(self):
        options_request = self.factory.options("/api/v1/test/")
        health_request = self.factory.get("/health/")
        self.assertTrue(is_rate_limit_exempt(options_request))
        self.assertTrue(is_rate_limit_exempt(health_request))

    @override_settings(RATE_LIMIT_MODE="observe")
    @patch("config.rate_limit.evaluate_rate_limit")
    def test_observe_mode_never_blocks_the_request(self, evaluate):
        evaluate.return_value = RateLimitDecision(
            allowed=False,
            retry_after_seconds=10,
            blocked_scopes=("api_anon",),
        )
        request = self.factory.get("/api/v1/test/")
        request.user = AnonymousUser()

        view = SimpleNamespace(rate_limit_scopes=())
        self.assertTrue(YallaRateThrottle().allow_request(request, view))


class RateLimitResponseTests(SimpleTestCase):
    def test_throttled_exception_uses_the_public_429_contract(self):
        response = api_exception_handler(Throttled(wait=4.2), {})

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "rate_limited")
        self.assertEqual(response.data["retry_after_seconds"], 5)
        self.assertEqual(response.headers["Retry-After"], "5")
