from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import Notification
from .serializers import NotificationSerializer


def parse_bool(value):
    if value is None:
        return None
    normalized = value.lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def visible_notifications(user):
    if user.role == User.Role.ADMIN:
        return Notification.objects.filter(audience=Notification.Audience.ADMIN)
    audience = (
        Notification.Audience.COURIER
        if user.role == User.Role.REPRESENTATIVE
        else Notification.Audience.CLIENT
    )
    return Notification.objects.filter(audience=audience, recipient=user)


def apply_notification_filters(queryset, params):
    unread = parse_bool(params.get("unread"))
    if unread is True:
        queryset = queryset.filter(is_read=False)
    elif unread is False:
        queryset = queryset.filter(is_read=True)

    notification_type = params.get("type")
    if notification_type:
        queryset = queryset.filter(type=notification_type)

    audience = params.get("audience")
    if audience:
        queryset = queryset.filter(audience=audience)

    is_blocking = parse_bool(params.get("is_blocking"))
    if is_blocking is not None:
        queryset = queryset.filter(is_blocking=is_blocking)

    is_resolved = parse_bool(params.get("is_resolved"))
    if is_resolved is not None:
        queryset = queryset.filter(is_resolved=is_resolved)

    return queryset


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = apply_notification_filters(
            visible_notifications(request.user),
            request.query_params,
        ).order_by("-created_at", "-id")
        return Response(NotificationSerializer(notifications, many=True).data)


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id):
        notification = visible_notifications(request.user).filter(
            pk=notification_id,
        ).first()
        if notification is None:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        count = visible_notifications(request.user).filter(is_read=False).update(
            is_read=True,
            read_at=now,
            updated_at=now,
        )
        return Response({"marked_read": count})


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = visible_notifications(request.user).filter(is_read=False).count()
        return Response({"unread_count": count})
