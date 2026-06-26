from django.db.models import ProtectedError

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import Offer
from .serializers import AdminOfferSerializer


class IsAdminRole(BasePermission):
    message = "Only admin users can manage offers."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class OfferListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        return (
            Offer.objects.select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__delivery_areas",
                "products",
            )
            .order_by("-created_at", "-id")
        )

    def get(self, request):
        return Response(AdminOfferSerializer(self.get_queryset(), many=True).data)

    def post(self, request):
        serializer = AdminOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offer = serializer.save()
        offer = self.get_queryset().get(id=offer.id)
        return Response(
            AdminOfferSerializer(offer).data,
            status=status.HTTP_201_CREATED,
        )


class OfferDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        return (
            Offer.objects.select_related(
                "market__classification",
            )
            .prefetch_related(
                "market__delivery_areas",
                "products",
            )
        )

    def get_offer(self, offer_id):
        return get_object_or_404(self.get_queryset(), id=offer_id)

    def get(self, request, offer_id):
        offer = self.get_offer(offer_id)
        return Response(AdminOfferSerializer(offer).data)

    def patch(self, request, offer_id):
        offer = self.get_offer(offer_id)
        serializer = AdminOfferSerializer(
            offer,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        offer = serializer.save()
        offer = self.get_queryset().get(id=offer.id)
        return Response(AdminOfferSerializer(offer).data)

    def delete(self, request, offer_id):
        offer = self.get_offer(offer_id)
        try:
            offer.delete()
        except ProtectedError:
            return Response(
                {"detail": "Cannot delete offer while orders are using it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_200_OK,
        )
