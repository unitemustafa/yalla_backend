from django.urls import include, path


app_name = "v2"

urlpatterns = [
    path("auth/", include("accounts.urls")),
    path("catalog/", include("catalog.urls")),
    path("home/", include("markets.urls")),
    path("market-region/", include("markets.region_urls")),
    path("offers/", include("offers.urls")),
    path("orders/", include("orders.urls")),
    path("admin/", include("orders.admin_urls")),
    path("courier/", include("orders.courier_urls")),
    path("notifications/", include("notifications.urls")),
    path("partners/", include("partners.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("addresses/", include("locations.address_urls")),
    path("locations/", include("locations.urls")),
]
