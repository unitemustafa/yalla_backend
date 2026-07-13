from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.settings import api_settings

from .client_sessions import (
    client_session_claims,
    validate_client_session_deadline,
)
from .exceptions import AccountInactive, InvalidSession

User = get_user_model()


def token_user(validated_token):
    try:
        user_id = validated_token[api_settings.USER_ID_CLAIM]
        return User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
    except KeyError as exc:
        raise AuthenticationFailed(
            "Token contained no recognizable user identification.",
            code="token_not_valid",
        ) from exc
    except User.DoesNotExist as exc:
        raise AuthenticationFailed("User not found.", code="user_not_found") from exc


def validate_client_token_state(
    validated_token,
    user=None,
    *,
    validate_session_deadline=True,
):
    user = user or token_user(validated_token)
    if user.role not in {User.Role.CLIENT, User.Role.REPRESENTATIVE}:
        return user
    if user.deleted_at is not None or not user.is_active:
        raise AccountInactive()
    try:
        token_version = int(validated_token.get("auth_token_version", 0))
    except (TypeError, ValueError) as exc:
        if user.role == User.Role.CLIENT:
            raise InvalidSession() from exc
        raise AuthenticationFailed("Token is invalid.", code="token_not_valid") from exc
    if token_version != user.auth_token_version:
        if user.role == User.Role.REPRESENTATIVE:
            raise AuthenticationFailed(
                "Password changed. Please login again.",
                code="password_changed",
            )
        raise InvalidSession()
    if user.role in {User.Role.CLIENT, User.Role.REPRESENTATIVE}:
        if validate_session_deadline:
            validate_client_session_deadline(validated_token)
        else:
            client_session_claims(validated_token)
    return user
