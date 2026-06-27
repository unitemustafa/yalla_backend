from django.urls import path

from .views import AddressDefaultView, AddressDetailView, AddressListCreateView, AddressSetDefaultView

urlpatterns = [
    path("", AddressListCreateView.as_view(), name="addresses-root"),
    path("default/", AddressDefaultView.as_view(), name="default-address-root"),
    path("<int:address_id>/", AddressDetailView.as_view(), name="address-detail-root"),
    path(
        "<int:address_id>/default/",
        AddressSetDefaultView.as_view(),
        name="address-set-default-root",
    ),
]
