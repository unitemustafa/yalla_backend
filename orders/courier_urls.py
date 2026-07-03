from django.urls import path

from .views import (
    CourierOrderDetailView,
    CourierOrderListView,
    CourierOrderStatusView,
)

urlpatterns = [
    path("orders/", CourierOrderListView.as_view(), name="courier-order-list"),
    path(
        "orders/<int:order_id>/",
        CourierOrderDetailView.as_view(),
        name="courier-order-detail",
    ),
    path(
        "orders/<int:order_id>/status/",
        CourierOrderStatusView.as_view(),
        name="courier-order-status",
    ),
]
