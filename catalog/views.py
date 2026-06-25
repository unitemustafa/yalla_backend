from django.db.models import ProtectedError

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import CategoryClassification, Product, ProductCategory, ProductAddition
from .serializers import (
    AdditionClassificationSerializer,
    AdminProductSerializer,
    CategoryClassificationSerializer,
    ProductCategorySerializer,
    ProductAdditionSerializer,
)


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


class CategoryClassificationListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        classifications = CategoryClassification.objects.order_by("name", "id")
        return Response(
            CategoryClassificationSerializer(classifications, many=True).data
        )

    def post(self, request):
        serializer = CategoryClassificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            CategoryClassificationSerializer(classification).data,
            status=status.HTTP_201_CREATED,
        )


class CategoryClassificationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_classification(self, classification_id):
        return get_object_or_404(
            CategoryClassification,
            id=classification_id,
        )

    def get(self, request, classification_id):
        classification = self.get_classification(classification_id)
        return Response(CategoryClassificationSerializer(classification).data)

    def patch(self, request, classification_id):
        classification = self.get_classification(classification_id)
        serializer = CategoryClassificationSerializer(
            classification,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(CategoryClassificationSerializer(classification).data)

    def delete(self, request, classification_id):
        classification = self.get_classification(classification_id)
        try:
            classification.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete category classification while "
                        "categories are using it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


class ProductCategoryListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        categories = ProductCategory.objects.select_related(
            "classification",
        ).order_by("name", "id")
        return Response(ProductCategorySerializer(categories, many=True).data)

    def post(self, request):
        serializer = ProductCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            ProductCategorySerializer(category).data,
            status=status.HTTP_201_CREATED,
        )


class ProductCategoryDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_category(self, category_id):
        return get_object_or_404(
            ProductCategory.objects.select_related("classification"),
            id=category_id,
        )

    def get(self, request, category_id):
        category = self.get_category(category_id)
        return Response(ProductCategorySerializer(category).data)

    def patch(self, request, category_id):
        category = self.get_category(category_id)
        serializer = ProductCategorySerializer(
            category,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(ProductCategorySerializer(category).data)

    def delete(self, request, category_id):
        category = self.get_category(category_id)
        try:
            category.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete product category while products are "
                        "using it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


class ProductListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        return (
            Product.objects.select_related(
                "market__classification",
                "category__classification",
            )
            .prefetch_related(
                "category__attributes__options",
                "attribute_values__attribute__options",
                "attribute_values__option",
                "variants__attribute_values__attribute__options",
                "variants__attribute_values__option",
                "additions",
            )
            .order_by("name", "id")
        )

    def get(self, request):
        return Response(
            AdminProductSerializer(self.get_queryset(), many=True).data
        )

    def post(self, request):
        serializer = AdminProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        product = self.get_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )


class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        return (
            Product.objects.select_related(
                "market__classification",
                "category__classification",
            )
            .prefetch_related(
                "category__attributes__options",
                "attribute_values__attribute__options",
                "attribute_values__option",
                "variants__attribute_values__attribute__options",
                "variants__attribute_values__option",
                "additions",
            )
        )

    def get_product(self, product_id):
        return get_object_or_404(self.get_queryset(), id=product_id)

    def get(self, request, product_id):
        product = self.get_product(product_id)
        return Response(AdminProductSerializer(product).data)

    def patch(self, request, product_id):
        product = self.get_product(product_id)
        serializer = AdminProductSerializer(
            product,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        product = self.get_queryset().get(id=product.id)
        return Response(AdminProductSerializer(product).data)

    def delete(self, request, product_id):
        product = self.get_product(product_id)
        try:
            product.delete()
        except ProtectedError:
            return Response(
                {"detail": "Cannot delete product while orders are using it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_204_NO_CONTENT,
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
        return Response({
            "details" : "Deleted Successfully"
        },status=status.HTTP_204_NO_CONTENT)
