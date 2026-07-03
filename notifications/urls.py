from django.urls import path

from .views import (
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationReadView,
    NotificationUnreadCountView,
)

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
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
