from rest_framework.exceptions import APIException


ACCOUNT_INACTIVE_MESSAGE = "تم إيقاف حسابك. تواصل مع الدعم."
SESSION_EXPIRED_MESSAGE = "Session expired. Please login again."
INVALID_SESSION_MESSAGE = "Token is invalid."


class AccountInactive(APIException):
    status_code = 403
    default_code = "account_inactive"

    def __init__(self):
        self.detail = {
            "code": self.default_code,
            "detail": ACCOUNT_INACTIVE_MESSAGE,
        }


class EmailVerificationRequired(APIException):
    status_code = 403
    default_code = "email_verification_required"

    def __init__(
        self,
        *,
        email=None,
        retry_after_seconds=None,
        resend_available_at=None,
        registration_expires_at=None,
    ):
        detail = {
            "code": self.default_code,
            "detail": "Email verification is required.",
        }
        if email:
            detail["email"] = email
        if retry_after_seconds is not None:
            detail["retry_after_seconds"] = retry_after_seconds
        if resend_available_at is not None:
            detail["resend_available_at"] = resend_available_at.isoformat()
        if registration_expires_at is not None:
            detail["registration_expires_at"] = registration_expires_at.isoformat()
        self.detail = detail


class SessionExpired(APIException):
    status_code = 401
    default_code = "session_expired"

    def __init__(self):
        self.detail = {
            "code": self.default_code,
            "detail": SESSION_EXPIRED_MESSAGE,
        }


class InvalidSession(APIException):
    status_code = 401
    default_code = "token_not_valid"

    def __init__(self):
        self.detail = {
            "code": self.default_code,
            "detail": INVALID_SESSION_MESSAGE,
        }
