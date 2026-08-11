from django.db.models import ProtectedError
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsMarketAdminRole
from config.pagination import paginated_list_response

from .models import Market, MarketClassification, MarketType
from .serializers import (
    AdminMarketClassificationSerializer,
    AdminMarketSerializer,
    MarketTypeSerializer,
)


class AdminMarketClassificationListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsMarketAdminRole]

    def get(self, request):
        classifications = MarketClassification.objects.order_by("name", "id")
        return paginated_list_response(
            request,
            classifications,
            AdminMarketClassificationSerializer,
        )

    def post(self, request):
        serializer = AdminMarketClassificationSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            AdminMarketClassificationSerializer(
                classification,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdminMarketClassificationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsMarketAdminRole]

    def get_classification(self, classification_id):
        return get_object_or_404(MarketClassification, id=classification_id)

    def get(self, request, classification_id):
        classification = self.get_classification(classification_id)
        return Response(
            AdminMarketClassificationSerializer(
                classification,
                context={"request": request},
            ).data
        )

    def patch(self, request, classification_id):
        classification = self.get_classification(classification_id)
        serializer = AdminMarketClassificationSerializer(
            classification,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            AdminMarketClassificationSerializer(
                classification,
                context={"request": request},
            ).data
        )

    def delete(self, request, classification_id):
        classification = self.get_classification(classification_id)
        try:
            classification.delete()
        except ProtectedError:
            classification.is_active = False
            classification.save(update_fields=("is_active",))
            return Response(
                {
                    "action": "archived",
                    "detail": (
                        "تمت أرشفة فئة المحل وتعطيلها لأنها مستخدمة "
                        "بواسطة محلات حالية."
                    ),
                },
                status=status.HTTP_200_OK,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMarketTypeListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsMarketAdminRole]

    def get(self, request):
        market_types = MarketType.objects.select_related(
            "classification"
        ).annotate(
            market_count=Count("markets", distinct=True)
        )
        classification_id = request.query_params.get("classification_id")
        if classification_id:
            market_types = market_types.filter(
                classification_id=classification_id
            )
        return paginated_list_response(
            request,
            market_types.order_by(
                "classification__name",
                "sort_order",
                "id",
            ),
            MarketTypeSerializer,
        )

    def post(self, request):
        serializer = MarketTypeSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        market_type = serializer.save()
        return Response(
            MarketTypeSerializer(
                market_type,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdminMarketTypeDetailView(APIView):
    permission_classes = [IsAuthenticated, IsMarketAdminRole]

    def get_market_type(self, market_type_id):
        return get_object_or_404(
            MarketType.objects.select_related("classification").annotate(
                market_count=Count("markets", distinct=True)
            ),
            id=market_type_id,
        )

    def get(self, request, market_type_id):
        return Response(
            MarketTypeSerializer(
                self.get_market_type(market_type_id),
                context={"request": request},
            ).data
        )

    def patch(self, request, market_type_id):
        serializer = MarketTypeSerializer(
            self.get_market_type(market_type_id),
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        market_type = serializer.save()
        return Response(
            MarketTypeSerializer(
                market_type,
                context={"request": request},
            ).data
        )

    def delete(self, request, market_type_id):
        self.get_market_type(market_type_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMarketListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsMarketAdminRole]

    def get(self, request):
        protected_markets = Market.objects.filter(pk=OuterRef("pk")).filter(
            Q(orders__isnull=False)
            | Q(order_sections__isnull=False)
            | Q(products__variants__order_items__isnull=False)
            | Q(products__variants__offer_items__isnull=False)
        )
        markets = (
            Market.objects.annotate(
                deletion_mode_is_archive=Exists(protected_markets),
            )
            .select_related("classification")
            .prefetch_related(
                "service_cities",
                "delivery_areas",
                "subcategory_assignments__subcategory",
                "market_types",
            )
            .order_by("name", "id")
        )
        if request.query_params.get("archived") in {"true", "1"}:
            markets = markets.filter(archived_at__isnull=False)
        else:
            markets = markets.filter(archived_at__isnull=True)
        return paginated_list_response(
            request,
            markets,
            AdminMarketSerializer,
        )

    def post(self, request):
        serializer = AdminMarketSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        market = serializer.save()
        return Response(
            AdminMarketSerializer(
                market,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdminMarketDetailView(APIView):
    permission_classes = [IsAuthenticated, IsMarketAdminRole]

    def get_market(self, market_id):
        return get_object_or_404(
            Market.objects.select_related("classification").prefetch_related(
                "service_cities",
                "delivery_areas",
                "subcategory_assignments__subcategory",
                "market_types",
            ),
            id=market_id,
        )

    def get(self, request, market_id):
        market = self.get_market(market_id)
        return Response(
            AdminMarketSerializer(
                market,
                context={"request": request},
            ).data
        )

    def patch(self, request, market_id):
        market = self.get_market(market_id)
        if request.data.get("restore") is True:
            market.archived_at = None
            market.save(update_fields=("archived_at", "updated_at"))
            return Response(
                AdminMarketSerializer(
                    market,
                    context={"request": request},
                ).data
            )
        serializer = AdminMarketSerializer(
            market,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        market = serializer.save()
        return Response(
            AdminMarketSerializer(
                market,
                context={"request": request},
            ).data
        )

    def delete(self, request, market_id):
        market = self.get_market(market_id)
        try:
            market.delete()
        except ProtectedError:
            market.status = Market.Status.INACTIVE
            market.archived_at = timezone.now()
            market.save(update_fields=("status", "archived_at", "updated_at"))
            return Response(
                {
                    "action": "archived",
                    "detail": (
                        "تمت أرشفة المحل بدلًا من حذفه لأنه مرتبط "
                        "بسجل طلبات سابق."
                    ),
                },
                status=status.HTTP_200_OK,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

