from django.urls import path

from .views import (
    HomeCampaignDetailView,
    HomeCampaignListCreateView,
    HomeCampaignMediaUploadView,
    OfferDetailView,
    OfferImageUploadView,
    OfferListCreateView,
    OfferSendNotificationView,
)

urlpatterns = [
    path(
        "home-campaigns/",
        HomeCampaignListCreateView.as_view(),
        name="home-campaign-list-create",
    ),
    path(
        "home-campaigns/<int:campaign_id>/media/",
        HomeCampaignMediaUploadView.as_view(),
        name="home-campaign-media-upload",
    ),
    path(
        "home-campaigns/<int:campaign_id>/",
        HomeCampaignDetailView.as_view(),
        name="home-campaign-detail",
    ),
    path(
        "<int:offer_id>/send-notification/",
        OfferSendNotificationView.as_view(),
        name="offer-send-notification",
    ),
    path(
        "<int:offer_id>/image/",
        OfferImageUploadView.as_view(),
        name="offer-image-upload",
    ),
    path(
        "",
        OfferListCreateView.as_view(),
        name="offer-list-create",
    ),
    path(
        "<int:offer_id>/",
        OfferDetailView.as_view(),
        name="offer-detail",
    ),
]
