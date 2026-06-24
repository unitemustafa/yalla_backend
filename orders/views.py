from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import OrderSerializer


class UserOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = (
            Order.objects.filter(user=request.user)
            .select_related("market__classification")
            .prefetch_related(
                "items__variant__product__category__classification",
                "order_offers__offer",
            )
            .order_by("-created_at", "-id")
        )
        serializer = OrderSerializer(
            orders,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
