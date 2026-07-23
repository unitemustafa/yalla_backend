from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import ClientDevice, Notification
from .serializers import (
    ClientDeviceSerializer,
    DeviceTokenSerializer,
    NotificationSerializer,
)


ADMIN_DASHBOARD_ORDER_EVENTS = (
    "courier_order_picked_up",
    "courier_order_delivered",
)


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
        return Notification.objects.filter(
            Q(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.NEW_ORDER_REVIEW,
            )
            | Q(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.ORDER_STATUS_CHANGED,
                data__event__in=ADMIN_DASHBOARD_ORDER_EVENTS,
            )
            | Q(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.NEW_PARTNER_APPLICATION,
            )
        )
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
        ).select_related("offer__market").order_by("-created_at", "-id")
        return Response(
            NotificationSerializer(
                notifications,
                many=True,
                context={"request": request},
            ).data
        )


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
        return Response(
            NotificationSerializer(
                notification,
                context={"request": request},
            ).data
        )


class NotificationDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, notification_id):
        notification = visible_notifications(request.user).filter(
            pk=notification_id,
        ).first()
        if notification is None:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if notification.is_blocking and not notification.is_resolved:
            return Response(
                {
                    "detail": (
                        "Unresolved blocking notifications cannot be deleted."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class NotificationClearReadView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        deleted_count, _ = (
            visible_notifications(request.user)
            .filter(is_read=True)
            .filter(Q(is_blocking=False) | Q(is_resolved=True))
            .delete()
        )
        return Response({"deleted_count": deleted_count})


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = visible_notifications(request.user).filter(is_read=False).count()
        return Response({"unread_count": count})


class DeviceRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in {
            User.Role.CLIENT,
            User.Role.REPRESENTATIVE,
        }:
            return Response(
                {"detail": "Only client or courier devices can be registered."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, _ = ClientDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "user": request.user,
                "platform": serializer.validated_data.get(
                    "platform",
                    ClientDevice.Platform.ANDROID,
                ),
                "is_active": True,
                "last_seen_at": timezone.now(),
            },
        )
        return Response(ClientDeviceSerializer(device).data)


class DeviceUnregisterView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.fields["platform"].required = False
        serializer.is_valid(raise_exception=True)
        ClientDevice.objects.filter(
            user=request.user,
            token=serializer.validated_data["token"],
        ).update(is_active=False, updated_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)
