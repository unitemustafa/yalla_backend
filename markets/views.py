from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductVariant
from offers.models import Offer

from .models import Market, MarketClassification
from .serializers import (
    HomeMarketClassificationSerializer,
    HomeOfferSerializer,
    HomeProductSerializer,
    MarketClassificationCountSerializer,
    MarketClassificationWithProductsSerializer,
    MarketWithCommonProductsSerializer,
    ProductDetailSerializer,
)
from .services import markets_covering_address


def get_user_home_address(user):
    return (
        user.addresses.filter(is_default=True).order_by("-created_at").first()
        or user.addresses.order_by("-created_at").first()
    )


class ProductSearchPagination(PageNumberPagination):
    page_size = 10


class HomeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address = get_user_home_address(request.user)
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


class MarketClassificationSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address = get_user_home_address(request.user)
        if address is None:
            return Response(
                {
                    "detail": (
                        "A user address is required before loading market "
                        "classifications."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        market_ids = markets_covering_address(address)
        common_classifications = (
            MarketClassification.objects.filter(markets__id__in=market_ids)
            .annotate(
                product_count=Count(
                    "markets__products",
                    filter=Q(markets__id__in=market_ids),
                    distinct=True,
                )
            )
            .distinct()
            .order_by("-product_count", "name")[:4]
        )
        all_classifications = (
            MarketClassification.objects.annotate(
                product_count=Count(
                    "markets__products",
                    filter=Q(markets__status=Market.Status.ACTIVE),
                    distinct=True,
                )
            )
            .distinct()
            .order_by("name")
        )
        products_by_classification = {
            classification.id: list(
                Product.objects.filter(
                    market__classification=classification,
                    market__status=Market.Status.ACTIVE,
                )
                .select_related(
                    "category__classification",
                    "market__classification",
                )
                .prefetch_related(
                    Prefetch(
                        "variants",
                        queryset=ProductVariant.objects.order_by("price", "id"),
                    )
                )
                .order_by("-created_at", "-id")[:3]
            )
            for classification in all_classifications
        }
        serializer_context = {
            "request": request,
            "products_by_classification": products_by_classification,
        }

        return Response(
            {
                "common_categories": MarketClassificationCountSerializer(
                    common_classifications,
                    many=True,
                ).data,
                "market_classifications": MarketClassificationWithProductsSerializer(
                    all_classifications,
                    many=True,
                    context=serializer_context,
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class MarketClassificationMarketsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, classification_id):
        classification = get_object_or_404(
            MarketClassification,
            id=classification_id,
        )
        address = get_user_home_address(request.user)
        if address is None:
            return Response(
                {
                    "detail": (
                        "A user address is required before loading "
                        "classification markets."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        market_ids = markets_covering_address(address)
        markets = (
            Market.objects.filter(
                id__in=market_ids,
                classification=classification,
                status=Market.Status.ACTIVE,
            )
            .distinct()
            .order_by("name", "id")
        )
        products_by_market = {
            market.id: list(
                Product.objects.filter(market=market)
                .select_related("category__classification")
                .order_by("-created_at", "-id")[:3]
            )
            for market in markets
        }

        return Response(
            {
                "classification": {
                    "id": classification.id,
                    "name": classification.name,
                },
                "markets": MarketWithCommonProductsSerializer(
                    markets,
                    many=True,
                    context={
                        "request": request,
                        "products_by_market": products_by_market,
                    },
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ProductSearchView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = ProductSearchPagination

    def get(self, request):
        address = get_user_home_address(request.user)
        if address is None:
            return Response(
                {
                    "detail": (
                        "A user address is required before searching products."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        market_ids = markets_covering_address(address)
        search_query = request.query_params.get("q", "").strip()
        products = Product.objects.filter(
            market_id__in=market_ids,
            market__status=Market.Status.ACTIVE,
        )
        if search_query:
            products = products.filter(
                Q(name__icontains=search_query)
                | Q(category__name__icontains=search_query)
                | Q(category__classification__name__icontains=search_query)
                | Q(market__name__icontains=search_query)
                | Q(market__classification__name__icontains=search_query)
            )

        products = (
            products.select_related(
                "category__classification",
                "market__classification",
            )
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.order_by("price", "id"),
                )
            )
            .distinct()
            .order_by("-created_at", "-id")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(products, request, view=self)
        serializer = HomeProductSerializer(
            page,
            many=True,
            context={"request": request},
        )
        return paginator.get_paginated_response(serializer.data)


class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        address = get_user_home_address(request.user)
        if address is None:
            return Response(
                {
                    "detail": (
                        "A user address is required before loading product "
                        "details."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        market_ids = markets_covering_address(address)
        product = get_object_or_404(
            Product.objects.filter(
                id=product_id,
                market_id__in=market_ids,
                market__status=Market.Status.ACTIVE,
            )
            .select_related(
                "category__classification",
                "market__classification",
            )
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.prefetch_related(
                        "attribute_values__attribute",
                        "attribute_values__option",
                    ).order_by("price", "id"),
                ),
                "attribute_values__attribute",
                "attribute_values__option",
                "additions__classification",
            )
        )
        serializer = ProductDetailSerializer(
            product,
            context={"request": request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
