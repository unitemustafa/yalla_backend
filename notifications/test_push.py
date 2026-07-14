import base64
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import push
from .models import ClientDevice, Notification


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
    def test_multicast_delivery_is_split_at_five_hundred_devices(self):
        tokens = [f"batch-token-{index}" for index in range(501)]
        messaging = Mock()
        messaging.MulticastMessage.side_effect = (
            lambda **kwargs: SimpleNamespace(**kwargs)
        )
        messaging.Notification.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.AndroidConfig.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.AndroidNotification.side_effect = (
            lambda **kwargs: SimpleNamespace(**kwargs)
        )
        messaging.APNSConfig.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.APNSPayload.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.Aps.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.send_each_for_multicast.side_effect = lambda message: SimpleNamespace(
            responses=[
                SimpleNamespace(success=True, exception=None)
                for _ in message.tokens
            ]
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            result = push._send_tokens(
                tokens,
                {"event": "offer_created", "offer_id": 1},
                title="Shared offer",
                message="Shared message",
                high_priority=True,
                android_channel_id="offer_updates",
            )

        self.assertEqual(messaging.send_each_for_multicast.call_count, 2)
        self.assertEqual(
            [
                len(call.args[0].tokens)
                for call in messaging.send_each_for_multicast.call_args_list
            ],
            [500, 1],
        )
        self.assertEqual(result.successful_tokens, set(tokens))

    def test_identical_notifications_are_sent_in_one_multicast_batch(self):
        first_user = User.objects.create_user(
            username="batch-push-user-1",
            email="batch-push-1@example.com",
            phone="+213555900101",
            password="Password1!",
        )
        second_user = User.objects.create_user(
            username="batch-push-user-2",
            email="batch-push-2@example.com",
            phone="+213555900102",
            password="Password1!",
        )
        first_device = ClientDevice.objects.create(
            user=first_user,
            token="batch-token-1",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        second_device = ClientDevice.objects.create(
            user=second_user,
            token="batch-token-2",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        first_notification = Notification.objects.create(
            recipient=first_user,
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.OFFER_CREATED,
            title="Shared offer",
            message="Shared message",
            data={"event": "offer_created", "offer_id": 1},
        )
        second_notification = Notification.objects.create(
            recipient=second_user,
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.OFFER_CREATED,
            title="Shared offer",
            message="Shared message",
            data={"event": "offer_created", "offer_id": 1},
        )
        messaging = Mock()
        messaging.MulticastMessage.side_effect = (
            lambda **kwargs: SimpleNamespace(**kwargs)
        )
        messaging.Notification.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.AndroidConfig.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.AndroidNotification.side_effect = (
            lambda **kwargs: SimpleNamespace(**kwargs)
        )
        messaging.APNSConfig.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.APNSPayload.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.Aps.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        messaging.send_each_for_multicast.return_value = SimpleNamespace(
            responses=[
                SimpleNamespace(success=True, exception=None),
                SimpleNamespace(success=True, exception=None),
            ]
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            result = push.send_notifications_push(
                [first_notification.id, second_notification.id],
                high_priority=True,
                android_channel_id="offer_updates",
            )

        message = messaging.send_each_for_multicast.call_args.args[0]
        self.assertEqual(
            set(message.tokens),
            {first_device.token, second_device.token},
        )
        self.assertNotIn("notification_id", message.data)
        self.assertEqual(message.data["offer_id"], "1")
        self.assertEqual(message.android.notification.channel_id, "offer_updates")
        self.assertEqual(
            result.successful_tokens,
            {first_device.token, second_device.token},
        )

    def test_only_unregistered_fcm_token_is_deleted(self):
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
            "UnregisteredError",
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
            result = push._send_tokens(
                [valid_device.token, invalid_device.token],
                {"event": "account_disabled"},
            )

        valid_device.refresh_from_db()
        self.assertEqual(result.successful_tokens, {valid_device.token})
        self.assertEqual(result.stale_tokens, {invalid_device.token})
        self.assertEqual(result.failed_tokens, set())
        self.assertTrue(valid_device.is_active)
        self.assertFalse(ClientDevice.objects.filter(pk=invalid_device.pk).exists())
        messaging.send_each_for_multicast.assert_called_once()

    def test_non_unregistered_fcm_error_keeps_device(self):
        user = User.objects.create_user(
            username="invalid-payload-user",
            email="invalid-payload-user@example.com",
            phone="+213555900004",
            password="Password1!",
        )
        device = ClientDevice.objects.create(
            user=user,
            token="invalid-payload-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        messaging = Mock()
        messaging.MulticastMessage.return_value = object()
        messaging.send_each_for_multicast.return_value = SimpleNamespace(
            responses=[
                SimpleNamespace(
                    success=False,
                    exception=type("InvalidArgumentError", (Exception,), {})(),
                )
            ]
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            result = push._send_tokens([device.token], {"event": "test"})

        self.assertEqual(result.failed_tokens, {device.token})
        self.assertTrue(ClientDevice.objects.filter(pk=device.pk).exists())

    def test_account_disabled_keeps_device_active_when_fcm_send_fails(self):
        user = User.objects.create_user(
            username="fcm-retry-user",
            email="fcm-retry-user@example.com",
            phone="+213555900002",
            password="Password1!",
        )
        device = ClientDevice.objects.create(
            user=user,
            token="transient-failure-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        messaging = Mock()
        messaging.MulticastMessage.return_value = object()
        messaging.send_each_for_multicast.side_effect = RuntimeError(
            "temporary FCM failure"
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            result = push.send_account_disabled_event(user.id)

        device.refresh_from_db()
        self.assertEqual(result.successful_tokens, set())
        self.assertEqual(result.failed_tokens, {device.token})
        self.assertTrue(device.is_active)

    def test_account_disabled_keeps_device_after_successful_delivery(self):
        user = User.objects.create_user(
            username="fcm-delivered-user",
            email="fcm-delivered-user@example.com",
            phone="+213555900003",
            password="Password1!",
        )
        device = ClientDevice.objects.create(
            user=user,
            token="delivered-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        messaging = Mock()
        messaging.MulticastMessage.return_value = object()
        messaging.send_each_for_multicast.return_value = SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None)]
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            result = push.send_account_disabled_event(user.id)

        device.refresh_from_db()
        self.assertEqual(result.successful_tokens, {device.token})
        self.assertTrue(device.is_active)

    def test_account_restored_push_has_required_payload_and_android_channel(self):
        user = User.objects.create_user(
            username="restored-push-user",
            email="restored-push-user@example.com",
            phone="+213555900005",
            password="Password1!",
        )
        device = ClientDevice.objects.create(
            user=user,
            token="restored-token",
            platform=ClientDevice.Platform.ANDROID,
            last_seen_at=timezone.now(),
        )
        notification = Notification.objects.create(
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.ACCOUNT_RESTORED,
            title="تم استعادة حسابك",
            message="تم استعادة حسابك بواسطة فريق دعم يلا ماركت.",
            recipient=user,
        )
        messaging = Mock()
        messaging.MulticastMessage.return_value = object()
        messaging.send_each_for_multicast.return_value = SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None)]
        )

        with patch.object(push, "_messaging_module", return_value=messaging):
            result = push.send_account_restored_push(notification.id)

        self.assertEqual(result.successful_tokens, {device.token})
        message_kwargs = messaging.MulticastMessage.call_args.kwargs
        self.assertEqual(message_kwargs["tokens"], [device.token])
        self.assertEqual(
            message_kwargs["data"],
            {
                "event": "account_restored",
                "notification_id": str(notification.id),
                "route": "login",
            },
        )
        messaging.Notification.assert_called_once_with(
            title="تم استعادة حسابك",
            body="تم استعادة حسابك بواسطة فريق دعم يلا ماركت.",
        )
        messaging.AndroidConfig.assert_called_once()
        self.assertEqual(
            messaging.AndroidConfig.call_args.kwargs["priority"],
            "high",
        )
        messaging.AndroidNotification.assert_called_once_with(
            channel_id="account_updates",
        )

    def test_account_restored_push_without_devices_is_successful(self):
        user = User.objects.create_user(
            username="restored-no-device-user",
            email="restored-no-device-user@example.com",
            phone="+213555900006",
            password="Password1!",
        )
        notification = Notification.objects.create(
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.ACCOUNT_RESTORED,
            title="تم استعادة حسابك",
            message="تم استعادة حسابك بواسطة فريق دعم يلا ماركت.",
            recipient=user,
        )

        with patch.object(push, "_messaging_module") as messaging_module:
            result = push.send_account_restored_push(notification.id)

        self.assertEqual(result.successful_tokens, set())
        self.assertEqual(result.failed_tokens, set())
        messaging_module.assert_not_called()
