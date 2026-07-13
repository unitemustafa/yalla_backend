from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from .exceptions import InvalidSession, SessionExpired


CLIENT_SESSION_MODE_CLAIM = "client_session_mode"
CLIENT_SESSION_STARTED_AT_CLAIM = "client_session_started_at"
CLIENT_SESSION_EXPIRES_AT_CLAIM = "client_session_exp"

PERSISTENT_MODE = "persistent"
TEMPORARY_MODE = "temporary"


@dataclass(frozen=True)
class ClientSessionClaims:
    mode: str
    started_at: int
    absolute_expires_at: int | None
    legacy: bool = False

    @property
    def remember(self):
        return self.mode == PERSISTENT_MODE


def now_epoch(now=None):
    return int((now or timezone.now()).timestamp())


def client_session_claims(token):
    mode = token.get(CLIENT_SESSION_MODE_CLAIM)
    legacy = mode is None
    if legacy:
        mode = TEMPORARY_MODE
    if mode not in {PERSISTENT_MODE, TEMPORARY_MODE}:
        raise InvalidSession()

    try:
        started_at = int(
            token.get(CLIENT_SESSION_STARTED_AT_CLAIM, token.get("iat"))
        )
    except (TypeError, ValueError) as exc:
        raise InvalidSession() from exc

    absolute_expires_at = None
    if mode == TEMPORARY_MODE:
        raw_deadline = token.get(CLIENT_SESSION_EXPIRES_AT_CLAIM)
        if raw_deadline is None:
            raw_deadline = started_at + int(
                settings.CLIENT_TEMPORARY_SESSION_LIFETIME.total_seconds()
            )
        try:
            absolute_expires_at = int(raw_deadline)
        except (TypeError, ValueError) as exc:
            raise InvalidSession() from exc

    return ClientSessionClaims(
        mode=mode,
        started_at=started_at,
        absolute_expires_at=absolute_expires_at,
        legacy=legacy,
    )


def apply_new_client_session(refresh, *, remember, now=None):
    now = now or timezone.now()
    started_at = int(now.timestamp())
    refresh[CLIENT_SESSION_STARTED_AT_CLAIM] = started_at

    if remember:
        refresh[CLIENT_SESSION_MODE_CLAIM] = PERSISTENT_MODE
        refresh.payload.pop(CLIENT_SESSION_EXPIRES_AT_CLAIM, None)
        refresh.set_exp(
            from_time=now,
            lifetime=settings.CLIENT_REMEMBERED_SESSION_LIFETIME,
        )
    else:
        deadline = started_at + int(
            settings.CLIENT_TEMPORARY_SESSION_LIFETIME.total_seconds()
        )
        refresh[CLIENT_SESSION_MODE_CLAIM] = TEMPORARY_MODE
        refresh[CLIENT_SESSION_EXPIRES_AT_CLAIM] = deadline
        refresh["exp"] = deadline

    return client_session_claims(refresh)


def apply_rotated_client_session(refresh, claims, *, now=None):
    now = now or timezone.now()
    refresh[CLIENT_SESSION_MODE_CLAIM] = claims.mode
    refresh[CLIENT_SESSION_STARTED_AT_CLAIM] = claims.started_at

    if claims.remember:
        refresh.payload.pop(CLIENT_SESSION_EXPIRES_AT_CLAIM, None)
        refresh.set_exp(
            from_time=now,
            lifetime=settings.CLIENT_REMEMBERED_SESSION_LIFETIME,
        )
    else:
        refresh[CLIENT_SESSION_EXPIRES_AT_CLAIM] = claims.absolute_expires_at
        refresh["exp"] = claims.absolute_expires_at


def client_access_token(refresh, *, now=None):
    now = now or timezone.now()
    remaining = int(refresh["exp"]) - int(now.timestamp())
    if remaining <= 0:
        raise SessionExpired()

    access = refresh.access_token
    access.set_exp(
        from_time=now,
        lifetime=min(
            timedelta(seconds=remaining),
            settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
        ),
    )
    return access


def validate_client_session_deadline(token, *, now=None):
    claims = client_session_claims(token)
    if (
        claims.absolute_expires_at is not None
        and claims.absolute_expires_at <= now_epoch(now)
    ):
        raise SessionExpired()
    return claims


def client_session_metadata(refresh, access):
    claims = client_session_claims(refresh)
    return {
        "mode": claims.mode,
        "remember": claims.remember,
        "startedAt": _iso_from_epoch(claims.started_at),
        "absoluteExpiresAt": (
            _iso_from_epoch(claims.absolute_expires_at)
            if claims.absolute_expires_at is not None
            else None
        ),
        "accessExpiresAt": _iso_from_epoch(int(access["exp"])),
        "refreshExpiresAt": _iso_from_epoch(int(refresh["exp"])),
    }


def access_expires_in(access, *, now=None):
    return max(0, int(access["exp"]) - now_epoch(now))


def sync_outstanding_token(refresh, *, user=None):
    expires_at = datetime.fromtimestamp(
        int(refresh["exp"]),
        tz=datetime_timezone.utc,
    )
    updates = {
        "token": str(refresh),
        "expires_at": expires_at,
    }
    if user is not None:
        updates["user"] = user
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(**updates)


def _iso_from_epoch(value):
    return (
        datetime.fromtimestamp(value, tz=datetime_timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
