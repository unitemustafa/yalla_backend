import logging

from django.db import transaction
from django.db.models import F
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from notifications.services import create_account_disabled_notification


logger = logging.getLogger(__name__)


def handle_client_deactivation(user, *, was_active, notify_disabled=True):
    if (
        not was_active
        or user.is_active
        or user.role != user.Role.CLIENT
    ):
        return False

    user.__class__.objects.filter(pk=user.pk).update(
        auth_token_version=F("auth_token_version") + 1,
    )
    user.refresh_from_db(fields=["auth_token_version"])
    BlacklistedToken.objects.bulk_create(
        [
            BlacklistedToken(token=token)
            for token in OutstandingToken.objects.filter(user=user)
        ],
        ignore_conflicts=True,
    )
    if notify_disabled:
        create_account_disabled_notification(user)
    transaction.on_commit(
        lambda user_id=user.pk: _dispatch_account_disabled(user_id)
    )
    return True


def _dispatch_account_disabled(user_id):
    from notifications.push import send_account_disabled_event

    try:
        send_account_disabled_event(user_id)
    except Exception:
        logger.exception(
            "Account-disabled notification delivery failed for user_id=%s",
            user_id,
        )
