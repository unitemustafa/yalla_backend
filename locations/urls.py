from django.urls import path

from .views import (
    AddressDefaultView,
    AddressDetailView,
    AddressListCreateView,
    AddressSetDefaultView,
    DeliveryAreaListView,
)

urlpatterns = [
    path("delivery-areas/", DeliveryAreaListView.as_view(), name="delivery-areas"),
    path("addresses/", AddressListCreateView.as_view(), name="addresses"),
    path("addresses/default/", AddressDefaultView.as_view(), name="default-address"),
    path("addresses/<int:address_id>/", AddressDetailView.as_view(), name="address-detail"),
    path(
        "addresses/<int:address_id>/default/",
        AddressSetDefaultView.as_view(),
        name="address-set-default",
    ),
]
