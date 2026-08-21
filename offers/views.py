import logging
import uuid

from django.db.models import Exists, OuterRef, ProtectedError, Q
from django.utils import timezone

from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from config.pagination import paginated_list_response
from markets.region import (
    current_market_region_selection,
    no_market_region_selection_response,
    visible_offer_queryset,
)
from markets.serializers import HomeOfferSerializer

from .models import Offer
from .images import OfferImageStorageError, replace_offer_image
from .serializers import AdminOfferSerializer, OfferImageUploadSerializer


logger = logging.getLogger(__name__)


class OfferListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        protected_offers = Offer.objects.filter(pk=OuterRef("pk")).filter(
            Q(order_offers__isnull=False)
            | Q(notification_dispatches__isnull=False)
        )
        return (
            Offer.objects.annotate(
                deletion_mode_is_archive=Exists(protected_offers),
            ).select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__delivery_areas",
                "market__service_cities",
                "service_cities",
                "products__market",
                "products__images",
                "items__variant__product__market__classification",
                "items__variant__product__market__service_cities",
                "items__variant__product__market__delivery_areas",
                "items__variant__product__attributes__options",
                "items__variant__product__images",
                "items__variant__attribute_values__attribute",
                "items__variant__attribute_values__option",
                "items__variant__attribute_values__product_attribute",
                "items__variant__attribute_values__product_attribute_option",
            )
            .order_by("-announcement_priority", "-created_at", "-id")
        )

    def get(self, request):
        if request.user.role == User.Role.ADMIN:
            queryset = self.get_queryset()
            if request.query_params.get("archived") in {"true", "1"}:
                queryset = queryset.filter(archived_at__isnull=False)
            else:
                queryset = queryset.filter(archived_at__isnull=True)
            return paginated_list_response(
                request,
                queryset,
                AdminOfferSerializer,
            )
        if request.user.role != User.Role.CLIENT:
            raise PermissionDenied("Only admin or client users can access offers.")
        if current_market_region_selection(request.user) is None:
            return no_market_region_selection_response()

        offers = (
            visible_offer_queryset(request.user)
            .select_related("market__classification")
            .prefetch_related(
                "market__service_cities",
                "market__delivery_areas",
                "service_cities",
                "products__category__classification",
                "products__market__classification",
                "products__market__service_cities",
                "products__market__delivery_areas",
                "products__variants",
                "products__images",
                "items__variant__product__market__classification",
                "items__variant__product__market__service_cities",
                "items__variant__product__market__delivery_areas",
                "items__variant__product__attributes__options",
                "items__variant__product__images",
                "items__variant__attribute_values__attribute",
                "items__variant__attribute_values__option",
                "items__variant__attribute_values__product_attribute",
                "items__variant__attribute_values__product_attribute_option",
            )
            .order_by("-announcement_priority", "-created_at", "-id")
        )
        return paginated_list_response(
            request,
            offers,
            HomeOfferSerializer,
        )

    def post(self, request):
        self._require_admin(request)
        serializer = AdminOfferSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        offer = serializer.save()
        offer = self.get_queryset().get(id=offer.id)
        return Response(
            AdminOfferSerializer(
                offer,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _require_admin(request):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only admin users can manage offers.")


class OfferDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Offer.objects.select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__delivery_areas",
                "market__service_cities",
                "service_cities",
                "products__market",
                "products__images",
                "items__variant__product__market__classification",
                "items__variant__product__market__service_cities",
                "items__variant__product__market__delivery_areas",
                "items__variant__product__attributes__options",
                "items__variant__product__images",
                "items__variant__attribute_values__attribute",
                "items__variant__attribute_values__option",
                "items__variant__attribute_values__product_attribute",
                "items__variant__attribute_values__product_attribute_option",
            )
        )

    def get_offer(self, offer_id):
        return get_object_or_404(self.get_queryset(), id=offer_id)

    def get(self, request, offer_id):
        if request.user.role == User.Role.CLIENT:
            if current_market_region_selection(request.user) is None:
                return no_market_region_selection_response()
            offer = get_object_or_404(
                visible_offer_queryset(request.user)
                .select_related("market__classification")
                .prefetch_related(
                    "market__service_cities",
                    "market__delivery_areas",
                    "service_cities",
                    "products__category__classification",
                    "products__market__classification",
                    "products__market__service_cities",
                    "products__market__delivery_areas",
                    "products__variants",
                    "products__images",
                    "items__variant__product__market__classification",
                    "items__variant__product__market__service_cities",
                    "items__variant__product__market__delivery_areas",
                    "items__variant__product__attributes__options",
                    "items__variant__product__images",
                    "items__variant__attribute_values__attribute",
                    "items__variant__attribute_values__option",
                    "items__variant__attribute_values__product_attribute",
                    "items__variant__attribute_values__product_attribute_option",
                ),
                id=offer_id,
            )
            return Response(
                HomeOfferSerializer(offer, context={"request": request}).data
            )
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only admin or client users can access offers.")
        offer = self.get_offer(offer_id)
        return Response(
            AdminOfferSerializer(
                offer,
                context={"request": request},
            ).data
        )

    def patch(self, request, offer_id):
        self._require_admin(request)
        if request.FILES.get("image") and set(request.data.keys()) == {"image"}:
            return update_offer_image_response(request, offer_id)
        offer = self.get_offer(offer_id)
        if request.data.get("restore") is True:
            offer.archived_at = None
            offer.save(update_fields=("archived_at", "updated_at"))
            offer = self.get_queryset().get(id=offer.id)
            return Response(
                AdminOfferSerializer(
                    offer,
                    context={"request": request},
                ).data
            )
        serializer = AdminOfferSerializer(
            offer,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        offer = serializer.save()
        offer = self.get_queryset().get(id=offer.id)
        return Response(
            AdminOfferSerializer(
                offer,
                context={"request": request},
            ).data
        )

    def delete(self, request, offer_id):
        self._require_admin(request)
        offer = self.get_offer(offer_id)
        try:
            offer.delete()
        except ProtectedError:
            offer.status = Offer.Status.INACTIVE
            offer.archived_at = timezone.now()
            offer.save(update_fields=("status", "archived_at", "updated_at"))
            return Response(
                {
                    "action": "archived",
                    "detail": (
                        "تمت أرشفة العرض بدلًا من حذفه لأنه مرتبط "
                        "بسجل طلبات سابق."
                    ),
                },
                status=status.HTTP_200_OK,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _require_admin(request):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only admin users can manage offers.")


class OfferImageUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, offer_id):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only admin users can manage offers.")
        return update_offer_image_response(request, offer_id)


def update_offer_image_response(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    serializer = OfferImageUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    request_id = str(uuid.uuid4())
    try:
        replace_offer_image(offer.id, serializer.validated_data["image"])
    except OfferImageStorageError:
        logger.exception(
            "Offer image storage failed offer_id=%s request_id=%s",
            offer.id,
            request_id,
        )
        return Response(
            {
                "detail": "تعذر رفع صورة العرض إلى خدمة الصور. حاول مرة أخرى.",
                "code": "offer_image_storage_unavailable",
                "request_id": request_id,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    offer = OfferDetailView().get_queryset().get(id=offer.id)
    return Response(
        AdminOfferSerializer(
            offer,
            context={"request": request},
        ).data,
        status=status.HTTP_200_OK,
    )


class OfferSendNotificationView(APIView):
    permission_classes = [IsAuthenticated]
    rate_limit_scopes = ("notification_send_user",)

    def post(self, request, offer_id):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only admin users can manage offers.")
        request_id = serializers.UUIDField().run_validation(request.data.get("request_id"))
        from notifications.offer_services import dispatch_offer_notifications

        try:
            dispatch = dispatch_offer_notifications(
                offer_id,
                request_id,
                request.user.id,
            )
        except serializers.ValidationError:
            raise
        except Exception:
            logger.exception(
                "Offer notification dispatch failed offer_id=%s request_id=%s "
                "requested_by_id=%s",
                offer_id,
                request_id,
                request.user.id,
            )
            raise
        return Response({
            "dispatch_id": dispatch.id,
            "request_id": str(dispatch.request_id),
            "status": dispatch.status,
            "recipient_count": dispatch.recipient_count,
            "notification_count": dispatch.notification_count,
            "sent_at": dispatch.completed_at,
        })
