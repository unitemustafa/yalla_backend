from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from .share_views import market_share, offer_share, product_share
from .health import liveness, readiness
from accounts.legal_views import (
    AccountDeletionView,
    PrivacyPolicyView,
    TermsOfUseView,
)

urlpatterns = [
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy-policy"),
    path("terms/", TermsOfUseView.as_view(), name="terms-of-use"),
    path(
        "account-deletion/",
        AccountDeletionView.as_view(),
        name="account-deletion",
    ),
    path("health/", liveness, name="health"),
    path("healthz/", liveness, name="healthz"),
    path("readyz/", readiness, name="readyz"),
    path("share/products/<int:product_id>/", product_share, name="product-share"),
    path("share/offers/<int:offer_id>/", offer_share, name="offer-share"),
    path("share/markets/<int:market_id>/", market_share, name="market-share"),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/catalog/", include("catalog.urls")),
    path("api/v1/home/", include("markets.urls")),
    path("api/v1/market-region/", include("markets.region_urls")),
    path("api/v1/offers/", include("offers.urls")),
    path("api/v1/orders/", include("orders.urls")),
    path("api/v1/admin/", include("orders.admin_urls")),
    path("api/v1/courier/", include("orders.courier_urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/partners/", include("partners.urls")),
    path("api/v1/dashboard/", include("dashboard.urls")),
    path("api/v1/addresses/", include("locations.address_urls")),
    path("api/v1/locations/", include("locations.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
