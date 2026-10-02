from django.urls import path

from .views import AppLaunchMediaView, DashboardOverviewView, DashboardSettingsView
from .media_views import MediaSpecsView, MediaJobCreateView, MediaJobDetailView, MediaJobRetryView, MediaJobStatsView

urlpatterns = [
    path("media-specs/", MediaSpecsView.as_view(), name="media-specs"),
    path("media-jobs/", MediaJobCreateView.as_view(), name="media-job-create"),
    path("media-jobs/stats/", MediaJobStatsView.as_view(), name="media-job-stats"),
    path("media-jobs/<uuid:job_id>/", MediaJobDetailView.as_view(), name="media-job-detail"),
    path("media-jobs/<uuid:job_id>/retry/", MediaJobRetryView.as_view(), name="media-job-retry"),
    path("app-media/", AppLaunchMediaView.as_view(), name="app-launch-media"),
    path("overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("settings/", DashboardSettingsView.as_view(), name="dashboard-settings"),
]
