from django.urls import path, include

urlpatterns = [
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/catalog/", include("catalog.urls")),
    path("api/v1/home/", include("markets.urls")),
    path("api/v1/offers/", include("offers.urls")),
    path("api/v1/orders/", include("orders.urls")),
]
