import hashlib
import logging
import smtplib
import time
from datetime import timedelta
from typing import List, Optional

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from config.celery_utils import calculate_backoff, log_task_execution
from config.redis_client import get_redis_client

logger = logging.getLogger("accounts.tasks")

RETRYABLE_EMAIL_EXCEPTIONS = (
    smtplib.SMTPException,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _hash_email_payload(recipient_list: List[str], subject: str, message: str) -> str:
    serialized = f"{sorted(recipient_list)}:{subject}:{message}"
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _anonymize_recipient_list(recipients: List[str]) -> str:
    """Mask email addresses for safe structured logging without leaking PII."""
    masked = []
    for email in recipients:
        parts = email.split("@")
        if len(parts) == 2:
            name, domain = parts
            masked.append(f"{name[:2]}***@{domain}")
        else:
            masked.append("***")
    return ", ".join(masked)


@shared_task(
    bind=True,
    name="accounts.tasks.send_email_task",
    queue="mail",
    max_retries=3,
    soft_time_limit=15,
    time_limit=30,
)
def send_email_task(
    self,
    subject: str,
    message: str,
    recipient_list: List[str],
    html_message: Optional[str] = None,
    from_email: Optional[str] = None,
):
    """Send transactional email asynchronously via Celery worker."""
    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    safe_recipients = _anonymize_recipient_list(recipient_list)

    # Claim the payload atomically.  A failed delivery releases the claim before
    # retrying, while a completed delivery remains deduplicated briefly.
    payload_hash = _hash_email_payload(recipient_list, subject, message)
    dedup_key = f"yalla:email:dedup:{payload_hash}"
    in_flight = False
    try:
        r = get_redis_client("default")
        claimed = r.set(dedup_key, "processing", ex=30, nx=True)
        if not claimed:
            if r.get(dedup_key) not in ("completed", b"completed"):
                # A previous worker may have died after claiming the payload.
                # Retry after the lease expires instead of losing the email.
                in_flight = True
            else:
                log_task_execution(
                    self.name,
                    self.request.id,
                    safe_recipients,
                    attempt,
                    "success",
                    (time.perf_counter() - t0) * 1000.0,
                )
                return {"status": "skipped", "reason": "deduplicated"}
    except Exception:
        r = None
    if in_flight:
        raise self.retry(countdown=31)

    try:
        sender = from_email or settings.DEFAULT_FROM_EMAIL
        send_mail(
            subject=subject,
            message=message,
            from_email=sender,
            recipient_list=recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0

        try:
            r = get_redis_client("default")
            r.set(dedup_key, "completed", ex=30)
        except Exception:
            pass

        log_task_execution(
            self.name,
            self.request.id,
            safe_recipients,
            attempt,
            "success",
            duration_ms,
        )
        return {"status": "success", "recipients": safe_recipients}

    except RETRYABLE_EMAIL_EXCEPTIONS as exc:
        if r is not None:
            try:
                r.delete(dedup_key)
            except Exception:
                pass
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            safe_recipients,
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries, base=3.0, max_backoff=60.0)
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        if r is not None:
            try:
                r.delete(dedup_key)
            except Exception:
                pass
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            safe_recipients,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="accounts.tasks.cleanup_unverified_users_task",
    queue="default",
    max_retries=1,
    soft_time_limit=120,
    time_limit=180,
)
def cleanup_unverified_users_task(self):
    """Periodic maintenance task to purge stale unverified registrations and expired OTPs."""
    from accounts.models import OTPCooldown, OneTimePassword, PendingRegistration

    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    now = timezone.now()
    cutoff = now - timedelta(hours=settings.AUTH_UNVERIFIED_USER_RETENTION_HOURS)

    registrations = PendingRegistration.objects.filter(updated_at__lt=cutoff)
    stale_emails = list(registrations.values_list("email", flat=True))
    expired_legacy_otps = OneTimePassword.objects.filter(
        purpose=OneTimePassword.Purpose.REGISTRATION,
        expires_at__lte=now,
    )
    registration_count = registrations.count()
    expired_otp_count = expired_legacy_otps.count()

    with transaction.atomic():
        registrations.delete()
        OTPCooldown.objects.filter(
            purpose=OneTimePassword.Purpose.REGISTRATION,
            identifier__in=stale_emails,
        ).delete()
        expired_legacy_otps.delete()

    duration_ms = (time.perf_counter() - t0) * 1000.0
    log_task_execution(
        self.name,
        self.request.id,
        "unverified_users_cleanup",
        attempt,
        "success",
        duration_ms,
    )
    return {
        "status": "success",
        "cleaned_registrations": registration_count,
        "cleaned_otps": expired_otp_count,
    }
