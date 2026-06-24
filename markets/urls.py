from django.urls import path

from .views import (
    HomeView,
    MarketClassificationMarketsView,
    MarketClassificationSummaryView,
    ProductDetailView,
    ProductSearchView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
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
