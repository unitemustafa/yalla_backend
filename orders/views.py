from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import (
    OrderAssignmentSerializer,
    OrderSerializer,
    OrderStatusSerializer,
)

User = get_user_model()


class IsAdminRole(BasePermission):
    message = "Only admin users can manage orders."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.ADMIN


def order_queryset():
    return (
        Order.objects.select_related(
            "user", "delivery_address", "assigned_representative", "market"
        )
        .prefetch_related("items__variant", "order_offers__offer")
        .order_by("-created_at", "-id")
    )


class OrderListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    serializer_class = OrderSerializer

    def get_queryset(self):
        queryset = order_queryset()
        order_status = self.request.query_params.get("status")
        if order_status:
            queryset = queryset.filter(status=order_status)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()


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
        order.assigned_representative = representative
        order.assigned_at = timezone.now() if representative else None
        order.status = Order.Status.READY if representative else Order.Status.PENDING
        order.save()
        return Response(OrderSerializer(order, context={"request": request}).data)
