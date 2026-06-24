from django.urls import path

from .views import AdditionClassificationCreateView

urlpatterns = [
    path(
        "addition-classifications/",
        AdditionClassificationCreateView.as_view(),
        name="addition-classification-create",
    ),
]
