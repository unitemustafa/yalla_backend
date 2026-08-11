from unittest.mock import patch

from celery.exceptions import Retry
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings

from accounts.models import User

from .models import Notification, PushOutbox
from .push import PushDeliveryResult, send_notification_push
from .services import create_courier_notification
from .tasks import deliver_push_outbox


@override_settings(PUSH_DELIVERY_ASYNC=True)
class PushOutboxTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(
            username="outbox_client",
            email="outbox-client@example.com",
            phone="+201000000080",
            password="StrongPassword123!",
            role=User.Role.CLIENT,
        )
        self.notification = Notification.objects.create(
            audience=Notification.Audience.CLIENT,
            type=Notification.Type.ORDER_STATUS_CHANGED,
            title="Update",
            message="Order updated",
            recipient=self.user,
        )

    @patch("notifications.tasks.deliver_push_outbox.delay")
    def test_async_send_persists_before_publishing(self, delay):
        entry = send_notification_push(
            self.notification.id,
            high_priority=True,
            android_channel_id="orders",
        )

        self.assertTrue(PushOutbox.objects.filter(pk=entry.pk).exists())
        self.assertEqual(entry.status, PushOutbox.Status.PENDING)
        self.assertEqual(entry.options["android_channel_id"], "orders")
        delay.assert_called_once_with(str(entry.pk))

    @patch(
        "notifications.tasks._delivery_result",
        return_value=PushDeliveryResult(frozenset(), frozenset(), frozenset()),
    )
    def test_worker_marks_successful_delivery_complete(self, delivery):
        entry = PushOutbox.objects.create(
            kind=PushOutbox.Kind.NOTIFICATION,
            notification=self.notification,
        )

        result = deliver_push_outbox.run(str(entry.pk))

        entry.refresh_from_db()
        self.assertEqual(result, PushOutbox.Status.COMPLETED)
        self.assertEqual(entry.status, PushOutbox.Status.COMPLETED)
        self.assertEqual(entry.attempts, 1)
        delivery.assert_called_once()

    @patch("notifications.tasks._delivery_result")
    def test_duplicate_worker_delivery_does_not_send_twice(self, delivery):
        entry = PushOutbox.objects.create(
            kind=PushOutbox.Kind.NOTIFICATION,
            notification=self.notification,
            status=PushOutbox.Status.PROCESSING,
        )

        result = deliver_push_outbox.run(str(entry.pk))

        entry.refresh_from_db()
        self.assertEqual(result, PushOutbox.Status.PROCESSING)
        self.assertEqual(entry.attempts, 0)
        delivery.assert_not_called()

    @patch("notifications.tasks._delivery_result", side_effect=RuntimeError("FCM down"))
    def test_worker_keeps_retryable_failure_in_outbox(self, delivery):
        entry = PushOutbox.objects.create(
            kind=PushOutbox.Kind.NOTIFICATION,
            notification=self.notification,
        )

        # A task invoked directly re-raises the original exception; a worker
        # invocation raises Celery's Retry control-flow exception.
        with self.assertRaises((Retry, RuntimeError)):
            deliver_push_outbox.run(str(entry.pk))

        entry.refresh_from_db()
        self.assertEqual(entry.status, PushOutbox.Status.PENDING)
        self.assertEqual(entry.attempts, 1)
        self.assertIn("FCM down", entry.last_error)

    def test_database_rejects_an_outbox_entry_without_a_target(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PushOutbox.objects.create(kind=PushOutbox.Kind.NOTIFICATION)

    @patch(
        "notifications.tasks.deliver_push_outbox.delay",
        side_effect=RuntimeError("Redis down"),
    )
    def test_broker_outage_does_not_lose_or_fail_business_commit(self, delay):
        entry = send_notification_push(self.notification.id)

        entry.refresh_from_db()
        self.assertEqual(entry.status, PushOutbox.Status.PENDING)
        self.assertTrue(PushOutbox.objects.filter(pk=entry.pk).exists())

    @patch("notifications.tasks.deliver_push_outbox.delay")
    def test_service_persists_outbox_in_same_business_transaction(self, delay):
        courier = User.objects.create_user(
            username="outbox_courier",
            email="outbox-courier@example.com",
            phone="+201000000081",
            password="StrongPassword123!",
            role=User.Role.REPRESENTATIVE,
        )

        with transaction.atomic():
            notification = create_courier_notification(
                courier,
                notification_type=Notification.Type.ORDER_ASSIGNED,
                title="Assigned",
                message="A new order was assigned.",
                data={"event": "order_assigned"},
            )
            self.assertTrue(
                PushOutbox.objects.filter(
                    notification=notification,
                    kind=PushOutbox.Kind.COURIER_NOTIFICATION,
                ).exists()
            )
            delay.assert_not_called()

        entry = PushOutbox.objects.get(notification=notification)
        delay.assert_called_once_with(str(entry.pk))

    @patch("notifications.tasks.deliver_push_outbox.delay")
    def test_business_rollback_removes_notification_and_outbox(self, delay):
        courier = User.objects.create_user(
            username="rollback_courier",
            email="rollback-courier@example.com",
            phone="+201000000082",
            password="StrongPassword123!",
            role=User.Role.REPRESENTATIVE,
        )

        with self.assertRaises(RuntimeError), transaction.atomic():
            create_courier_notification(
                courier,
                notification_type=Notification.Type.ORDER_ASSIGNED,
                title="Assigned",
                message="A new order was assigned.",
                data={"event": "order_assigned"},
            )
            raise RuntimeError("roll back the business operation")

        self.assertFalse(
            Notification.objects.filter(recipient=courier).exists()
        )
        self.assertFalse(PushOutbox.objects.exists())
        delay.assert_not_called()
