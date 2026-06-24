from django.urls import path

from .views import UserOrdersView

urlpatterns = [
    path("", UserOrdersView.as_view(), name="user-orders"),
]
