from django.shortcuts import render

# Create your views here.
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import IsAdminRole

from .models import DeliveryArea


class DeliveryAreaListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        areas = DeliveryArea.objects.order_by("name", "id")
        return Response(
            [
                {
                    "id": area.id,
                    "name": area.name,
                    "delivery_price": area.delivery_price,
                    "is_active": area.is_active,
                }
                for area in areas
            ]
        )
