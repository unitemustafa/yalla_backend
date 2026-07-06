from django.urls import path

from .views import (
    AddressProductListView,
    AdminMarketClassificationDetailView,
    AdminMarketClassificationListCreateView,
    AdminMarketDetailView,
    AdminMarketListCreateView,
    HomeView,
    LoginDashboardSnapshotView,
    FeaturedMarketClassificationSummaryView,
    MarketClassificationMarketsView,
    MarketClassificationSummaryView,
    NormalMarketClassificationSummaryView,
    PopularMarketClassificationSummaryView,
    ProductDetailView,
    ProductSearchView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path(
        "login-dashboard-snapshot/",
        LoginDashboardSnapshotView.as_view(),
        name="login-dashboard-snapshot",
    ),
    path(
        "market-classifications/",
        AdminMarketClassificationListCreateView.as_view(),
        name="admin-market-classification-list-create",
    ),
    path(
        "market-classifications/<int:classification_id>/",
        AdminMarketClassificationDetailView.as_view(),
        name="admin-market-classification-detail",
    ),
    path(
        "markets/",
        AdminMarketListCreateView.as_view(),
        name="admin-market-list-create",
    ),
    path(
        "markets/<int:market_id>/",
        AdminMarketDetailView.as_view(),
        name="admin-market-detail",
    ),
    path("search/", ProductSearchView.as_view(), name="product-search"),
    path("products/", AddressProductListView.as_view(), name="address-product-list"),
    path(
        "products/<int:product_id>/",
        ProductDetailView.as_view(),
        name="product-detail",
    ),
    path(
        "classifications/",
        MarketClassificationSummaryView.as_view(),
        name="market-classification-summary",
    ),
    path(
        "classifications/featured/",
        FeaturedMarketClassificationSummaryView.as_view(),
        name="market-classification-featured",
    ),
    path(
        "classifications/popular/",
        PopularMarketClassificationSummaryView.as_view(),
        name="market-classification-popular",
    ),
    path(
        "classifications/normal/",
        NormalMarketClassificationSummaryView.as_view(),
        name="market-classification-normal",
    ),
    path(
        "classifications/<int:classification_id>/markets/",
        MarketClassificationMarketsView.as_view(),
        name="market-classification-markets",
    ),
]
