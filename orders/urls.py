from django.urls import path

from .views import (
    AdminOrderDetailView,
    AdminOrderStatusView,
    AdminOrdersView,
    AssignedOrdersView,
    DeliverOrderView,
    OrderAssignmentView,
    UserOrdersView,
)

urlpatterns = [
    path("", UserOrdersView.as_view(), name="user-orders"),
    path("admin/", AdminOrdersView.as_view(), name="admin-orders"),
    path("admin/<int:order_id>/", AdminOrderDetailView.as_view(), name="admin-order-detail"),
    path("admin/<int:order_id>/status/", AdminOrderStatusView.as_view(), name="admin-order-status"),
    path("assigned/", AssignedOrdersView.as_view(), name="assigned-orders"),
    path("<int:order_id>/assignment/", OrderAssignmentView.as_view(), name="order-assignment"),
    path("<int:order_id>/deliver/", DeliverOrderView.as_view(), name="deliver-order"),
]
