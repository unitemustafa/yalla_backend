from django.db import transaction
from django.db.models import Count, Sum
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsRepresentativeRole
from config.pagination import paginated_list_response, YallaPageNumberPagination
from notifications.order_services import (
    create_admin_courier_order_status_notification,
    schedule_order_lifecycle_notification,
)

from .models import Order, OrderEvent, OrderMarketSection
from .selectors import (
    courier_order_list_queryset,
    courier_orders_for_user,
    order_queryset,
)
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
        scope = request.query_params.get("scope")
        if scope not in (None, "active", "history"):
            return Response(
                {"scope": "Unsupported order scope."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        terminal = (
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
            Order.Status.CANCELLED,
        )
        if scope == "active":
            queryset = queryset.exclude(status__in=terminal)
        elif scope == "history":
            queryset = queryset.filter(status__in=terminal)
        for parameter, lookup in (
            ("delivered_from", "delivered_at__gte"),
            ("delivered_before", "delivered_at__lt"),
        ):
            value = request.query_params.get(parameter)
            if value:
                try:
                    parsed = parse_datetime(value)
                except ValueError:
                    parsed = None
                if parsed is None or timezone.is_naive(parsed):
                    return Response(
                        {parameter: "Use an ISO timestamp with timezone."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                queryset = queryset.filter(**{lookup: parsed})
        order_status = request.query_params.get("status")
        if order_status:
            if order_status not in COURIER_STATUSES:
                return Response(
                    {"status": "Unsupported status filter."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=order_status)
        if scope:
            totals = queryset.aggregate(
                count=Count("pk"),
                total_value=Sum("total_price"),
                total_delivery_fees=Sum("delivery_price"),
            )
            paginator = YallaPageNumberPagination()
            # Scoped responses always paginate, including callers without page.
            page = super(YallaPageNumberPagination, paginator).paginate_queryset(
                queryset, request
            )
            response = paginator.get_paginated_response(
                CourierOrderListSerializer(
                    page, many=True, context={"request": request}
                ).data
            )
            response.data["summary"] = {
                "count": totals["count"],
                "total_value": f"{totals['total_value'] or 0:.2f}",
                "total_delivery_fees": f"{totals['total_delivery_fees'] or 0:.2f}",
            }
            return response
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


class CourierOrderMarketPickupView(APIView):
    permission_classes = (IsAuthenticated, IsRepresentativeRole)

    @transaction.atomic
    def patch(self, request, order_id, section_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update().filter(
                assigned_representative=request.user,
            ),
            pk=order_id,
        )
        if order.status != Order.Status.ASSIGNED:
            return Response(
                {"status": "Order is not awaiting pickup."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        section = generics.get_object_or_404(
            OrderMarketSection.objects.select_for_update(),
            pk=section_id,
            order=order,
        )
        if section.pickup_status != OrderMarketSection.PickupStatus.PICKED_UP:
            section.pickup_status = OrderMarketSection.PickupStatus.PICKED_UP
            section.picked_up_at = timezone.now()
            section.save(update_fields=("pickup_status", "picked_up_at", "updated_at"))
        return Response(
            CourierOrderDetailSerializer(
                order_queryset().get(pk=order.pk),
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
        if new_status == order.status:
            # Lost-response retries do not replace the committed note/proof or
            # repeat notifications. Authorization is still checked above.
            return Response(
                CourierOrderDetailSerializer(
                    order_queryset().get(pk=order.pk), context={"request": request}
                ).data
            )
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
