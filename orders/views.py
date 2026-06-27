from rest_framework import status
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import DeliverOrderSerializer, OrderSerializer
from accounts.models import CourierProfile

User = get_user_model()


class IsAdminRole(BasePermission):
    message = "Only admin users can manage delivery assignments."

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsRepresentativeRole(BasePermission):
    message = "Only representative accounts can access assigned deliveries."

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.role == User.Role.REPRESENTATIVE
        )


def order_queryset():
    return (
        Order.objects.select_related(
            "user",
            "market__classification",
            "delivery_address",
            "assigned_representative",
        )
        .prefetch_related(
            "items__variant__product__category__classification",
            "order_offers__offer",
        )
        .order_by("-created_at", "-id")
    )


class UserOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = order_queryset().filter(user=request.user)
        serializer = OrderSerializer(
            orders,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminOrdersView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        orders = order_queryset()
        order_status = request.query_params.get("status")
        if order_status:
            orders = orders.filter(status=order_status)
        return Response(OrderSerializer(orders, many=True, context={"request": request}).data)


class OrderAssignmentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @transaction.atomic
    def patch(self, request, order_id):
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        representative_id = request.data.get("representative_id")
        if representative_id in (None, ""):
            if order.status != Order.Status.READY:
                return Response(
                    {"detail": "Only ready orders can be unassigned."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.assigned_representative = None
            order.assigned_at = None
            order.save(update_fields=["assigned_representative", "assigned_at", "updated_at"])
            return Response(OrderSerializer(order, context={"request": request}).data)

        if order.status != Order.Status.READY:
            return Response(
                {"detail": "Only ready orders can be assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.delivery_address_id is None:
            return Response(
                {"detail": "A delivery address is required before assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            representative = (
                User.objects.select_for_update()
                .get(
                    pk=representative_id,
                    role=User.Role.REPRESENTATIVE,
                    is_active=True,
                    deleted_at__isnull=True,
                )
            )
        except (User.DoesNotExist, ValueError):
            return Response(
                {"representative_id": "Active representative not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            profile = CourierProfile.objects.select_for_update().get(
                user=representative
            )
        except CourierProfile.DoesNotExist:
            return Response(
                {"representative_id": "Representative has no courier profile."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not profile.is_available:
            return Response(
                {"representative_id": "Representative is unavailable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        active_count = Order.objects.filter(
            assigned_representative=representative,
            status=Order.Status.READY,
        ).exclude(pk=order.pk).count()
        if active_count >= profile.max_active_orders:
            return Response(
                {"representative_id": "Representative has reached the active order limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.assigned_representative = representative
        order.assigned_at = timezone.now()
        order.save(update_fields=["assigned_representative", "assigned_at", "updated_at"])
        return Response(OrderSerializer(order, context={"request": request}).data)


class AssignedOrdersView(APIView):
    permission_classes = [IsAuthenticated, IsRepresentativeRole]

    def get(self, request):
        orders = order_queryset().filter(
            assigned_representative=request.user,
            status__in=[Order.Status.READY, Order.Status.DELIVERED],
        )
        requested_status = request.query_params.get("status")
        if requested_status == "active":
            orders = orders.filter(status=Order.Status.READY)
        elif requested_status == "delivered":
            orders = orders.filter(status=Order.Status.DELIVERED)
        return Response(OrderSerializer(orders, many=True, context={"request": request}).data)


class DeliverOrderView(APIView):
    permission_classes = [IsAuthenticated, IsRepresentativeRole]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        if order.assigned_representative_id != request.user.id:
            return Response(
                {"detail": "This order is not assigned to the current representative."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if order.status != Order.Status.READY:
            return Response(
                {"detail": "Only ready orders can be delivered."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = DeliverOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "")
        proof = serializer.validated_data.get("proof")
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.delivery_note = note
        if proof is not None:
            order.delivery_proof = proof
        order.save()
        return Response(OrderSerializer(order, context={"request": request}).data)
