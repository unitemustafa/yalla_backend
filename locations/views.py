from django.db import transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from accounts.views import IsAdminRole
from accounts.models import CourierProfile, User
from orders.models import Order
from notifications.delivery_area_services import (
    schedule_delivery_area_created_notifications,
)

from .models import Address, DeliveryArea, ServiceCity
from .serializers import (
    AddressSerializer,
    AddressWriteSerializer,
    DeliveryAreaSerializer,
    PointResolveSerializer,
    ServiceCitySerializer,
)
from .resolution import resolve_point_for_selection


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


def service_city_queryset():
    return ServiceCity.objects.annotate(
        delivery_area_count=Count("delivery_areas", distinct=True),
        market_count=Count("markets", distinct=True),
        offer_count=Count("offers", distinct=True),
    ).order_by("name", "id")


def service_city_relation_counts(city):
    checks = {
        "delivery_areas": city.delivery_areas.count(),
        "markets": city.markets.distinct().count(),
        "offers": city.offers.distinct().count(),
        "couriers": CourierProfile.objects.filter(
            service_city=city,
            user__deleted_at__isnull=True,
        ).count(),
        "addresses": Address.objects.filter(
            service_city=city,
            user__deleted_at__isnull=True,
        ).count(),
        "orders": Order.objects.filter(service_city=city).count(),
        "users": city.market_region_users.filter(
            deleted_at__isnull=True,
        ).count(),
    }
    return {key: value for key, value in checks.items() if value}


def service_city_relation_message(city, relations):
    labels = {
        "delivery_areas": "مناطق التوصيل",
        "markets": "المحلات",
        "offers": "العروض",
        "couriers": "المندوبون",
        "addresses": "عناوين العملاء",
        "orders": "الطلبات",
        "users": "حسابات العملاء",
    }
    linked_data = "، ".join(
        f"{labels.get(key, key)} ({count})" for key, count in relations.items()
    )
    return (
        f"لا يمكن حذف مدينة {city.name} لأنها مرتبطة بـ: {linked_data}. "
        "انقل أو احذف هذه البيانات أولًا."
    )


class ServiceCityListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = ServiceCitySerializer

    def get_queryset(self):
        return service_city_queryset()


class ServiceCityDetailView(
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = ServiceCitySerializer
    lookup_url_kwarg = "city_id"

    def get_queryset(self):
        return service_city_queryset()

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        city = generics.get_object_or_404(
            ServiceCity.objects.select_for_update(),
            pk=kwargs[self.lookup_url_kwarg],
        )
        # Soft-deleted accounts are not active city dependencies. Remove their
        # dependent data before deleting the city because its foreign keys
        # intentionally protect a city while stale records still reference it.
        CourierProfile.objects.filter(
            service_city=city,
            user__deleted_at__isnull=False,
        ).delete()
        Address.objects.filter(
            service_city=city,
            user__deleted_at__isnull=False,
        ).delete()
        User.objects.filter(
            market_region_service_city=city,
            deleted_at__isnull=False,
        ).update(
            market_region_mode=None,
            market_region_service_city=None,
            market_region_updated_at=None,
        )
        relations = service_city_relation_counts(city)
        if relations:
            return Response(
                {
                    "detail": service_city_relation_message(city, relations),
                    "code": "service_city_in_use",
                    "relations": relations,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        city.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        area = serializer.save()
        schedule_delivery_area_created_notifications(area.id)

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
    address_error_message = (
        "لا يمكن حذف منطقة التوصيل لوجود عناوين محفوظة مرتبطة بها."
    )

    def get_queryset(self):
        queryset = DeliveryArea.objects.select_related("service_city")
        if self.request.user.role != self.request.user.Role.ADMIN:
            queryset = queryset.filter(
                is_active=True,
                service_city__is_active=True,
            )
        return queryset

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        area = serializer.save()
        if was_active != area.is_active:
            transaction.on_commit(
                lambda area_id=area.id, is_active=area.is_active: _send_delivery_area_status_change(
                    area_id,
                    is_active,
                )
            )

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

        stale_addresses = Address.objects.filter(
            delivery_area=area,
            is_active=False,
            orders__isnull=True,
        )
        try:
            stale_addresses.delete()
        except ProtectedError:
            return Response(
                {"detail": self.order_error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Address.objects.filter(delivery_area=area, is_active=True).exists():
            return Response(
                {"detail": self.address_error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        area.markets.clear()
        area.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _send_delivery_area_status_change(area_id, is_active):
    from notifications.push import send_delivery_area_status_changed_event

    try:
        send_delivery_area_status_changed_event(area_id, is_active)
    except Exception:
        # A refresh when the user reopens the app remains the fallback.
        pass


class DeliveryAreaListView(APIView):
    """Backward-compatible alias for the original read-only endpoint."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        areas = DeliveryArea.objects.order_by("name", "id")
        return Response(DeliveryAreaSerializer(areas, many=True).data)


class PointResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PointResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resolution = resolve_point_for_selection(
            user=request.user,
            latitude=serializer.validated_data["latitude"],
            longitude=serializer.validated_data["longitude"],
        )
        response_status = (
            status.HTTP_200_OK
            if resolution.allowed
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        return Response(resolution.as_dict(), status=response_status)


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

    def get_address(self, request, address_id, *, for_update=False):
        queryset = Address.objects.select_related(
            "user",
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
        )
        if for_update:
            queryset = queryset.select_for_update()
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
        address = self.get_address(request, address_id, for_update=True)
        if address is None:
            return Response({"detail": "Address not found."}, status=status.HTTP_404_NOT_FOUND)
        user = address.user
        was_default = address.is_default
        if Order.objects.filter(delivery_address=address).exists():
            address.is_active = False
            address.is_default = False
            address.save(update_fields=["is_active", "is_default"])
        else:
            address.delete()
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
