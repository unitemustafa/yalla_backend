from django.db.models import ProtectedError

from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductImage,
    ProductCategory,
    ProductAddition,
)
from .serializers import (
    AdditionClassificationSerializer,
    AdminProductSerializer,
    AdminCategoryAttributeSerializer,
    AdminCategoryOptionSerializer,
    CategoryClassificationSerializer,
    LikedProductSerializer,
    ProductCategorySerializer,
    ProductAdditionSerializer,
    ProductImagePrimarySerializer,
    ProductImageReorderSerializer,
    ProductImageUploadSerializer,
)
from .product_images import (
    add_product_images,
    delete_product_image,
    reorder_product_images,
    set_primary_product_image,
)


class IsAdminRole(BasePermission):
    message = "Only admin users can manage catalog data."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsClientRole(BasePermission):
    message = "Only client users can like products."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.CLIENT
        )


def product_queryset():
    return (
        Product.objects.select_related(
            "market__classification",
            "category__classification",
        )
        .prefetch_related(
            "category__attributes__options",
            "attributes__options",
            "attribute_values__attribute__options",
            "attribute_values__option",
            "variants__attribute_values__attribute__options",
            "variants__attribute_values__option",
            "variants__attribute_values__product_attribute__options",
            "variants__attribute_values__product_attribute_option",
            "additions",
            "images",
        )
    )


class AdditionClassificationListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        classifications = AdditionClassification.objects.order_by("name", "id")
        return Response(
            AdditionClassificationSerializer(classifications, many=True).data
        )

    def post(self, request):
        serializer = AdditionClassificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            AdditionClassificationSerializer(classification).data,
            status=status.HTTP_201_CREATED,
        )


class AdditionClassificationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_classification(self, classification_id):
        return get_object_or_404(
            AdditionClassification,
            id=classification_id,
        )

    def get(self, request, classification_id):
        classification = self.get_classification(classification_id)
        return Response(AdditionClassificationSerializer(classification).data)

    def patch(self, request, classification_id):
        classification = self.get_classification(classification_id)
        serializer = AdditionClassificationSerializer(
            classification,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(AdditionClassificationSerializer(classification).data)

    def delete(self, request, classification_id):
        classification = self.get_classification(classification_id)
        try:
            classification.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete addition classification while product "
                        "additions are using it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_200_OK,
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
            status=status.HTTP_200_OK,
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
            status=status.HTTP_200_OK,
        )


class CategoryAttributeListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        attributes = (
            CategoryAttribute.objects.select_related(
                "category__classification",
            )
            .prefetch_related("options")
            .order_by("category__name", "name", "id")
        )
        return Response(AdminCategoryAttributeSerializer(attributes, many=True).data)

    def post(self, request):
        serializer = AdminCategoryAttributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attribute = serializer.save()
        return Response(
            AdminCategoryAttributeSerializer(attribute).data,
            status=status.HTTP_201_CREATED,
        )


class CategoryAttributeDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_attribute(self, attribute_id):
        return get_object_or_404(
            CategoryAttribute.objects.select_related(
                "category__classification",
            ).prefetch_related("options"),
            id=attribute_id,
        )

    def get(self, request, attribute_id):
        attribute = self.get_attribute(attribute_id)
        return Response(AdminCategoryAttributeSerializer(attribute).data)

    def patch(self, request, attribute_id):
        attribute = self.get_attribute(attribute_id)
        serializer = AdminCategoryAttributeSerializer(
            attribute,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        attribute = serializer.save()
        return Response(AdminCategoryAttributeSerializer(attribute).data)

    def delete(self, request, attribute_id):
        attribute = self.get_attribute(attribute_id)
        try:
            attribute.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete category attribute while product or "
                        "variant values are using it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_200_OK,
        )


class CategoryOptionListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        options = CategoryOption.objects.select_related(
            "attribute__category",
        ).order_by("attribute__name", "value", "id")
        return Response(AdminCategoryOptionSerializer(options, many=True).data)

    def post(self, request):
        serializer = AdminCategoryOptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        option = serializer.save()
        return Response(
            AdminCategoryOptionSerializer(option).data,
            status=status.HTTP_201_CREATED,
        )


class CategoryOptionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_option(self, option_id):
        return get_object_or_404(
            CategoryOption.objects.select_related("attribute__category"),
            id=option_id,
        )

    def get(self, request, option_id):
        option = self.get_option(option_id)
        return Response(AdminCategoryOptionSerializer(option).data)

    def patch(self, request, option_id):
        option = self.get_option(option_id)
        serializer = AdminCategoryOptionSerializer(
            option,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        option = serializer.save()
        return Response(AdminCategoryOptionSerializer(option).data)

    def delete(self, request, option_id):
        option = self.get_option(option_id)
        try:
            option.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete category option while product or "
                        "variant values are using it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"details": "Deleted Successfully"},
            status=status.HTTP_200_OK,
        )


class ProductListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return product_queryset().order_by("name", "id")

    def get(self, request):
        return Response(
            AdminProductSerializer(
                self.get_queryset(),
                many=True,
                context={"request": request},
            ).data
        )

    def post(self, request):
        serializer = AdminProductSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        product = self.get_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return product_queryset()

    def get_product(self, product_id):
        return get_object_or_404(self.get_queryset(), id=product_id)

    def get(self, request, product_id):
        product = self.get_product(product_id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data
        )

    def patch(self, request, product_id):
        product = self.get_product(product_id)
        serializer = AdminProductSerializer(
            product,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        product = self.get_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data
        )

    def put(self, request, product_id):
        product = self.get_product(product_id)
        serializer = AdminProductSerializer(
            product,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        product = self.get_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data
        )

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


class ProductSendNotificationView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, product_id):
        get_object_or_404(Product, id=product_id)
        request_id = serializers.UUIDField().run_validation(
            request.data.get("request_id")
        )
        from notifications.product_services import dispatch_product_notifications

        dispatch = dispatch_product_notifications(
            product_id,
            request_id,
            request.user.id,
        )
        return Response(
            {
                "dispatch_id": dispatch.id,
                "request_id": str(dispatch.request_id),
                "status": dispatch.status,
                "recipient_count": dispatch.recipient_count,
                "notification_count": dispatch.notification_count,
                "sent_at": dispatch.completed_at,
            }
        )


class ProductImageCollectionView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, product_id):
        product = get_object_or_404(product_queryset(), id=product_id)
        serializer = ProductImageUploadSerializer(
            data=request.data,
            context={"product": product, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        add_product_images(
            product.id,
            serializer.validated_data["images"],
            serializer.validated_data.get("primary_image_index"),
        )
        product = product_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class ProductImageDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_product_image(self, product_id, image_id):
        product = get_object_or_404(product_queryset(), id=product_id)
        get_object_or_404(ProductImage, id=image_id, product=product)
        return product

    def patch(self, request, product_id, image_id):
        product = self.get_product_image(product_id, image_id)
        serializer = ProductImagePrimarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_primary_product_image(product.id, image_id)
        product = product_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data
        )

    def delete(self, request, product_id, image_id):
        product = self.get_product_image(product_id, image_id)
        delete_product_image(product.id, image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductImageReorderView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, product_id):
        product = get_object_or_404(product_queryset(), id=product_id)
        serializer = ProductImageReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reorder_product_images(
            product.id,
            serializer.validated_data["image_ids"],
        )
        product = product_queryset().get(id=product.id)
        return Response(
            AdminProductSerializer(
                product,
                context={"request": request},
            ).data
        )


class ProductLikeListView(APIView):
    permission_classes = [IsAuthenticated, IsClientRole]

    def get(self, request):
        products = (
            product_queryset()
            .filter(liked_by=request.user)
            .order_by("name", "id")
        )
        return Response(
            LikedProductSerializer(
                products,
                many=True,
                context={"request": request},
            ).data
        )


class ProductLikeToggleView(APIView):
    permission_classes = [IsAuthenticated, IsClientRole]

    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        if product.liked_by.filter(id=request.user.id).exists():
            product.liked_by.remove(request.user)
            liked = False
        else:
            product.liked_by.add(request.user)
            liked = True
        return Response(
            {
                "product_id": product.id,
                "liked": liked,
            }
        )


class ProductUnlikeView(APIView):
    permission_classes = [IsAuthenticated, IsClientRole]

    def delete(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        product.liked_by.remove(request.user)
        return Response(
            {
                "product_id": product.id,
                "liked": False,
            }
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
