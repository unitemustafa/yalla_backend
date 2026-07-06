from django.urls import path

from .views import (
    ClientOrderCreateView,
    ClientOrderListView,
    OrderAssignmentView,
    OrderDetailView,
    OrderDeliveryPriceView,
    OrderListCreateView,
    OrderPreviewView,
    OrderStatusView,
)

urlpatterns = [
    path("my/", ClientOrderListView.as_view(), name="client-order-list"),
    path("preview/", OrderPreviewView.as_view(), name="order-preview"),
    path("create/", ClientOrderCreateView.as_view(), name="client-order-create"),
    path("", OrderListCreateView.as_view(), name="order-list-create"),
    path("<int:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("<int:order_id>/status/", OrderStatusView.as_view(), name="order-status"),
    path(
        "<int:order_id>/delivery-price/",
        OrderDeliveryPriceView.as_view(),
        name="order-delivery-price",
    ),
    path(
        "<int:order_id>/assignment/",
        OrderAssignmentView.as_view(),
        name="order-assignment",
    ),
]
