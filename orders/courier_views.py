from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsRepresentativeRole
from config.pagination import paginated_list_response
from notifications.order_services import (
    create_admin_courier_order_status_notification,
    schedule_order_lifecycle_notification,
)

from .models import Order, OrderEvent, OrderMarketSection
from .selectors import courier_order_list_queryset, courier_orders_for_user, order_queryset
from .serializers import (
    CourierOrderDetailSerializer,
    CourierOrderListSerializer,
    CourierOrderStatusSerializer,
)
from .services import COURIER_STATUSES, COURIER_TRANSITIONS, record_order_event


class CourierOrderListView(APIView):
    permission_classes = (IsAuthenticated, IsRepresentativeRole)

    def get(self, request):
        queryset = courier_order_list_queryset(request.user)
        order_status = request.query_params.get("status")
        if order_status:
            if order_status not in COURIER_STATUSES:
                return Response(
                    {"status": "Unsupported status filter."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=order_status)
        return paginated_list_response(
            request,
            queryset,
            CourierOrderListSerializer,
        )


class CourierOrderDetailView(APIView):
    permission_classes = (IsAuthenticated, IsRepresentativeRole)

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
    permission_classes = (IsAuthenticated, IsRepresentativeRole)

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
        old_status = order.status
        order.status = new_status
        update_fields = ["status", "updated_at"]
        if new_status == Order.Status.PICKED_UP:
            order.market_sections.update(
                pickup_status=OrderMarketSection.PickupStatus.PICKED_UP,
                picked_up_at=timezone.now(),
            )
        if new_status in (Order.Status.DELIVERED, Order.Status.FAILED_DELIVERY):
            if "delivery_note" in serializer.validated_data:
                order.delivery_note = serializer.validated_data["delivery_note"].strip()
                update_fields.append("delivery_note")
        if new_status == Order.Status.DELIVERED:
            order.delivered_at = timezone.now()
            update_fields.append("delivered_at")
            if "delivery_proof" in serializer.validated_data:
                order.delivery_proof = serializer.validated_data["delivery_proof"]
                update_fields.append("delivery_proof")
        order.save(update_fields=update_fields)
        event = record_order_event(
            order,
            OrderEvent.EventType.STATUS_CHANGED,
            actor=request.user,
            from_status=old_status,
            to_status=new_status,
        )
        create_admin_courier_order_status_notification(order, event, new_status)
        schedule_order_lifecycle_notification(
            order,
            event,
            (
                "order_failed_delivery"
                if new_status == Order.Status.FAILED_DELIVERY
                else "order_status_changed"
            ),
            old_status=old_status,
            new_status=new_status,
        )
        return Response(
            CourierOrderDetailSerializer(
                order_queryset().get(pk=order.pk),
                context={"request": request},
            ).data
        )

