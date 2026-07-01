from django.urls import path

from .views import (
    ClientOrderListView,
    OrderAssignmentView,
    OrderDetailView,
    OrderListCreateView,
    OrderStatusView,
)

urlpatterns = [
    path("my/", ClientOrderListView.as_view(), name="client-order-list"),
    path("", OrderListCreateView.as_view(), name="order-list-create"),
    path("<int:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("<int:order_id>/status/", OrderStatusView.as_view(), name="order-status"),
    path(
        "<int:order_id>/assignment/",
        OrderAssignmentView.as_view(),
        name="order-assignment",
    ),
]
