from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase

from config.firebase_admin import FirebaseConfigurationError
from config.test_fakes import InMemoryRedis
from notifications.models import Notification
from notifications.push import PushDeliveryResult
from notifications.tasks import (
    send_account_disabled_event_task,
    send_notification_push_task,
    send_notifications_multicast_batch_task,
)

User = get_user_model()


class NotificationsCeleryTasksTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notif_user",
            email="notif@example.com",
            phone="+201011112222",
            password="Password1!",
            role=User.Role.CLIENT,
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.ORDER_ASSIGNED,
            title="Order Update",
            message="Your order is on the way.",
        )
        self.redis = InMemoryRedis()
        self.redis_patcher = patch(
            "notifications.tasks.get_redis_client", return_value=self.redis
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)
        self.metrics_redis_patcher = patch(
            "config.celery_utils.get_redis_client", return_value=self.redis
        )
        self.metrics_redis_patcher.start()
        self.addCleanup(self.metrics_redis_patcher.stop)

    @patch("notifications.tasks._send_notification_push_now")
    def test_send_notification_push_task_success(self, mock_send):
        mock_send.return_value = PushDeliveryResult(
            successful_tokens=frozenset(["token_1"]),
            stale_tokens=frozenset(),
            failed_tokens=frozenset(),
        )

        result = send_notification_push_task.apply(
            args=[self.notification.id],
            kwargs={"high_priority": True, "android_channel_id": "order_updates"},
        ).get()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["successful_tokens"], 1)
        mock_send.assert_called_once_with(
            self.notification.id,
            high_priority=True,
            android_channel_id="order_updates",
        )

    @patch("notifications.tasks._send_notification_push_now")
    def test_send_notification_push_task_idempotency_deduplication(self, mock_send):
        mock_send.return_value = PushDeliveryResult(
            successful_tokens=frozenset(["token_1"]),
            stale_tokens=frozenset(),
            failed_tokens=frozenset(),
        )

        # 1st call executes push
        first = send_notification_push_task.apply(args=[self.notification.id]).get()
        self.assertEqual(first["status"], "success")
        mock_send.assert_called_once()

        # 2nd call is deduplicated via Redis
        second = send_notification_push_task.apply(args=[self.notification.id]).get()
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(second["reason"], "already_sent")
        self.assertEqual(mock_send.call_count, 1)

    @patch("notifications.tasks._send_notification_push_now")
    def test_push_retries_an_abandoned_processing_claim(self, mock_send):
        self.redis.set(f"yalla:push:sent:{self.notification.id}", "processing", ex=30)

        with patch.object(
            send_notification_push_task,
            "retry",
            side_effect=RuntimeError("retry_called"),
        ) as retry:
            with self.assertRaisesMessage(RuntimeError, "retry_called"):
                send_notification_push_task.apply(args=[self.notification.id])

        retry.assert_called_once_with(countdown=31)
        mock_send.assert_not_called()

    @patch("notifications.tasks._send_notification_push_now")
    def test_push_failed_tokens_are_retried_without_durable_success(self, mock_send):
        mock_send.return_value = PushDeliveryResult(
            successful_tokens=frozenset(),
            stale_tokens=frozenset(),
            failed_tokens=frozenset({"temporary-failure"}),
        )

        with patch.object(
            send_notification_push_task,
            "retry",
            side_effect=RuntimeError("retry_called"),
        ):
            with self.assertRaisesMessage(RuntimeError, "retry_called"):
                send_notification_push_task.apply(args=[self.notification.id])

        self.notification.refresh_from_db()
        self.assertFalse(self.notification.data.get("push_dispatched", False))
        self.assertIsNone(self.redis.get(f"yalla:push:sent:{self.notification.id}"))

    @patch(
        "notifications.tasks._send_notification_push_now",
        side_effect=requests.exceptions.ConnectTimeout("FCM timeout"),
    )
    def test_send_notification_push_task_retries_on_network_timeout(self, mock_send):
        with patch.object(
            send_notification_push_task,
            "retry",
            side_effect=RuntimeError("retry_invoked"),
        ) as mock_retry:
            with self.assertRaises(RuntimeError) as ctx:
                send_notification_push_task.apply(args=[self.notification.id])
            self.assertEqual(str(ctx.exception), "retry_invoked")
            mock_retry.assert_called_once()
        self.assertIsNone(self.redis.get(f"yalla:push:sent:{self.notification.id}"))

    @patch(
        "notifications.tasks._send_notification_push_now",
        side_effect=FirebaseConfigurationError("Invalid credentials"),
    )
    def test_send_notification_push_task_permanent_failure_on_config_error(
        self, mock_send
    ):
        result = send_notification_push_task.apply(args=[self.notification.id]).get()
        self.assertEqual(result["status"], "failed")
        self.assertIn("Invalid credentials", result["error"])

    @patch("notifications.tasks.send_notifications_push")
    def test_send_notifications_multicast_batch_task(self, mock_multicast):
        mock_multicast.return_value = PushDeliveryResult(
            successful_tokens=frozenset(["tok1", "tok2"]),
            stale_tokens=frozenset(),
            failed_tokens=frozenset(),
        )

        result = send_notifications_multicast_batch_task.apply(
            args=[[self.notification.id]],
            kwargs={"high_priority": True, "android_channel_id": "promo"},
        ).get()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["successful_tokens"], 2)
        mock_multicast.assert_called_once_with(
            [self.notification.id],
            high_priority=True,
            android_channel_id="promo",
        )

    @patch("notifications.tasks.send_notifications_push")
    def test_multicast_retry_only_sends_notifications_not_yet_dispatched(
        self, mock_multicast
    ):
        another = Notification.objects.create(
            recipient=self.user,
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.ORDER_ASSIGNED,
            title="Another update",
            message="A second notification.",
        )
        mock_multicast.return_value = PushDeliveryResult(
            successful_tokens=frozenset({"sent-token"}),
            stale_tokens=frozenset(),
            failed_tokens=frozenset({"failed-token"}),
            dispatched_notification_ids=frozenset({self.notification.id}),
        )

        with patch.object(
            send_notifications_multicast_batch_task,
            "retry",
            side_effect=RuntimeError("retry_invoked"),
        ):
            with self.assertRaisesMessage(RuntimeError, "retry_invoked"):
                send_notifications_multicast_batch_task.apply(
                    args=[[self.notification.id, another.id]]
                )

        self.notification.refresh_from_db()
        another.refresh_from_db()
        self.assertTrue(self.notification.data["push_dispatched"])
        self.assertFalse(another.data.get("push_dispatched", False))

        mock_multicast.return_value = PushDeliveryResult(
            successful_tokens=frozenset({"failed-token"}),
            stale_tokens=frozenset(),
            failed_tokens=frozenset(),
            dispatched_notification_ids=frozenset({another.id}),
        )
        result = send_notifications_multicast_batch_task.apply(
            args=[[self.notification.id, another.id]]
        ).get()

        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_multicast.call_args.args[0], [another.id])
        another.refresh_from_db()
        self.assertTrue(another.data["push_dispatched"])

    @patch("notifications.tasks._send_account_disabled_event_now")
    def test_send_account_disabled_event_task(self, mock_send):
        mock_send.return_value = None
        result = send_account_disabled_event_task.apply(args=[self.user.id]).get()
        self.assertEqual(result["status"], "success")
        mock_send.assert_called_once_with(self.user.id)
