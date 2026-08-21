from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOrderAdminRole
from notifications.order_services import schedule_order_lifecycle_notification
from notifications.services import resolve_order_review_notifications

from .models import Order, OrderEvent
from .selectors import (
    courier_service_city_for_order,
    eligible_representatives_for_order,
    order_queryset,
)
from .serializers import (
    OrderReviewActionSerializer,
    OrderSerializer,
    RepresentativeSummarySerializer,
)
from .services import record_order_event


class AdminOrderReviewBlockerView(APIView):
    permission_classes = (IsAuthenticated, IsOrderAdminRole)

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
    permission_classes = (IsAuthenticated, IsOrderAdminRole)

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
        old_status = order.status
        order.review_status = Order.ReviewStatus.APPROVED
        order.approved_by = request.user
        order.approved_at = timezone.now()
        order.rejected_by = None
        order.rejected_at = None
        order.rejection_reason = ""
        order.status = Order.Status.CONFIRMED
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
        event = record_order_event(
            order,
            OrderEvent.EventType.REVIEW_APPROVED,
            actor=request.user,
            from_status=old_status,
            to_status=order.status,
            metadata={"review_status": order.review_status},
        )
        schedule_order_lifecycle_notification(
            order,
            event,
            "order_review_approved",
            old_status=old_status,
            new_status=order.status,
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
    permission_classes = (IsAuthenticated, IsOrderAdminRole)

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
        old_status = order.status
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
        event = record_order_event(
            order,
            OrderEvent.EventType.REVIEW_REJECTED,
            actor=request.user,
            from_status=old_status,
            to_status=order.status,
            note=order.rejection_reason,
            metadata={"review_status": order.review_status},
        )
        resolve_order_review_notifications(order)
        schedule_order_lifecycle_notification(
            order,
            event,
            "order_review_rejected",
            old_status=old_status,
            new_status=order.status,
        )
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
    permission_classes = (IsAuthenticated, IsOrderAdminRole)

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

