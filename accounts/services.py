import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone

from .models import OneTimePassword


OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 5


def normalize_email(email):
    return email.strip().lower()


def issue_otp(user, purpose):
    OneTimePassword.objects.filter(
        user=user,
        purpose=purpose,
        used_at__isnull=True,
    ).update(used_at=timezone.now())

    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    otp = OneTimePassword.objects.create(
        user=user,
        purpose=purpose,
        code_hash=make_password(code),
        expires_at=timezone.now()
        + timedelta(seconds=settings.AUTH_OTP_EXPIRY_SECONDS),
    )
    send_mail(
        subject=_otp_subject(purpose),
        message=(
            f"Your Yalla verification code is {code}. "
            f"It expires in {settings.AUTH_OTP_EXPIRY_SECONDS // 60} minutes."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return otp, code


def verify_otp(user, purpose, code):
    otp = (
        OneTimePassword.objects.filter(
            user=user,
            purpose=purpose,
            used_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )

    if otp is None:
        return None, "No active verification code was found."
    if otp.expires_at <= timezone.now():
        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        return None, "The verification code has expired."
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        return None, "Too many invalid attempts. Request a new code."
    if not check_password(code, otp.code_hash):
        otp.attempts += 1
        update_fields = ["attempts"]
        if otp.attempts >= OTP_MAX_ATTEMPTS:
            otp.used_at = timezone.now()
            update_fields.append("used_at")
        otp.save(update_fields=update_fields)
        return None, "Invalid verification code."

    otp.used_at = timezone.now()
    otp.save(update_fields=["used_at"])
    return otp, None


def otp_response_data(code):
    if settings.AUTH_OTP_INCLUDE_IN_RESPONSE:
        return {"dev_otp": code}
    return {}


def _otp_subject(purpose):
    if purpose == OneTimePassword.Purpose.REGISTRATION:
        return "Verify your Yalla account"
    return "Reset your Yalla password"
