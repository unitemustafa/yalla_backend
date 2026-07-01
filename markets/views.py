from django.db.models import ProtectedError
from django.db.models import Count, Max, Min, Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from catalog.models import Product, ProductVariant
from offers.models import Offer

from .models import Market, MarketClassification
from .serializers import (
    AdminMarketClassificationSerializer,
    AdminMarketSerializer,
    HomeMarketClassificationSerializer,
    HomeOfferSerializer,
    HomeProductSerializer,
    MarketClassificationCountSerializer,
    MarketWithCommonProductsSerializer,
    ProductDetailSerializer,
    StoreMarketClassificationSerializer,
)
from .services import markets_covering_address


class IsAdminRole(BasePermission):
    message = "Only admin users can manage markets."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsClientRole(BasePermission):
    message = "Only client users can access address products."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.CLIENT
        )


def get_user_home_address(user):
    return (
        user.addresses.filter(is_default=True).order_by("-created_at").first()
        or user.addresses.order_by("-created_at").first()
    )


class ProductSearchPagination(PageNumberPagination):
    page_size = 4


class AddressProductPagination(PageNumberPagination):
    page_size = 4


class AdminMarketClassificationListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        classifications = MarketClassification.objects.order_by("name", "id")
        return Response(
            AdminMarketClassificationSerializer(classifications, many=True).data
        )

    def post(self, request):
        serializer = AdminMarketClassificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            AdminMarketClassificationSerializer(classification).data,
            status=status.HTTP_201_CREATED,
        )


class AdminMarketClassificationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_classification(self, classification_id):
        return get_object_or_404(MarketClassification, id=classification_id)

    def get(self, request, classification_id):
        classification = self.get_classification(classification_id)
        return Response(AdminMarketClassificationSerializer(classification).data)

    def patch(self, request, classification_id):
        classification = self.get_classification(classification_id)
        serializer = AdminMarketClassificationSerializer(
            classification,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(AdminMarketClassificationSerializer(classification).data)

    def delete(self, request, classification_id):
        classification = self.get_classification(classification_id)
        try:
            classification.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete market classification while markets "
                        "are using it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminMarketListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        markets = (
            Market.objects.select_related("classification")
            .prefetch_related("delivery_areas")
            .order_by("name", "id")
        )
        return Response(AdminMarketSerializer(markets, many=True).data)

    def post(self, request):
        serializer = AdminMarketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        market = serializer.save()
        return Response(
            AdminMarketSerializer(market).data,
            status=status.HTTP_201_CREATED,
        )


class AdminMarketDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_market(self, market_id):
        return get_object_or_404(
            Market.objects.select_related("classification").prefetch_related(
                "delivery_areas"
            ),
            id=market_id,
        )

    def get(self, request, market_id):
        market = self.get_market(market_id)
        return Response(AdminMarketSerializer(market).data)

    def patch(self, request, market_id):
        market = self.get_market(market_id)
        serializer = AdminMarketSerializer(
            market,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        market = serializer.save()
        return Response(AdminMarketSerializer(market).data)

    def delete(self, request, market_id):
        market = self.get_market(market_id)
        try:
            market.delete()
        except ProtectedError:
            return Response(
                {"detail": "Cannot delete market while orders are using it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                "market__delivery_areas",
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
                "market__delivery_areas",
                Prefetch(
                    "products",
                    queryset=Product.objects.filter(
                        market_id__in=market_ids,
                    )
                    .select_related(
                        "category__classification",
                        "market__classification",
                    )
                    .prefetch_related("variants", "market__delivery_areas"),
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
            MarketClassification.objects.filter(markets__id__in=market_ids)
            .annotate(
                product_count=Count(
                    "markets__products",
                    filter=Q(markets__id__in=market_ids),
                    distinct=True,
                )
            )
            .distinct()
            .order_by("name")
        )
        markets_by_classification = {
            classification.id: list(
                Market.objects.filter(
                    id__in=market_ids,
                    classification=classification,
                    status=Market.Status.ACTIVE,
                )
                .annotate(
                    product_count=Count(
                        "products",
                        distinct=True,
                    )
                )
                .prefetch_related("delivery_areas")
                .order_by("-product_count", "name", "id")[:5]
            )
            for classification in all_classifications
        }
        market_ids_for_response = [
            market.id
            for markets in markets_by_classification.values()
            for market in markets
        ]
        products_by_market = {
            market_id: list(
                Product.objects.filter(
                    market_id=market_id,
                    market__status=Market.Status.ACTIVE,
                )
                .select_related("category__classification")
                .order_by("-created_at", "-id")
            )
            for market_id in market_ids_for_response
        }
        serializer_context = {
            "request": request,
            "markets_by_classification": markets_by_classification,
            "products_by_market": products_by_market,
        }

        return Response(
            {
                "common_market_classifications": MarketClassificationCountSerializer(
                    common_classifications,
                    many=True,
                ).data,
                "market_classifications": StoreMarketClassificationSerializer(
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
            .prefetch_related("delivery_areas")
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
                "market__delivery_areas",
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


class AddressProductListView(APIView):
    permission_classes = [IsAuthenticated, IsClientRole]
    pagination_class = AddressProductPagination
    sort_params = (
        "order_by_name",
        "order_by_high_price",
        "order_by_low_price",
        "order_by_latest",
    )

    def get_sort_param(self, request):
        selected_params = [
            param
            for param in self.sort_params
            if request.query_params.get(param, "").lower() in {"1", "true", "yes"}
        ]
        if len(selected_params) > 1:
            return None, Response(
                {"detail": "Use only one order parameter at a time."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return selected_params[0] if selected_params else "order_by_latest", None

    def apply_ordering(self, products, sort_param):
        products = products.annotate(
            lowest_variant_price=Min("variants__price"),
            highest_variant_price=Max("variants__price"),
        )
        ordering = {
            "order_by_name": ("name", "id"),
            "order_by_high_price": ("-highest_variant_price", "-created_at", "-id"),
            "order_by_low_price": ("lowest_variant_price", "-created_at", "-id"),
            "order_by_latest": ("-created_at", "-id"),
        }
        return products.order_by(*ordering[sort_param])

    def get(self, request):
        address = get_user_home_address(request.user)
        if address is None:
            return Response(
                {
                    "detail": (
                        "A user address is required before loading address products."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sort_param, error_response = self.get_sort_param(request)
        if error_response is not None:
            return error_response

        market_ids = markets_covering_address(address)
        products = (
            Product.objects.filter(
                market_id__in=market_ids,
                market__status=Market.Status.ACTIVE,
                is_available=True,
            )
            .select_related(
                "category__classification",
                "market__classification",
            )
            .prefetch_related(
                "market__delivery_areas",
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.order_by("price", "id"),
                ),
            )
            .distinct()
        )
        products = self.apply_ordering(products, sort_param)

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
                "market__delivery_areas",
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
