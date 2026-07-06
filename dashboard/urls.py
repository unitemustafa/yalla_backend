from django.urls import path

from .views import DashboardOverviewView, DashboardSettingsView

urlpatterns = [
    path("overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("settings/", DashboardSettingsView.as_view(), name="dashboard-settings"),
]
