import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import OTPCooldown, OneTimePassword


OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_DURATIONS = [30, 60, 120, 300]


class OTPCooldownError(Exception):
    def __init__(self, retry_after_seconds):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Please wait before requesting another code.")


def normalize_email(email):
    return email.strip().lower()


def issue_otp(user, purpose):
    with transaction.atomic():
        cooldown = _locked_cooldown(user.email, purpose)
        _enforce_cooldown(cooldown)

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
        email_context = _otp_email_context(user, purpose, code)
        send_mail(
            subject=email_context["subject"],
            message=render_to_string(
                "accounts/emails/otp.txt",
                email_context,
            ).strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
            html_message=render_to_string(
                "accounts/emails/otp.html",
                email_context,
            ),
        )
        cooldown_data = _mark_cooldown_sent(cooldown)
        return otp, code, cooldown_data


def clear_otp_cooldown(email, purpose):
    OTPCooldown.objects.filter(
        identifier=normalize_email(email),
        purpose=purpose,
    ).delete()


def verify_otp(user, purpose, code, *, consume=True):
    # The selected code must remain locked through each state transition so a
    # valid registration code can only be consumed by one request.
    with transaction.atomic():
        otp = (
            OneTimePassword.objects.select_for_update()
            .filter(
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

        if consume:
            otp.used_at = timezone.now()
            otp.save(update_fields=["used_at"])
        return otp, None


def otp_response_data(code):
    if settings.AUTH_OTP_INCLUDE_IN_RESPONSE:
        return {"dev_otp": code}
    return {}


def otp_cooldown_response_data(cooldown_data):
    return {
        "resend_after_seconds": cooldown_data["resend_after_seconds"],
        "resend_available_at": cooldown_data["resend_available_at"].isoformat(),
    }


def _locked_cooldown(email, purpose):
    identifier = normalize_email(email)
    try:
        return OTPCooldown.objects.select_for_update().get(
            purpose=purpose,
            identifier=identifier,
        )
    except OTPCooldown.DoesNotExist:
        try:
            with transaction.atomic():
                return OTPCooldown.objects.create(
                    purpose=purpose,
                    identifier=identifier,
                )
        except IntegrityError:
            return OTPCooldown.objects.select_for_update().get(
                purpose=purpose,
                identifier=identifier,
            )


def _enforce_cooldown(cooldown):
    now = timezone.now()
    next_allowed_at = cooldown.next_allowed_at
    if next_allowed_at and next_allowed_at > now:
        retry_after = int((next_allowed_at - now).total_seconds())
        if retry_after < 1:
            retry_after = 1
        raise OTPCooldownError(retry_after)

    expiry_seconds = getattr(settings, "AUTH_OTP_EXPIRY_SECONDS", 600)
    if (
        next_allowed_at
        and next_allowed_at <= now
        and cooldown.last_sent_at
        and cooldown.last_sent_at <= now - timedelta(seconds=expiry_seconds)
    ):
        cooldown.resend_level = 0
        cooldown.next_allowed_at = None
        cooldown.save(update_fields=["resend_level", "next_allowed_at", "updated_at"])


def _mark_cooldown_sent(cooldown):
    now = timezone.now()
    duration = OTP_COOLDOWN_DURATIONS[
        min(cooldown.resend_level, len(OTP_COOLDOWN_DURATIONS) - 1)
    ]
    cooldown.resend_level = min(
        cooldown.resend_level + 1,
        len(OTP_COOLDOWN_DURATIONS) - 1,
    )
    cooldown.last_sent_at = now
    cooldown.next_allowed_at = now + timedelta(seconds=duration)
    cooldown.save(
        update_fields=[
            "resend_level",
            "last_sent_at",
            "next_allowed_at",
            "updated_at",
        ]
    )
    return {
        "resend_after_seconds": duration,
        "resend_available_at": cooldown.next_allowed_at,
    }


def _otp_subject(purpose):
    if purpose == OneTimePassword.Purpose.REGISTRATION:
        return "Yalla Market | رمز تأكيد البريد الإلكتروني"
    return "Yalla Market | رمز تغيير كلمة المرور"


def _otp_email_context(user, purpose, code):
    expiry_seconds = getattr(settings, "AUTH_OTP_EXPIRY_SECONDS", 600)
    expiry_minutes = max(1, (expiry_seconds + 59) // 60)
    is_registration = purpose == OneTimePassword.Purpose.REGISTRATION

    return {
        "subject": _otp_subject(purpose),
        "code": code,
        "expiry_minutes": expiry_minutes,
        "first_name": user.first_name.strip(),
        "headline_ar": (
            "أكد بريدك الإلكتروني"
            if is_registration
            else "غيّر كلمة المرور بأمان"
        ),
        "headline_en": (
            "Verify your email"
            if is_registration
            else "Reset your password securely"
        ),
        "intro_ar": (
            "استخدم رمز التأكيد التالي لإكمال إنشاء حسابك في يلا ماركت."
            if is_registration
            else "استخدم الرمز التالي لتأكيد طلب تغيير كلمة المرور."
        ),
        "intro_en": (
            "Use the following verification code to finish creating your Yalla Market account."
            if is_registration
            else "Use the following code to confirm your password reset request."
        ),
        "preheader": (
            "رمز تأكيد حسابك في يلا ماركت"
            if is_registration
            else "رمز تغيير كلمة مرور حسابك في يلا ماركت"
        ),
    }
