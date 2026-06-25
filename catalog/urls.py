from django.urls import path

from .views import (
    AdditionClassificationCreateView,
    CategoryClassificationDetailView,
    CategoryClassificationListCreateView,
    ProductCategoryDetailView,
    ProductCategoryListCreateView,
    ProductAdditionDetailView,
    ProductAdditionListCreateView,
)

urlpatterns = [
    path(
        "addition-classifications/",
        AdditionClassificationCreateView.as_view(),
        name="addition-classification-create",
    ),
    path(
        "category-classifications/",
        CategoryClassificationListCreateView.as_view(),
        name="category-classification-list-create",
    ),
    path(
        "category-classifications/<int:classification_id>/",
        CategoryClassificationDetailView.as_view(),
        name="category-classification-detail",
    ),
    path(
        "product-categories/",
        ProductCategoryListCreateView.as_view(),
        name="product-category-list-create",
    ),
    path(
        "product-categories/<int:category_id>/",
        ProductCategoryDetailView.as_view(),
        name="product-category-detail",
    ),
    path(
        "product-additions/",
        ProductAdditionListCreateView.as_view(),
        name="product-addition-list-create",
    ),
    path(
        "product-additions/<int:addition_id>/",
        ProductAdditionDetailView.as_view(),
        name="product-addition-detail",
    ),
]
