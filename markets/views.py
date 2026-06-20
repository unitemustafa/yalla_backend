from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductVariant
from offers.models import Offer

from .models import MarketClassification
from .serializers import (
    HomeMarketClassificationSerializer,
    HomeOfferSerializer,
    HomeProductSerializer,
)
from .services import markets_covering_address


class HomeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address = (
            request.user.addresses.filter(is_default=True)
            .order_by("-created_at")
            .first()
            or request.user.addresses.order_by("-created_at").first()
        )
        if address is None:
            return Response(
                {
                    "detail": (
                        "A user address is required before loading the home page."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        market_ids = markets_covering_address(address)
        now = timezone.now()

        products = (
            Product.objects.filter(market_id__in=market_ids)
            .select_related("category__classification", "market__classification")
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.order_by("price", "id"),
                )
            )
            .order_by("-created_at", "-id")[:8]
        )
        offers = (
            Offer.objects.filter(
                market_id__in=market_ids,
                status=Offer.Status.ACTIVE,
                start_time__lte=now,
                end_time__gte=now,
            )
            .select_related("market__classification")
            .prefetch_related(
                Prefetch(
                    "products",
                    queryset=Product.objects.filter(
                        market_id__in=market_ids,
                    )
                    .select_related(
                        "category__classification",
                        "market__classification",
                    )
                    .prefetch_related("variants"),
                )
            )
            .order_by("-created_at", "-id")[:4]
        )
        classifications = (
            MarketClassification.objects.filter(
                markets__id__in=market_ids,
            )
            .distinct()
            .order_by("name")
        )

        serializer_context = {
            "request": request,
            "eligible_market_ids": market_ids,
        }
        return Response(
            {
                "location": {
                    "address_id": address.id,
                    "name": address.name,
                    "latitude": address.latitude,
                    "longitude": address.longitude,
                },
                "offers": HomeOfferSerializer(
                    offers,
                    many=True,
                    context=serializer_context,
                ).data,
                "market_classifications": HomeMarketClassificationSerializer(
                    classifications,
                    many=True,
                    context=serializer_context,
                ).data,
                "products": HomeProductSerializer(
                    products,
                    many=True,
                    context=serializer_context,
                ).data,
            },
            status=status.HTTP_200_OK,
        )
