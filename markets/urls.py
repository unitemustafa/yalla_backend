from django.urls import path

from .views import (
    AdminMarketClassificationDetailView,
    AdminMarketClassificationListCreateView,
    AdminMarketDetailView,
    AdminMarketListCreateView,
    HomeView,
    MarketClassificationMarketsView,
    MarketClassificationSummaryView,
    ProductDetailView,
    ProductSearchView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
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
        "classifications/<int:classification_id>/markets/",
        MarketClassificationMarketsView.as_view(),
        name="market-classification-markets",
    ),
]
