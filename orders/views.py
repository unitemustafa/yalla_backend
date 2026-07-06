from django.contrib.auth import get_user_model
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CourierProfile
from .models import Order, OrderMarketSection
from .serializers import (
    AdminOrderCreateSerializer,
    ClientOrderCreateSerializer,
    CourierOrderDetailSerializer,
    CourierOrderListSerializer,
    CourierOrderStatusSerializer,
    OrderAssignmentSerializer,
    OrderDeliveryPriceSerializer,
    OrderPreviewSerializer,
    OrderReviewActionSerializer,
    OrderSerializer,
    OrderStatusSerializer,
    RepresentativeSummarySerializer,
)
from notifications.services import (
    create_order_assigned_notification,
    create_order_rejected_notification,
    resolve_order_review_notifications,
)

User = get_user_model()


class IsAdminRole(BasePermission):
    message = "Only admin users can manage orders."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.ADMIN


class IsClientRole(BasePermission):
    message = "Only client users can access their orders."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.CLIENT


class IsCourierRole(BasePermission):
    message = "Only courier users can access courier orders."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.REPRESENTATIVE
        )


def order_queryset():
    return (
        Order.objects.select_related(
            "user",
            "delivery_address",
            "delivery_address__service_city",
            "delivery_address__delivery_area",
            "delivery_address__delivery_area__service_city",
            "assigned_representative",
            "market",
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
            "approved_by",
            "rejected_by",
        )
        .prefetch_related(
            "items__variant__product",
            "items__variant__attribute_values__attribute",
            "items__variant__attribute_values__option",
            "items__section",
            "order_offers__offer",
            "order_offers__section",
            "market__service_cities",
            "market_sections__market",
            "market_sections__items__variant__product",
            "market_sections__items__variant__attribute_values__attribute",
            "market_sections__items__variant__attribute_values__option",
            "market_sections__offers__offer",
        )
        .order_by("-created_at", "-id")
    )


def active_available_representatives():
    return (
        User.objects.filter(
            role=User.Role.REPRESENTATIVE,
            is_active=True,
            deleted_at__isnull=True,
            courier_profile__is_available=True,
        )
        .select_related("courier_profile__service_city")
        .order_by("first_name", "last_name", "username", "id")
    )


def same_city_representatives(service_city):
    if service_city is None:
        return User.objects.none()
    return active_available_representatives().filter(
        courier_profile__service_city=service_city,
    )


def courier_service_city_for_order(order):
    if order.order_scope == Order.Scope.SERVICE_CITY:
        return order.service_city
    return None


def eligible_representatives_for_order(order):
    service_city = courier_service_city_for_order(order)
    if service_city is None:
        return active_available_representatives()
    return same_city_representatives(service_city)


class OrderListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    serializer_class = OrderSerializer

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminOrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        queryset = order_queryset()
        order_status = self.request.query_params.get("status")
        if order_status:
            queryset = queryset.filter(status=order_status)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()


class ClientOrderListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, IsClientRole)
    serializer_class = OrderSerializer

    def get_queryset(self):
        queryset = order_queryset().filter(user=self.request.user)
        order_status = self.request.query_params.get("status")
        if order_status:
            queryset = queryset.filter(status=order_status)
        return queryset


class OrderPreviewView(APIView):
    permission_classes = (IsAuthenticated, IsClientRole)

    def post(self, request):
        serializer = OrderPreviewSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.preview_data())


class ClientOrderCreateView(APIView):
    permission_classes = (IsAuthenticated, IsClientRole)

    @transaction.atomic
    def post(self, request):
        serializer = ClientOrderCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        orders = serializer.create_orders()
        return Response(
            OrderSerializer(
                orders,
                many=True,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    serializer_class = OrderSerializer
    lookup_url_kwarg = "order_id"

    def get_queryset(self):
        return order_queryset()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        order.status = Order.Status.CANCELLED
        order.assigned_representative = None
        order.assigned_at = None
        order.save(
            update_fields=[
                "status",
                "assigned_representative",
                "assigned_at",
                "updated_at",
            ]
        )
        resolve_order_review_notifications(order)
        return Response(
            self.get_serializer(order).data,
            status=status.HTTP_200_OK,
        )


class OrderStatusView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(Order, pk=order_id)
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.status = serializer.validated_data["status"]
        if order.status != Order.Status.READY:
            order.assigned_representative = None
            order.assigned_at = None
        if order.status != Order.Status.DELIVERED:
            order.delivered_at = None
        elif order.delivered_at is None:
            order.delivered_at = timezone.now()
        order.save()
        return Response(OrderSerializer(order, context={"request": request}).data)


class OrderDeliveryPriceView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
        )
        if order.status in (Order.Status.DELIVERED, Order.Status.CANCELLED):
            return Response(
                {
                    "detail": (
                        "Delivery price cannot be changed after delivery or cancellation."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderDeliveryPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery_price = serializer.validated_data["delivery_price"]
        total = order.subtotal_price - order.discount + delivery_price
        order.delivery_price = delivery_price
        order.total_price = max(total, Decimal("0.00"))
        order.save(update_fields=["delivery_price", "total_price", "updated_at"])

        refreshed_order = order_queryset().get(pk=order.pk)
        return Response(
            OrderSerializer(refreshed_order, context={"request": request}).data
        )


class OrderAssignmentView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
        )
        serializer = OrderAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        representative = serializer.validated_data["representative"]
        if order.review_status != Order.ReviewStatus.APPROVED:
            return Response(
                {"detail": "Order must be approved before assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = (
            CourierProfile.objects.select_related("service_city")
            .filter(user=representative)
            .first()
        )
        if profile is None:
            return Response(
                {"representative_id": "Representative must have a courier profile."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        courier_service_city = courier_service_city_for_order(order)
        if (
            courier_service_city is not None
            and profile.service_city_id != courier_service_city.id
        ):
            return Response(
                {
                    "representative_id": (
                        "هذا المندوب لا يعمل في نفس مدينة الطلب."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.assigned_representative = representative
        order.assigned_at = timezone.now()
        order.status = Order.Status.READY
        order.save(
            update_fields=[
                "assigned_representative",
                "assigned_at",
                "status",
                "updated_at",
            ]
        )
        create_order_assigned_notification(order, representative)
        return Response(
            {
                "message": "Order assigned successfully.",
                "order": OrderSerializer(order, context={"request": request}).data,
                "representative": RepresentativeSummarySerializer(
                    representative
                ).data,
            }
        )


class AdminOrderReviewBlockerView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    def get(self, request):
        orders = order_queryset().filter(
            review_status=Order.ReviewStatus.PENDING_REVIEW,
        )
        pending_count = orders.count()
        return Response(
            {
                "blocked": pending_count > 0,
                "pending_count": pending_count,
                "orders": OrderSerializer(
                    orders,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )


class AdminOrderApproveView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def post(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(of=("self",)).select_related(
                "service_city",
                "delivery_area",
                "delivery_area__service_city",
            ),
            pk=order_id,
        )
        if order.review_status != Order.ReviewStatus.PENDING_REVIEW:
            return Response(
                {"detail": "Order must be pending review."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.review_status = Order.ReviewStatus.APPROVED
        order.approved_by = request.user
        order.approved_at = timezone.now()
        order.rejected_by = None
        order.rejected_at = None
        order.rejection_reason = ""
        order.status = Order.Status.UNDER_PREPARATION
        order.save(
            update_fields=[
                "review_status",
                "approved_by",
                "approved_at",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
                "status",
                "updated_at",
            ]
        )
        resolve_order_review_notifications(order)
        representatives = eligible_representatives_for_order(order)
        courier_service_city = courier_service_city_for_order(order)
        response_data = {
            "message": "Order approved successfully.",
            "order": OrderSerializer(order, context={"request": request}).data,
            "service_city": (
                {
                    "id": courier_service_city.id,
                    "name": courier_service_city.name,
                }
                if courier_service_city is not None
                else None
            ),
            "available_representatives": RepresentativeSummarySerializer(
                representatives,
                many=True,
            ).data,
        }
        if not representatives.exists():
            response_data["warning"] = (
                "No representatives are available in this city."
                if courier_service_city is not None
                else "No active representatives are available."
            )
        return Response(response_data)


class AdminOrderRejectView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def post(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update().select_related("user"),
            pk=order_id,
        )
        serializer = OrderReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if order.review_status != Order.ReviewStatus.PENDING_REVIEW:
            return Response(
                {"detail": "Order must be pending review."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.assigned_representative_id or order.status == Order.Status.DELIVERED:
            return Response(
                {"detail": "Assigned or delivered orders cannot be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.review_status = Order.ReviewStatus.REJECTED
        order.status = Order.Status.CANCELLED
        order.rejected_by = request.user
        order.rejected_at = timezone.now()
        order.rejection_reason = serializer.validated_data.get(
            "rejection_reason",
            "",
        ).strip()
        order.save(
            update_fields=[
                "review_status",
                "status",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        resolve_order_review_notifications(order)
        create_order_rejected_notification(order)
        return Response(
            {
                "message": "Order rejected successfully.",
                "order_id": order.id,
                "status": order.status,
                "review_status": order.review_status,
                "rejection_reason": order.rejection_reason,
            }
        )


class AdminOrderServiceCityRepresentativesView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    def get(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_related(
                "service_city",
                "delivery_area",
                "delivery_area__service_city",
            ),
            pk=order_id,
        )
        representatives = eligible_representatives_for_order(order)
        courier_service_city = courier_service_city_for_order(order)
        return Response(
            {
                "order_id": order.id,
                "service_city": (
                    {
                        "id": courier_service_city.id,
                        "name": courier_service_city.name,
                    }
                    if courier_service_city is not None
                    else None
                ),
                "representatives": RepresentativeSummarySerializer(
                    representatives,
                    many=True,
                ).data,
            }
        )


COURIER_STATUSES = {
    Order.Status.READY,
    Order.Status.PICKED_UP,
    Order.Status.ON_THE_WAY,
    Order.Status.DELIVERED,
    Order.Status.FAILED_DELIVERY,
}

COURIER_TRANSITIONS = {
    Order.Status.READY: {Order.Status.PICKED_UP},
    Order.Status.PICKED_UP: {Order.Status.ON_THE_WAY},
    Order.Status.ON_THE_WAY: {
        Order.Status.DELIVERED,
        Order.Status.FAILED_DELIVERY,
    },
}


def courier_orders_for_user(user):
    return order_queryset().filter(assigned_representative=user)


class CourierOrderListView(APIView):
    permission_classes = (IsAuthenticated, IsCourierRole)

    def get(self, request):
        queryset = courier_orders_for_user(request.user)
        order_status = request.query_params.get("status")
        if order_status:
            if order_status not in COURIER_STATUSES:
                return Response(
                    {"status": "Unsupported status filter."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=order_status)
        return Response(
            CourierOrderListSerializer(
                queryset,
                many=True,
                context={"request": request},
            ).data
        )


class CourierOrderDetailView(APIView):
    permission_classes = (IsAuthenticated, IsCourierRole)

    def get(self, request, order_id):
        order = generics.get_object_or_404(
            courier_orders_for_user(request.user),
            pk=order_id,
        )
        return Response(
            CourierOrderDetailSerializer(
                order,
                context={"request": request},
            ).data
        )


class CourierOrderStatusView(APIView):
    permission_classes = (IsAuthenticated, IsCourierRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update().filter(
                assigned_representative=request.user,
            ),
            pk=order_id,
        )
        serializer = CourierOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        allowed_next_statuses = COURIER_TRANSITIONS.get(order.status, set())
        if new_status not in allowed_next_statuses:
            return Response(
                {"status": "Invalid status transition."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = new_status
        update_fields = ["status", "updated_at"]
        if new_status == Order.Status.PICKED_UP:
            order.market_sections.update(
                pickup_status=OrderMarketSection.PickupStatus.PICKED_UP,
                picked_up_at=timezone.now(),
            )
        if new_status == Order.Status.DELIVERED:
            order.delivered_at = timezone.now()
            update_fields.append("delivered_at")
        order.save(update_fields=update_fields)
        return Response(
            CourierOrderDetailSerializer(
                order_queryset().get(pk=order.pk),
                context={"request": request},
            ).data
        )
