import base64
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import push
from .models import ClientDevice


User = get_user_model()


class FirebaseMessagingInitializationTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        push._messaging_module.cache_clear()

    def tearDown(self):
        push._messaging_module.cache_clear()
        super().tearDown()

    def firebase_modules(self, *, get_app_side_effect=None, get_app_return=None):
        firebase_admin = ModuleType("firebase_admin")
        firebase_admin.get_app = Mock(
            side_effect=get_app_side_effect,
            return_value=get_app_return,
        )
        firebase_admin.initialize_app = Mock()

        credentials = ModuleType("firebase_admin.credentials")
        credentials.Certificate = Mock()
        messaging = ModuleType("firebase_admin.messaging")
        firebase_admin.credentials = credentials
        firebase_admin.messaging = messaging
        return firebase_admin, credentials, messaging

    def encoded_service_account(self, data):
        return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")

    def test_valid_base64_initializes_firebase_once(self):
        service_account = {"type": "service_account", "project_id": "test-project"}
        encoded_account = self.encoded_service_account(service_account)
        firebase_admin, credentials, messaging = self.firebase_modules(
            get_app_side_effect=ValueError(),
        )

        with (
            override_settings(
                FIREBASE_SERVICE_ACCOUNT_BASE64=encoded_account,
                FIREBASE_SERVICE_ACCOUNT_JSON="",
            ),
            patch.dict(sys.modules, {"firebase_admin": firebase_admin}),
        ):
            first = push._messaging_module()
            second = push._messaging_module()

        self.assertIs(first, messaging)
        self.assertIs(second, messaging)
        credentials.Certificate.assert_called_once_with(service_account)
        firebase_admin.initialize_app.assert_called_once_with(
            credentials.Certificate.return_value
        )
        firebase_admin.get_app.assert_called_once_with()

    def test_existing_firebase_app_is_not_initialized_again(self):
        encoded_account = self.encoded_service_account({"project_id": "test-project"})
        firebase_admin, credentials, messaging = self.firebase_modules(
            get_app_return=object(),
        )

        with (
            override_settings(
                FIREBASE_SERVICE_ACCOUNT_BASE64=encoded_account,
                FIREBASE_SERVICE_ACCOUNT_JSON="",
            ),
            patch.dict(sys.modules, {"firebase_admin": firebase_admin}),
        ):
            result = push._messaging_module()

        self.assertIs(result, messaging)
        firebase_admin.get_app.assert_called_once_with()
        credentials.Certificate.assert_not_called()
        firebase_admin.initialize_app.assert_not_called()

    def test_legacy_json_is_used_when_base64_is_missing(self):
        service_account = {"type": "service_account", "project_id": "legacy-project"}
        firebase_admin, credentials, messaging = self.firebase_modules(
            get_app_side_effect=ValueError(),
        )

        with (
            override_settings(
                FIREBASE_SERVICE_ACCOUNT_BASE64="",
                FIREBASE_SERVICE_ACCOUNT_JSON=json.dumps(service_account),
            ),
            patch.dict(sys.modules, {"firebase_admin": firebase_admin}),
        ):
            result = push._messaging_module()

        self.assertIs(result, messaging)
        credentials.Certificate.assert_called_once_with(service_account)

    def test_base64_takes_precedence_over_legacy_json(self):
        base64_account = {"project_id": "base64-project"}
        legacy_account = {"project_id": "legacy-project"}
        firebase_admin, credentials, _ = self.firebase_modules(
            get_app_side_effect=ValueError(),
        )

        with (
            override_settings(
                FIREBASE_SERVICE_ACCOUNT_BASE64=self.encoded_service_account(
                    base64_account
                ),
                FIREBASE_SERVICE_ACCOUNT_JSON=json.dumps(legacy_account),
            ),
            patch.dict(sys.modules, {"firebase_admin": firebase_admin}),
        ):
            push._messaging_module()

        credentials.Certificate.assert_called_once_with(base64_account)

    def test_invalid_base64_raises_a_sanitized_configuration_error(self):
        with override_settings(
            FIREBASE_SERVICE_ACCOUNT_BASE64="not-valid-base64!",
            FIREBASE_SERVICE_ACCOUNT_JSON="",
        ):
            with self.assertRaisesRegex(
                push.FirebaseConfigurationError,
                "FIREBASE_SERVICE_ACCOUNT_BASE64 must be valid",
            ) as error:
                push._messaging_module()

        self.assertNotIn("not-valid-base64!", str(error.exception))

    def test_base64_with_invalid_json_raises_a_sanitized_configuration_error(self):
        encoded_invalid_json = base64.b64encode(
            b"PRIVATE_KEY_MUST_NOT_APPEAR"
        ).decode("ascii")

        with override_settings(
            FIREBASE_SERVICE_ACCOUNT_BASE64=encoded_invalid_json,
            FIREBASE_SERVICE_ACCOUNT_JSON="",
        ):
            with self.assertRaisesRegex(
                push.FirebaseConfigurationError,
                "FIREBASE_SERVICE_ACCOUNT_BASE64 must contain a valid JSON object",
            ) as error:
                push._messaging_module()

        self.assertNotIn("PRIVATE_KEY_MUST_NOT_APPEAR", str(error.exception))
        self.assertNotIn(encoded_invalid_json, str(error.exception))

    def test_missing_configuration_raises_a_clear_error(self):
        with override_settings(
            FIREBASE_SERVICE_ACCOUNT_BASE64="",
            FIREBASE_SERVICE_ACCOUNT_JSON="",
        ):
            with self.assertRaisesRegex(
                push.FirebaseConfigurationError,
                "Firebase configuration is missing",
            ):
                push._messaging_module()


class FCMTokenHandlingTests(TestCase):
    def test_invalid_fcm_token_is_deactivated_without_affecting_valid_devices(self):
        user = User.objects.create_user(
            username="fcm-token-user",
            email="fcm-token-user@example.com",
            phone="+213555900001",
            password="Password1!",
        )
        valid_device = ClientDevice.objects.create(
            user=user,
            token="valid-fcm-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        invalid_device = ClientDevice.objects.create(
            user=user,
            token="invalid-fcm-token",
            platform=ClientDevice.Platform.IOS,
            last_seen_at=timezone.now(),
        )
        invalid_token_error = type(
            "InvalidArgumentError",
            (Exception,),
            {},
        )("invalid registration token")
        messaging = Mock()
        messaging.MulticastMessage.return_value = object()
        messaging.send_each_for_multicast.return_value = SimpleNamespace(
            responses=[
                SimpleNamespace(success=True, exception=None),
                SimpleNamespace(success=False, exception=invalid_token_error),
            ]
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            stale_tokens = push._send_tokens(
                [valid_device.token, invalid_device.token],
                {"event": "account_disabled"},
            )

        valid_device.refresh_from_db()
        invalid_device.refresh_from_db()
        self.assertEqual(stale_tokens, {invalid_device.token})
        self.assertTrue(valid_device.is_active)
        self.assertFalse(invalid_device.is_active)
        messaging.send_each_for_multicast.assert_called_once()
