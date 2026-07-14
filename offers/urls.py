from django.urls import path

from .views import (
    OfferDetailView,
    OfferImageUploadView,
    OfferListCreateView,
    OfferSendNotificationView,
)

urlpatterns = [
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
