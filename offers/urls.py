from django.urls import path

from .views import OfferDetailView, OfferListCreateView

urlpatterns = [
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
