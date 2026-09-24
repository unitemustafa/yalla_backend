import smtplib
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import PendingRegistration
from accounts.tasks import (
    _anonymize_recipient_list,
    _hash_email_payload,
    cleanup_unverified_users_task,
    send_email_task,
)
from config.test_fakes import InMemoryRedis


class AccountsCeleryTasksTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.redis = InMemoryRedis()
        self.redis_patcher = patch(
            "accounts.tasks.get_redis_client", return_value=self.redis
        )
        self.redis_patcher.start()
        self.addCleanup(self.redis_patcher.stop)
        self.metrics_redis_patcher = patch(
            "config.celery_utils.get_redis_client", return_value=self.redis
        )
        self.metrics_redis_patcher.start()
        self.addCleanup(self.metrics_redis_patcher.stop)

    def test_anonymize_recipient_list_masks_pii(self):
        recipients = ["customer.ali@example.com", "admin@company.org", "invalid"]
        masked = _anonymize_recipient_list(recipients)
        self.assertIn("cu***@example.com", masked)
        self.assertIn("ad***@company.org", masked)
        self.assertNotIn("customer.ali", masked)

    def test_send_email_task_success(self):
        result = send_email_task.apply(
            args=[
                "Welcome to Yalla",
                "Hello, your account is ready.",
                ["client@example.com"],
            ],
            kwargs={"html_message": "<p>Hello</p>"},
        ).get()

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Welcome to Yalla")
        self.assertEqual(mail.outbox[0].to, ["client@example.com"])

    def test_send_email_task_deduplication_skips_duplicate(self):
        subject = "Your Verification Code"
        message = "Your OTP is 123456"
        recipients = ["dedup@example.com"]

        # First run succeeds
        first = send_email_task.apply(args=[subject, message, recipients]).get()
        self.assertEqual(first["status"], "success")
        self.assertEqual(len(mail.outbox), 1)

        # Second run within 30s is skipped by Redis deduplication lock
        second = send_email_task.apply(args=[subject, message, recipients]).get()
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(second["reason"], "deduplicated")
        self.assertEqual(len(mail.outbox), 1)

    def test_send_email_task_retries_an_abandoned_processing_claim(self):
        key = f"yalla:email:dedup:{_hash_email_payload(['retry@example.com'], 'OTP', '123456')}"
        self.redis.set(key, "processing", ex=30)

        with patch.object(
            send_email_task, "retry", side_effect=RuntimeError("retry_called")
        ) as retry:
            with self.assertRaisesMessage(RuntimeError, "retry_called"):
                send_email_task.apply(args=["OTP", "123456", ["retry@example.com"]])

        retry.assert_called_once_with(countdown=31)
        self.assertEqual(len(mail.outbox), 0)

    @patch(
        "accounts.tasks.send_mail",
        side_effect=smtplib.SMTPConnectError(421, b"Connection refused"),
    )
    def test_send_email_task_retries_on_smtp_error(self, mock_send_mail):
        with patch.object(
            send_email_task, "retry", side_effect=RuntimeError("retry_called")
        ) as mock_retry:
            with self.assertRaises(RuntimeError) as ctx:
                send_email_task.apply(args=["Retry Test", "Msg", ["retry@example.com"]])
            self.assertEqual(str(ctx.exception), "retry_called")
            mock_retry.assert_called_once()
        self.assertIsNone(
            self.redis.get(
                f"yalla:email:dedup:{_hash_email_payload(['retry@example.com'], 'Retry Test', 'Msg')}"
            )
        )

    def test_cleanup_unverified_users_task(self):
        now = timezone.now()
        retention = getattr(settings, "AUTH_UNVERIFIED_USER_RETENTION_HOURS", 48)

        stale_reg = PendingRegistration.objects.create(
            phone="+201000000001",
            username="stale_user",
            first_name="Stale",
            last_name="User",
            email="stale@example.com",
            password_hash="fakehash",
            terms_accepted_at=now,
        )
        # Manually force updated_at into the past since auto_now resets it on save
        PendingRegistration.objects.filter(pk=stale_reg.pk).update(
            updated_at=now - timedelta(hours=retention + 2)
        )

        fresh_reg = PendingRegistration.objects.create(
            phone="+201000000002",
            username="fresh_user",
            first_name="Fresh",
            last_name="User",
            email="fresh@example.com",
            password_hash="fakehash",
            terms_accepted_at=now,
        )

        res = cleanup_unverified_users_task.apply().get()
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["cleaned_registrations"], 1)

        self.assertFalse(PendingRegistration.objects.filter(pk=stale_reg.pk).exists())
        self.assertTrue(PendingRegistration.objects.filter(pk=fresh_reg.pk).exists())
