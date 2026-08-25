from django.urls import path

from .geocoding_views import (
    CityCoverageLookupView,
    GeocodingAutocompleteView,
    GeocodingReverseView,
)
from .views import (
    AddressDefaultView,
    AddressDetailView,
    AddressListCreateView,
    AddressSetDefaultView,
    DeliveryAreaDetailView,
    DeliveryAreaListCreateView,
    ServiceCityDetailView,
    ServiceCityListCreateView,
    ShippingCompanyDetailView,
    ShippingCompanyListCreateView,
)

urlpatterns = [
    path(
        "geocoding/autocomplete/",
        GeocodingAutocompleteView.as_view(),
        name="geocoding-autocomplete",
    ),
    path(
        "geocoding/reverse/",
        GeocodingReverseView.as_view(),
        name="geocoding-reverse",
    ),
    path(
        "service-cities/coverage-lookup/",
        CityCoverageLookupView.as_view(),
        name="service-city-coverage-lookup",
    ),
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
    path(
        "shipping-companies/",
        ShippingCompanyListCreateView.as_view(),
        name="shipping-company-list-create",
    ),
    path(
        "shipping-companies/<int:company_id>/",
        ShippingCompanyDetailView.as_view(),
        name="shipping-company-detail",
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
