from django.urls import path

from .views import (
    AdminPartnerApplicationDetailView,
    AdminPartnerApplicationListView,
    PartnerApplicationListCreateView,
)


urlpatterns = [
    path(
        "applications/",
        PartnerApplicationListCreateView.as_view(),
        name="partner-application-list-create",
    ),
    path(
        "admin/applications/",
        AdminPartnerApplicationListView.as_view(),
        name="admin-partner-application-list",
    ),
    path(
        "admin/applications/<int:application_id>/",
        AdminPartnerApplicationDetailView.as_view(),
        name="admin-partner-application-detail",
    ),
]

