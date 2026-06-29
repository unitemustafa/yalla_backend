from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/catalog/", include("catalog.urls")),
    path("api/v1/home/", include("markets.urls")),
    path("api/v1/offers/", include("offers.urls")),
    path("api/v1/orders/", include("orders.urls")),
    path("api/v1/dashboard/", include("dashboard.urls")),
    path("api/v1/addresses/", include("locations.address_urls")),
    path("api/v1/locations/", include("locations.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
