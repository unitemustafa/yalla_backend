from django.urls import path

from .region_views import (
    MarketRegionDetectView,
    MarketRegionMeView,
    MarketRegionOptionsView,
)


urlpatterns = [
    path("detect/", MarketRegionDetectView.as_view(), name="market-region-detect"),
    path("options/", MarketRegionOptionsView.as_view(), name="market-region-options"),
    path("me/", MarketRegionMeView.as_view(), name="market-region-me"),
]
