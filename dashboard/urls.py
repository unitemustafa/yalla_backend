from django.urls import path

from .views import AppLaunchMediaView, DashboardOverviewView, DashboardSettingsView

urlpatterns = [
    path("app-media/", AppLaunchMediaView.as_view(), name="app-launch-media"),
    path("overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("settings/", DashboardSettingsView.as_view(), name="dashboard-settings"),
]
