from django.urls import path

from .views import DeliveryAreaListView

urlpatterns = [
    path("delivery-areas/", DeliveryAreaListView.as_view(), name="delivery-areas"),
]
