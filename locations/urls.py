from django.urls import path

from .views import (
    AddressDefaultView,
    AddressDetailView,
    AddressListCreateView,
    AddressSetDefaultView,
    DeliveryAreaDetailView,
    DeliveryAreaListCreateView,
    PointResolveView,
    ServiceCityDetailView,
    ServiceCityListCreateView,
)

urlpatterns = [
    path("resolve-point/", PointResolveView.as_view(), name="resolve-point"),
    path(
        "service-cities/",
        ServiceCityListCreateView.as_view(),
        name="service-city-list-create",
    ),
    path(
        "service-cities/<int:city_id>/",
        ServiceCityDetailView.as_view(),
        name="service-city-detail",
    ),
    path(
        "delivery-areas/",
        DeliveryAreaListCreateView.as_view(),
        name="delivery-area-list-create",
    ),
    path(
        "delivery-areas/<int:area_id>/",
        DeliveryAreaDetailView.as_view(),
        name="delivery-area-detail",
    ),
    path("addresses/", AddressListCreateView.as_view(), name="addresses"),
    path("addresses/default/", AddressDefaultView.as_view(), name="default-address"),
    path("addresses/<int:address_id>/", AddressDetailView.as_view(), name="address-detail"),
    path(
        "addresses/<int:address_id>/default/",
        AddressSetDefaultView.as_view(),
        name="address-set-default",
    ),
]
