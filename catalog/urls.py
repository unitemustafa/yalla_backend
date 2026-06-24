from django.urls import path

from .views import (
    AdditionClassificationCreateView,
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
