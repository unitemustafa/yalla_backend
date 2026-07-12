from datetime import datetime, time, timedelta

from django.db.models import ProtectedError
from django.db.models import Count, Max, Min, Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from catalog.models import Product, ProductAddition, ProductVariant
from dashboard.models import DashboardSettings
from locations.models import DeliveryArea, ServiceCity
from orders.models import Order

from .models import Market, MarketClassification
from .region import (
    current_market_region_selection,
    no_market_region_selection_response,
    visible_market_queryset,
    visible_offer_queryset,
    visible_product_queryset,
)
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


class LoginDashboardSnapshotView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        dashboard_settings, _ = DashboardSettings.objects.get_or_create(pk=1)
        logo_url = None
        if dashboard_settings.logo:
            try:
                logo_url = request.build_absolute_uri(dashboard_settings.logo.url)
            except ValueError:
                logo_url = None
        local_today = timezone.localdate()
        current_timezone = timezone.get_current_timezone()
        start_of_day = timezone.make_aware(
            datetime.combine(local_today, time.min),
            current_timezone,
        )
        end_of_day = start_of_day + timedelta(days=1)

        return Response(
            {
                "todayOrders": Order.objects.filter(
                    created_at__gte=start_of_day,
                    created_at__lt=end_of_day,
                ).count(),
                "availableCities": ServiceCity.objects.filter(is_active=True).count(),
                "deliveryZones": DeliveryArea.objects.filter(is_active=True).count(),
                "branding": {
                    "brandName": dashboard_settings.brand_name,
                    "brandTagline": dashboard_settings.brand_tagline,
                    "logoUrl": logo_url,
                    "fontFamily": dashboard_settings.font_family,
                    "primaryColor": dashboard_settings.primary_color,
                    "subtleColor": dashboard_settings.subtle_color,
                    "accentColor": dashboard_settings.accent_color,
                },
            },
            status=status.HTTP_200_OK,
        )


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
            .prefetch_related("service_cities", "delivery_areas")
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
                "service_cities",
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
        current_selection = current_market_region_selection(request.user)
        if current_selection is None:
            return no_market_region_selection_response()

        address = get_user_home_address(request.user)
        market_ids = list(
            visible_market_queryset(request.user).values_list("id", flat=True)
        )

        products = (
            Product.objects.filter(market_id__in=market_ids)
            .filter(is_available=True, is_popular=True)
            .select_related("market__classification")
            .prefetch_related(
                "market__service_cities",
                "market__delivery_areas",
                "attributes__options",
                "images",
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.order_by("price", "id"),
                )
            )
            .order_by("-created_at", "-id")[:8]
        )
        offers = (
            visible_offer_queryset(request.user)
            .select_related("market__classification")
            .prefetch_related(
                "market__service_cities",
                "market__delivery_areas",
                "service_cities",
                Prefetch(
                    "products",
                    queryset=Product.objects.filter(
                        market_id__in=market_ids,
                    )
                    .select_related(
                        "market__classification",
                    )
                    .prefetch_related(
                        "variants",
                        "attributes__options",
                        "images",
                        "market__service_cities",
                        "market__delivery_areas",
                    ),
                )
            )
            .order_by("-created_at", "-id")
        )
        classifications = (
            MarketClassification.objects.filter(
                markets__id__in=market_ids,
                is_active=True,
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
                "current_selection": current_selection,
                "location": {
                    "address_id": address.id,
                    "name": address.name,
                    "latitude": address.latitude,
                    "longitude": address.longitude,
                }
                if address is not None
                else None,
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
    classification_type = None

    def get(self, request):
        current_selection = current_market_region_selection(request.user)
        if current_selection is None:
            return no_market_region_selection_response()

        market_ids = list(
            visible_market_queryset(request.user).values_list("id", flat=True)
        )
        classification_filters = {
            "markets__id__in": market_ids,
            "is_active": True,
        }
        if self.classification_type is not None:
            classification_filters["classification_type"] = self.classification_type

        common_classifications = (
            MarketClassification.objects.filter(**classification_filters)
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
            MarketClassification.objects.filter(**classification_filters)
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
                .prefetch_related("service_cities", "delivery_areas")
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
                .select_related("market__classification")
                .prefetch_related("images")
                .order_by("-created_at", "-id")
            )
            for market_id in market_ids_for_response
        }
        serializer_context = {
            "request": request,
            "markets_by_classification": markets_by_classification,
            "products_by_market": products_by_market,
        }

        if self.classification_type is not None:
            return Response(
                {
                    "current_selection": current_selection,
                    "classifications": StoreMarketClassificationSerializer(
                        all_classifications,
                        many=True,
                        context=serializer_context,
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

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


class FeaturedMarketClassificationSummaryView(MarketClassificationSummaryView):
    classification_type = MarketClassification.ClassificationType.FEATURED


class PopularMarketClassificationSummaryView(MarketClassificationSummaryView):
    classification_type = MarketClassification.ClassificationType.POPULAR


class NormalMarketClassificationSummaryView(MarketClassificationSummaryView):
    classification_type = MarketClassification.ClassificationType.NORMAL


class MarketClassificationMarketsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, classification_id):
        if current_market_region_selection(request.user) is None:
            return no_market_region_selection_response()

        classification = get_object_or_404(
            MarketClassification,
            id=classification_id,
            is_active=True,
        )
        market_ids = list(
            visible_market_queryset(request.user).values_list("id", flat=True)
        )
        markets = (
            Market.objects.filter(
                id__in=market_ids,
                classification=classification,
                status=Market.Status.ACTIVE,
            )
            .distinct()
            .prefetch_related("service_cities", "delivery_areas")
            .order_by("name", "id")
        )
        products_by_market = {
            market.id: list(
                Product.objects.filter(market=market)
                .select_related("market__classification")
                .prefetch_related("images")
                .order_by("-created_at", "-id")[:3]
            )
            for market in markets
        }

        return Response(
            {
                "classification": {
                    "id": classification.id,
                    "name": classification.name,
                    "classification_type": classification.classification_type,
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
        if current_market_region_selection(request.user) is None:
            return no_market_region_selection_response()

        search_query = request.query_params.get("q", "").strip()
        products = visible_product_queryset(request.user).filter(
            market__status=Market.Status.ACTIVE,
        )
        if search_query:
            products = products.filter(
                Q(name__icontains=search_query)
                | Q(market__name__icontains=search_query)
                | Q(market__classification__name__icontains=search_query)
            )

        products = (
            products.select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__service_cities",
                "market__delivery_areas",
                "attributes__options",
                "images",
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
        if current_market_region_selection(request.user) is None:
            return no_market_region_selection_response()

        sort_param, error_response = self.get_sort_param(request)
        if error_response is not None:
            return error_response

        products = (
            visible_product_queryset(request.user)
            .filter(
                market__status=Market.Status.ACTIVE,
                is_available=True,
            )
            .select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__service_cities",
                "market__delivery_areas",
                "attributes__options",
                "images",
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
        if current_market_region_selection(request.user) is None:
            return no_market_region_selection_response()

        product = get_object_or_404(
            visible_product_queryset(request.user)
            .filter(
                id=product_id,
                market__status=Market.Status.ACTIVE,
                is_available=True,
            )
            .select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__service_cities",
                "market__delivery_areas",
                "attributes__options",
                "images",
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.prefetch_related(
                        "attribute_values__attribute",
                        "attribute_values__option",
                        "attribute_values__product_attribute",
                        "attribute_values__product_attribute_option",
                    ).order_by("price", "id"),
                ),
                "attribute_values__attribute",
                "attribute_values__option",
                Prefetch(
                    "additions",
                    queryset=ProductAddition.objects.filter(
                        is_active=True,
                    ).select_related("classification"),
                ),
            )
        )
        serializer = ProductDetailSerializer(
            product,
            context={"request": request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
