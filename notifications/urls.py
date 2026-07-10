from django.urls import path

from .views import (
    NotificationClearReadView,
    NotificationDeleteView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationReadView,
    NotificationUnreadCountView,
    DeviceRegisterView,
    DeviceUnregisterView,
)

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path(
        "devices/register/",
        DeviceRegisterView.as_view(),
        name="notification-device-register",
    ),
    path(
        "devices/unregister/",
        DeviceUnregisterView.as_view(),
        name="notification-device-unregister",
    ),
    path(
        "clear-read/",
        NotificationClearReadView.as_view(),
        name="notification-clear-read",
    ),
    path(
        "<int:notification_id>/",
        NotificationDeleteView.as_view(),
        name="notification-delete",
    ),
    path(
        "<int:notification_id>/read/",
        NotificationReadView.as_view(),
        name="notification-read",
    ),
    path(
        "mark-all-read/",
        NotificationMarkAllReadView.as_view(),
        name="notification-mark-all-read",
    ),
    path(
        "unread-count/",
        NotificationUnreadCountView.as_view(),
        name="notification-unread-count",
    ),
]
