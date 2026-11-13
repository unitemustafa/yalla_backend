from django.urls import path
from .app_updates import (
    DeliveryAppReleasesView, DeliveryAppReleaseStatusView, LatestDeliveryAppReleaseView,
)

from .views import AppLaunchMediaView, DashboardOverviewView, DashboardSettingsView
from .media_views import MediaSpecsView, MediaJobCreateView, MediaJobDetailView, MediaJobRetryView, MediaJobStatsView

urlpatterns = [
    path("app-updates/", DeliveryAppReleasesView.as_view(), name="delivery-app-releases"),
    path("app-updates/latest/", LatestDeliveryAppReleaseView.as_view(), name="latest-delivery-app-release"),
    path("app-updates/<int:release_id>/", DeliveryAppReleaseStatusView.as_view(), name="delivery-app-release-status"),
    path("media-specs/", MediaSpecsView.as_view(), name="media-specs"),
    path("media-jobs/", MediaJobCreateView.as_view(), name="media-job-create"),
    path("media-jobs/stats/", MediaJobStatsView.as_view(), name="media-job-stats"),
    path("media-jobs/<uuid:job_id>/", MediaJobDetailView.as_view(), name="media-job-detail"),
    path("media-jobs/<uuid:job_id>/retry/", MediaJobRetryView.as_view(), name="media-job-retry"),
    path("app-media/", AppLaunchMediaView.as_view(), name="app-launch-media"),
    path("overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("settings/", DashboardSettingsView.as_view(), name="dashboard-settings"),
]
