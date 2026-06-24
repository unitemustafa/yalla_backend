from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import ProductAddition
from .serializers import AdditionClassificationSerializer, ProductAdditionSerializer


class IsAdminRole(BasePermission):
    message = "Only admin users can manage catalog data."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class AdditionClassificationCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = AdditionClassificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            AdditionClassificationSerializer(classification).data,
            status=status.HTTP_201_CREATED,
        )


class ProductAdditionListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        additions = (
            ProductAddition.objects.select_related("classification")
            .prefetch_related("products")
            .order_by("name_ar", "id")
        )
        return Response(ProductAdditionSerializer(additions, many=True).data)

    def post(self, request):
        serializer = ProductAdditionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        addition = serializer.save()
        return Response(
            ProductAdditionSerializer(addition).data,
            status=status.HTTP_201_CREATED,
        )


class ProductAdditionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_addition(self, addition_id):
        return get_object_or_404(
            ProductAddition.objects.select_related(
                "classification",
            ).prefetch_related("products"),
            id=addition_id,
        )

    def get(self, request, addition_id):
        addition = self.get_addition(addition_id)
        return Response(ProductAdditionSerializer(addition).data)

    def patch(self, request, addition_id):
        addition = self.get_addition(addition_id)
        serializer = ProductAdditionSerializer(
            addition,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        addition = serializer.save()
        return Response(ProductAdditionSerializer(addition).data)

    def delete(self, request, addition_id):
        addition = self.get_addition(addition_id)
        addition.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
