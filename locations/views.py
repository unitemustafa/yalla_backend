from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from accounts.views import IsAdminRole
from accounts.models import CourierProfile
from orders.models import Order

from .models import Address, DeliveryArea, ServiceCity
from .serializers import (
    AddressSerializer,
    AddressWriteSerializer,
    DeliveryAreaSerializer,
    ServiceCitySerializer,
)


class ProtectedDeleteMixin:
    protected_error_message = "This item is in use and cannot be deleted."

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": self.protected_error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ServiceCityListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = ServiceCitySerializer
    queryset = ServiceCity.objects.order_by("name", "id")


class ServiceCityDetailView(
    ProtectedDeleteMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = ServiceCitySerializer
    queryset = ServiceCity.objects.all()
    lookup_url_kwarg = "city_id"
    protected_error_message = (
        "Service city cannot be deleted while its delivery areas are in use."
    )


class DeliveryAreaPermission(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == request.user.Role.ADMIN


class DeliveryAreaListCreateView(generics.ListCreateAPIView):
    permission_classes = [DeliveryAreaPermission]
    serializer_class = DeliveryAreaSerializer

    def get_queryset(self):
        queryset = DeliveryArea.objects.select_related("service_city").order_by(
            "name", "id"
        )
        if self.request.user.role != self.request.user.Role.ADMIN:
            queryset = queryset.filter(
                is_active=True,
                service_city__is_active=True,
            )
        city_id = self.request.query_params.get("service_city_id")
        if city_id:
            queryset = queryset.filter(service_city_id=city_id)
        return queryset


class DeliveryAreaDetailView(
    ProtectedDeleteMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [DeliveryAreaPermission]
    serializer_class = DeliveryAreaSerializer
    lookup_url_kwarg = "area_id"
    protected_error_message = (
        "Delivery area cannot be deleted while representatives are using it."
    )
    courier_error_message = (
        "لا يمكن حذف منطقة التوصيل لأنها مستخدمة بواسطة مندوبين."
    )
    order_error_message = (
        "لا يمكن حذف منطقة التوصيل لوجود طلبات مرتبطة بها."
    )

    def get_queryset(self):
        queryset = DeliveryArea.objects.select_related("service_city")
        if self.request.user.role != self.request.user.Role.ADMIN:
            queryset = queryset.filter(
                is_active=True,
                service_city__is_active=True,
            )
        return queryset

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        area = generics.get_object_or_404(
            self.get_queryset().select_for_update(),
            pk=kwargs[self.lookup_url_kwarg]
        )

        if CourierProfile.objects.filter(delivery_area=area).exists():
            return Response(
                {"detail": self.courier_error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Order.objects.filter(
            delivery_area=area,
        ).exists() or Order.objects.filter(
            delivery_address__delivery_area=area,
        ).exists():
            return Response(
                {"detail": self.order_error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        area.markets.clear()
        Address.objects.filter(delivery_area=area).update(
            delivery_area=None,
            delivery_type=Address.DeliveryType.DELIVERY,
            manual_area=area.name,
        )
        area.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeliveryAreaListView(APIView):
    """Backward-compatible alias for the original read-only endpoint."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        areas = DeliveryArea.objects.order_by("name", "id")
        return Response(DeliveryAreaSerializer(areas, many=True).data)


def address_queryset_for_request(request):
    queryset = Address.objects.select_related(
        "user",
        "service_city",
        "delivery_area",
        "delivery_area__service_city",
    ).order_by(
        "-is_default",
        "-created_at",
        "-id",
    )
    queryset = queryset.filter(is_active=True)
    if request.user.role == request.user.Role.ADMIN:
        user_id = request.query_params.get("user_id")
        if user_id:
            return queryset.filter(user_id=user_id)
        return queryset
    return queryset.filter(user=request.user)


def set_default_address(address):
    if address.is_default:
        if not address.is_active:
            address.is_default = False
            address.save(update_fields=["is_default"])
            return
        Address.objects.filter(
            user=address.user,
            is_active=True,
        ).exclude(pk=address.pk).update(is_default=False)


class AddressListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        addresses = address_queryset_for_request(request)
        return Response(AddressSerializer(addresses, many=True).data)

    @transaction.atomic
    def post(self, request):
        serializer = AddressWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        address = serializer.save()
        set_default_address(address)
        addresses = address_queryset_for_request(request).filter(user=address.user)
        return Response(
            AddressSerializer(addresses, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class AddressDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address = (
            Address.objects.select_related(
                "user",
                "service_city",
                "delivery_area",
                "delivery_area__service_city",
            )
            .filter(user=request.user, is_default=True)
            .filter(is_active=True)
            .order_by("-created_at", "-id")
            .first()
            or Address.objects.select_related(
                "user",
                "service_city",
                "delivery_area",
                "delivery_area__service_city",
            )
            .filter(user=request.user)
            .filter(is_active=True)
            .order_by("-created_at", "-id")
            .first()
        )
        return Response(None if address is None else AddressSerializer(address).data)


class AddressDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_address(self, request, address_id):
        queryset = Address.objects.select_related(
            "user",
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
        )
        queryset = queryset.filter(is_active=True)
        if request.user.role != request.user.Role.ADMIN:
            queryset = queryset.filter(user=request.user)
        try:
            return queryset.get(pk=address_id)
        except Address.DoesNotExist:
            return None

    @transaction.atomic
    def patch(self, request, address_id):
        address = self.get_address(request, address_id)
        if address is None:
            return Response({"detail": "Address not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AddressWriteSerializer(
            address,
            data=request.data,
            context={"request": request, "user_id": address.user_id},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        address = serializer.save()
        set_default_address(address)
        addresses = address_queryset_for_request(request).filter(user=address.user)
        return Response(AddressSerializer(addresses, many=True).data)

    @transaction.atomic
    def delete(self, request, address_id):
        address = self.get_address(request, address_id)
        if address is None:
            return Response({"detail": "Address not found."}, status=status.HTTP_404_NOT_FOUND)
        user = address.user
        was_default = address.is_default
        address.is_active = False
        address.is_default = False
        address.save(update_fields=["is_active", "is_default"])
        if was_default:
            next_address = (
                Address.objects.filter(user=user, is_active=True)
                .order_by("-created_at", "-id")
                .first()
            )
            if next_address is not None:
                next_address.is_default = True
                next_address.save(update_fields=["is_default"])
        addresses = address_queryset_for_request(request).filter(user=user)
        return Response(AddressSerializer(addresses, many=True).data)


class AddressSetDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, address_id):
        queryset = Address.objects.select_related(
            "user",
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
        ).filter(is_active=True)
        if request.user.role != request.user.Role.ADMIN:
            queryset = queryset.filter(user=request.user)
        try:
            address = queryset.get(pk=address_id)
        except Address.DoesNotExist:
            return Response({"detail": "Address not found."}, status=status.HTTP_404_NOT_FOUND)
        Address.objects.filter(user=address.user, is_active=True).update(
            is_default=False
        )
        address.is_default = True
        address.save(update_fields=["is_default"])
        addresses = address_queryset_for_request(request).filter(user=address.user)
        return Response(AddressSerializer(addresses, many=True).data)
