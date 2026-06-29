from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from accounts.views import IsAdminRole

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


class DeliveryAreaListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = DeliveryAreaSerializer

    def get_queryset(self):
        queryset = DeliveryArea.objects.select_related("service_city").order_by(
            "name", "id"
        )
        city_id = self.request.query_params.get("service_city_id")
        if city_id:
            queryset = queryset.filter(service_city_id=city_id)
        return queryset


class DeliveryAreaDetailView(
    ProtectedDeleteMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = DeliveryAreaSerializer
    queryset = DeliveryArea.objects.select_related("service_city")
    lookup_url_kwarg = "area_id"
    protected_error_message = (
        "Delivery area cannot be deleted while representatives are using it."
    )


class DeliveryAreaListView(APIView):
    """Backward-compatible alias for the original read-only endpoint."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        areas = DeliveryArea.objects.order_by("name", "id")
        return Response(DeliveryAreaSerializer(areas, many=True).data)


def address_queryset_for_request(request):
    queryset = Address.objects.select_related("user").order_by("-is_default", "-created_at", "-id")
    if request.user.role == request.user.Role.ADMIN:
        user_id = request.query_params.get("user_id")
        if user_id:
            return queryset.filter(user_id=user_id)
        return queryset
    return queryset.filter(user=request.user)


def set_default_address(address):
    if address.is_default:
        Address.objects.filter(user=address.user).exclude(pk=address.pk).update(
            is_default=False
        )


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
        addresses = Address.objects.select_related("user").filter(
            user=address.user
        ).order_by("-is_default", "-created_at", "-id")
        return Response(
            AddressSerializer(addresses, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class AddressDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address = (
            Address.objects.select_related("user")
            .filter(user=request.user, is_default=True)
            .order_by("-created_at", "-id")
            .first()
            or Address.objects.select_related("user")
            .filter(user=request.user)
            .order_by("-created_at", "-id")
            .first()
        )
        return Response(None if address is None else AddressSerializer(address).data)


class AddressDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_address(self, request, address_id):
        queryset = Address.objects.select_related("user")
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
        addresses = Address.objects.select_related("user").filter(
            user=address.user
        ).order_by("-is_default", "-created_at", "-id")
        return Response(AddressSerializer(addresses, many=True).data)

    @transaction.atomic
    def delete(self, request, address_id):
        address = self.get_address(request, address_id)
        if address is None:
            return Response({"detail": "Address not found."}, status=status.HTTP_404_NOT_FOUND)
        user = address.user
        was_default = address.is_default
        address.delete()
        if was_default:
            next_address = (
                Address.objects.filter(user=user)
                .order_by("-created_at", "-id")
                .first()
            )
            if next_address is not None:
                next_address.is_default = True
                next_address.save(update_fields=["is_default"])
        addresses = Address.objects.select_related("user").filter(
            user=user
        ).order_by("-is_default", "-created_at", "-id")
        return Response(AddressSerializer(addresses, many=True).data)


class AddressSetDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, address_id):
        queryset = Address.objects.select_related("user")
        if request.user.role != request.user.Role.ADMIN:
            queryset = queryset.filter(user=request.user)
        try:
            address = queryset.get(pk=address_id)
        except Address.DoesNotExist:
            return Response({"detail": "Address not found."}, status=status.HTTP_404_NOT_FOUND)
        Address.objects.filter(user=address.user).update(is_default=False)
        address.is_default = True
        address.save(update_fields=["is_default"])
        addresses = Address.objects.select_related("user").filter(
            user=address.user
        ).order_by("-is_default", "-created_at", "-id")
        return Response(AddressSerializer(addresses, many=True).data)
