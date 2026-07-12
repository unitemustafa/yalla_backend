import base64
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from accounts.exceptions import ACCOUNT_INACTIVE_MESSAGE

from .models import ClientDevice, Notification

logger = logging.getLogger(__name__)


class FirebaseConfigurationError(RuntimeError):
    """Raised when Firebase Admin service account configuration is invalid."""


@dataclass(frozen=True)
class PushDeliveryResult:
    successful_tokens: frozenset
    stale_tokens: frozenset
    failed_tokens: frozenset


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


def _send_tokens(
    tokens,
    data,
    *,
    title=None,
    message=None,
    high_priority=False,
    android_channel_id=None,
):
    if not tokens:
        return PushDeliveryResult(frozenset(), frozenset(), frozenset())
    messaging = _messaging_module()
    if messaging is None:
        return PushDeliveryResult(
            frozenset(),
            frozenset(),
            frozenset(tokens),
        )
    successful_tokens = set()
    stale_tokens = set()
    failed_tokens = set()
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
                    android=(
                        messaging.AndroidConfig(
                            priority="high",
                            ttl=timedelta(minutes=5),
                            notification=(
                                messaging.AndroidNotification(
                                    channel_id=android_channel_id,
                                )
                                if android_channel_id
                                else None
                            ),
                        )
                        if high_priority or android_channel_id
                        else None
                    ),
                    apns=(
                        messaging.APNSConfig(
                            headers={"apns-priority": "10"},
                            payload=messaging.APNSPayload(
                                aps=messaging.Aps(
                                    content_available=True,
                                    sound="default",
                                )
                            ),
                        )
                        if high_priority
                        else None
                    ),
                )
            )
        except Exception:
            logger.exception("FCM multicast request failed")
            failed_tokens.update(chunk)
            continue
        for token, item in zip(chunk, response.responses):
            if item.success:
                successful_tokens.add(token)
                continue
            if (
                item.exception is not None
                and item.exception.__class__.__name__ == "UnregisteredError"
            ):
                stale_tokens.add(token)
            else:
                failed_tokens.add(token)
    if stale_tokens:
        ClientDevice.objects.filter(token__in=stale_tokens).delete()
    return PushDeliveryResult(
        frozenset(successful_tokens),
        frozenset(stale_tokens),
        frozenset(failed_tokens),
    )


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


def send_account_restored_push(notification_id):
    notification = Notification.objects.get(
        pk=notification_id,
        type=Notification.Type.ACCOUNT_RESTORED,
        recipient__isnull=False,
    )
    tokens = list(
        ClientDevice.objects.filter(
            user_id=notification.recipient_id,
            is_active=True,
        ).values_list("token", flat=True)
    )
    return _send_tokens(
        tokens,
        {
            "event": "account_restored",
            "notification_id": str(notification.id),
            "route": "login",
        },
        title=notification.title,
        message=notification.message,
        high_priority=True,
        android_channel_id="account_updates",
    )


def send_account_disabled_event(user_id):
    devices = list(
        ClientDevice.objects.filter(user_id=user_id, is_active=True).values_list(
            "token",
            flat=True,
        )
    )
    result = _send_tokens(
        devices,
        {
            "event": "account_disabled",
            "code": "account_inactive",
            "message": ACCOUNT_INACTIVE_MESSAGE,
        },
        title="تم تعطيل حسابك",
        message=ACCOUNT_INACTIVE_MESSAGE,
        high_priority=True,
    )
    if result.failed_tokens:
        logger.warning(
            "Account-disabled push failed for user_id=%s on %s device(s); "
            "tokens remain active for a later retry.",
            user_id,
            len(result.failed_tokens),
        )
    return result


def send_delivery_area_status_changed_event(area_id, is_active):
    devices = list(
        ClientDevice.objects.filter(
            user__addresses__delivery_area_id=area_id,
            is_active=True,
        )
        .distinct()
        .values_list("token", flat=True)
    )
    _send_tokens(
        devices,
        {
            "event": "delivery_area_status_changed",
            "area_id": str(area_id),
            "is_active": str(bool(is_active)).lower(),
        },
    )
