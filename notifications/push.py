import base64
import binascii
import json
import logging
from functools import lru_cache

from django.conf import settings
from django.utils import timezone

from accounts.exceptions import ACCOUNT_INACTIVE_MESSAGE

from .models import ClientDevice, Notification

logger = logging.getLogger(__name__)


class FirebaseConfigurationError(RuntimeError):
    """Raised when Firebase Admin service account configuration is invalid."""


def _string_data(data):
    normalized = {}
    for key, value in data.items():
        if value is None:
            normalized[str(key)] = ""
        elif isinstance(value, bool):
            normalized[str(key)] = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            normalized[str(key)] = json.dumps(value, ensure_ascii=False)
        else:
            normalized[str(key)] = str(value)
    return normalized


def _load_service_account_data():
    credentials_base64 = settings.FIREBASE_SERVICE_ACCOUNT_BASE64.strip()
    if credentials_base64:
        try:
            credentials_json = base64.b64decode(
                credentials_base64,
                validate=True,
            ).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise FirebaseConfigurationError(
                "FIREBASE_SERVICE_ACCOUNT_BASE64 must be valid "
                "Base64-encoded UTF-8 JSON."
            ) from None
        source_name = "FIREBASE_SERVICE_ACCOUNT_BASE64"
    else:
        credentials_json = settings.FIREBASE_SERVICE_ACCOUNT_JSON.strip()
        source_name = "FIREBASE_SERVICE_ACCOUNT_JSON"
        if not credentials_json:
            raise FirebaseConfigurationError(
                "Firebase configuration is missing. Set "
                "FIREBASE_SERVICE_ACCOUNT_BASE64 or "
                "FIREBASE_SERVICE_ACCOUNT_JSON."
            )

    try:
        credentials_data = json.loads(credentials_json)
    except (json.JSONDecodeError, TypeError):
        raise FirebaseConfigurationError(
            f"{source_name} must contain a valid JSON object."
        ) from None

    if not isinstance(credentials_data, dict):
        raise FirebaseConfigurationError(
            f"{source_name} must contain a JSON object."
        )
    return credentials_data


@lru_cache(maxsize=1)
def _messaging_module():
    credentials_data = _load_service_account_data()

    import firebase_admin
    from firebase_admin import credentials, messaging

    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            certificate = credentials.Certificate(credentials_data)
        except Exception:
            raise FirebaseConfigurationError(
                "Firebase service account credentials are invalid."
            ) from None
        firebase_admin.initialize_app(certificate)
    return messaging


def _send_tokens(tokens, data, *, title=None, message=None):
    messaging = _messaging_module()
    if messaging is None or not tokens:
        return set()
    stale_tokens = set()
    for start in range(0, len(tokens), 500):
        chunk = tokens[start : start + 500]
        try:
            response = messaging.send_each_for_multicast(
                messaging.MulticastMessage(
                    tokens=chunk,
                    data=_string_data(data),
                    notification=(
                        messaging.Notification(title=title, body=message)
                        if title and message
                        else None
                    ),
                )
            )
        except Exception:
            logger.exception("FCM multicast request failed")
            continue
        for token, item in zip(chunk, response.responses):
            if item.success or item.exception is None:
                continue
            if item.exception.__class__.__name__ in {
                "UnregisteredError",
                "SenderIdMismatchError",
            }:
                stale_tokens.add(token)
    if stale_tokens:
        ClientDevice.objects.filter(token__in=stale_tokens).update(
            is_active=False,
            updated_at=timezone.now(),
        )
    return stale_tokens


def send_notification_push(notification_id):
    try:
        notification = Notification.objects.select_related("recipient").get(
            pk=notification_id,
            recipient__isnull=False,
        )
        tokens = list(
            ClientDevice.objects.filter(
                user_id=notification.recipient_id,
                is_active=True,
            ).values_list("token", flat=True)
        )
        data = {
            **(notification.data or {}),
            "notification_id": notification.id,
            "title": notification.title,
            "message": notification.message,
        }
        _send_tokens(
            tokens,
            data,
            title=notification.title,
            message=notification.message,
        )
    except FirebaseConfigurationError:
        raise
    except Exception:
        logger.exception("Notification push failed for notification_id=%s", notification_id)


def send_account_disabled_event(user_id):
    devices = list(
        ClientDevice.objects.filter(user_id=user_id, is_active=True).values_list(
            "token",
            flat=True,
        )
    )
    try:
        _send_tokens(
            devices,
            {
                "event": "account_disabled",
                "code": "account_inactive",
                "message": ACCOUNT_INACTIVE_MESSAGE,
            },
        )
    finally:
        ClientDevice.objects.filter(user_id=user_id, is_active=True).update(
            is_active=False,
            updated_at=timezone.now(),
        )
