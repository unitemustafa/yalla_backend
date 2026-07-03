from django.urls import path

from .views import (
    AdminOrderApproveView,
    AdminOrderRejectView,
    AdminOrderReviewBlockerView,
    AdminOrderServiceCityRepresentativesView,
)

urlpatterns = [
    path(
        "order-review/blocker/",
        AdminOrderReviewBlockerView.as_view(),
        name="admin-order-review-blocker",
    ),
    path(
        "orders/<int:order_id>/approve/",
        AdminOrderApproveView.as_view(),
        name="admin-order-approve",
    ),
    path(
        "orders/<int:order_id>/reject/",
        AdminOrderRejectView.as_view(),
        name="admin-order-reject",
    ),
    path(
        "orders/<int:order_id>/service-city-representatives/",
        AdminOrderServiceCityRepresentativesView.as_view(),
        name="admin-order-service-city-representatives",
    ),
]
