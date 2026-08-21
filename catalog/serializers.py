import json

from django.db import transaction
from rest_framework import serializers

from config.image_validation import validate_safe_image

from .models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductImage,
    ProductCategory,
    ProductAddition,
    ProductAttribute,
    ProductAttributeOption,
    ProductAttributeValue,
    ProductVariant,
    StoreSubcategory,
    VariantAttributeValue,
)
from markets.models import Market, MarketSubcategory
from .admin_product_serializers import AdminProductWriteMixin
from .product_images import (
    PRODUCT_IMAGE_MAX_COUNT,
    add_product_images,
    clear_primary_product_image,
    validate_product_image_upload,
)
from .serializer_utils import deduplicate_image_uploads


class AdditionClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdditionClassification
        fields = ("id", "name")

    def validate_name(self, value):
        name = value.strip()
        queryset = AdditionClassification.objects.filter(name__iexact=name)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "An addition classification with this name already exists."
            )
        return name


class CategoryClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryClassification
        fields = ("id", "name")

    def validate_name(self, value):
        name = value.strip()
        queryset = CategoryClassification.objects.filter(name__iexact=name)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A category classification with this name already exists."
            )
        return name


class ProductCategorySerializer(serializers.ModelSerializer):
    classification_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoryClassification.objects.all(),
        source="classification",
        write_only=True,
    )
    classification = CategoryClassificationSerializer(read_only=True)

    class Meta:
        model = ProductCategory
        fields = (
            "id",
            "classification",
            "classification_id",
            "name",
            "type",
            "description",
            "image",
        )

    def validate_name(self, value):
        return value.strip()

    def validate_type(self, value):
        return value.strip()

    def validate_image(self, value):
        return validate_safe_image(value)


class StoreSubcategorySerializer(serializers.ModelSerializer):
    market_count = serializers.IntegerField(read_only=True)
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = StoreSubcategory
        fields = (
            "id",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "image",
            "is_active",
            "market_count",
            "product_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "market_count",
            "product_count",
            "created_at",
            "updated_at",
        )

    def validate_name_ar(self, value):
        return self._validate_unique_name(value, "name_ar")

    def validate_name_en(self, value):
        return self._validate_unique_name(value, "name_en")

    def _validate_unique_name(self, value, field_name):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("This field may not be blank.")
        queryset = StoreSubcategory.objects.filter(
            **{f"{field_name}__iexact": name}
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A store subcategory with this name already exists."
            )
        return name

    def validate_description_ar(self, value):
        return value.strip()

    def validate_description_en(self, value):
        return value.strip()

    def validate_image(self, value):
        return validate_safe_image(value)


class ProductSubcategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSubcategory
        fields = (
            "id",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "image",
            "is_active",
        )


class CategoryOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryOption
        fields = ("id", "value")


class AdminCategoryOptionSerializer(serializers.ModelSerializer):
    attribute_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoryAttribute.objects.all(),
        source="attribute",
        write_only=True,
    )
    attribute = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CategoryOption
        fields = ("id", "attribute", "attribute_id", "value")

    def get_attribute(self, option):
        return {
            "id": option.attribute_id,
            "name": option.attribute.name,
            "category_id": option.attribute.category_id,
        }

    def validate_value(self, value):
        return value.strip()

    def validate(self, attrs):
        attribute = attrs.get("attribute") or getattr(self.instance, "attribute", None)
        value = attrs.get("value") or getattr(self.instance, "value", None)
        if attribute is None or value is None:
            return attrs

        queryset = CategoryOption.objects.filter(
            attribute=attribute,
            value__iexact=value,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"value": "This option already exists for this attribute."}
            )
        return attrs


class CategoryAttributeSerializer(serializers.ModelSerializer):
    options = CategoryOptionSerializer(many=True, read_only=True)

    class Meta:
        model = CategoryAttribute
        fields = ("id", "name", "options")


class AdminCategoryAttributeSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        source="category",
        write_only=True,
    )
    category = ProductCategorySerializer(read_only=True)
    options = CategoryOptionSerializer(many=True, read_only=True)

    class Meta:
        model = CategoryAttribute
        fields = ("id", "category", "category_id", "name", "options")

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        category = attrs.get("category") or getattr(self.instance, "category", None)
        name = attrs.get("name") or getattr(self.instance, "name", None)
        if category is None or name is None:
            return attrs

        queryset = CategoryAttribute.objects.filter(
            category=category,
            name__iexact=name,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"name": "This attribute already exists for this category."}
            )
        return attrs


class ProductCategoryDetailSerializer(ProductCategorySerializer):
    attributes = CategoryAttributeSerializer(many=True, read_only=True)

    class Meta(ProductCategorySerializer.Meta):
        fields = ProductCategorySerializer.Meta.fields + ("attributes",)


class ProductAttributeOptionSerializer(serializers.ModelSerializer):
    client_id = serializers.CharField(required=False, write_only=True)

    class Meta:
        model = ProductAttributeOption
        fields = ("id", "client_id", "value", "sort_order")
        read_only_fields = ("id",)

    def validate_value(self, value):
        return value.strip()


class ProductAttributeSerializer(serializers.ModelSerializer):
    client_id = serializers.CharField(required=False, write_only=True)
    options = ProductAttributeOptionSerializer(many=True, required=False)

    class Meta:
        model = ProductAttribute
        fields = ("id", "client_id", "name", "sort_order", "options")
        read_only_fields = ("id",)

    def validate_name(self, value):
        return value.strip()


class MarketSummarySerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Market
        fields = ("id", "name", "branch", "status", "classification_id")


class AttributeValueSerializer(serializers.ModelSerializer):
    attribute_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoryAttribute.objects.all(),
        source="attribute",
        write_only=True,
    )
    option_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoryOption.objects.all(),
        source="option",
        write_only=True,
    )
    attribute = CategoryAttributeSerializer(read_only=True)
    option = CategoryOptionSerializer(read_only=True)

    class Meta:
        model = ProductAttributeValue
        fields = ("id", "attribute", "attribute_id", "option", "option_id")


class VariantAttributeValueSerializer(AttributeValueSerializer):
    product_attribute_id = serializers.IntegerField(read_only=True)
    product_attribute_option_id = serializers.IntegerField(read_only=True)
    attribute_name = serializers.SerializerMethodField()
    option_value = serializers.SerializerMethodField()

    class Meta:
        model = VariantAttributeValue
        fields = (
            "id",
            "attribute",
            "attribute_id",
            "option",
            "option_id",
            "product_attribute_id",
            "product_attribute_option_id",
            "attribute_name",
            "option_value",
        )

    def get_attribute_name(self, value):
        if value.product_attribute_id:
            return value.product_attribute.name
        if value.attribute_id:
            return value.attribute.name
        return ""

    def get_option_value(self, value):
        if value.product_attribute_option_id:
            return value.product_attribute_option.value
        if value.option_id:
            return value.option.value
        return ""


class ProductVariantSerializer(serializers.ModelSerializer):
    attribute_values = VariantAttributeValueSerializer(many=True, required=False)
    selections = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = ProductVariant
        fields = ("id", "price", "sku", "attribute_values", "selections")
        read_only_fields = ("id",)

    def validate_sku(self, value):
        return value.strip()


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("id", "url", "image", "is_primary", "sort_order")

    def get_url(self, product_image):
        if not product_image.image:
            return None
        try:
            url = product_image.image.url
        except ValueError:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class ProductImageUploadSerializer(serializers.Serializer):
    images = serializers.ListField(
        child=serializers.ImageField(
            validators=[validate_product_image_upload],
        ),
        allow_empty=False,
    )
    primary_image_index = serializers.IntegerField(
        required=False,
        min_value=0,
    )

    def validate(self, attrs):
        uploads = attrs["images"]
        primary_index = attrs.get("primary_image_index")
        if primary_index is not None and primary_index >= len(uploads):
            raise serializers.ValidationError(
                {"primary_image_index": "Invalid primary image index."}
            )
        unique_uploads, upload_indexes = deduplicate_image_uploads(uploads)
        product = self.context["product"]
        if product.images.count() + len(unique_uploads) > PRODUCT_IMAGE_MAX_COUNT:
            raise serializers.ValidationError(
                {"images": "A product can have at most 10 images."}
            )
        attrs["images"] = unique_uploads
        if primary_index is not None:
            attrs["primary_image_index"] = upload_indexes[primary_index]
        return attrs


class ProductImagePrimarySerializer(serializers.Serializer):
    is_primary = serializers.BooleanField()

    def validate_is_primary(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "An image can only be selected as primary; choose another image instead."
            )
        return value


class ProductImageReorderSerializer(serializers.Serializer):
    image_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )


class AdminProductSerializer(AdminProductWriteMixin, serializers.ModelSerializer):
    SALE_VARIANT_ERROR = (
        "يجب إضافة سعر أو متغير صالح قبل إتاحة المنتج للبيع."
    )
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.all(),
        source="market",
        write_only=True,
    )
    market = MarketSummarySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        source="category",
        write_only=True,
        required=False,
        allow_null=True,
    )
    category = ProductCategoryDetailSerializer(read_only=True)
    subcategory_id = serializers.PrimaryKeyRelatedField(
        queryset=StoreSubcategory.objects.all(),
        source="subcategory",
        write_only=True,
    )
    subcategory = ProductSubcategorySerializer(read_only=True)
    attributes = ProductAttributeSerializer(many=True, required=False)
    attribute_values = AttributeValueSerializer(many=True, required=False)
    variants = ProductVariantSerializer(many=True, required=False)
    additions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ProductAddition.objects.all(),
        required=False,
    )
    images = ProductImageSerializer(many=True, read_only=True)
    image_uploads = serializers.ListField(
        child=serializers.ImageField(
            validators=[validate_product_image_upload],
        ),
        required=False,
        write_only=True,
    )
    image = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_product_image_upload],
    )
    primary_image_index = serializers.IntegerField(
        required=False,
        min_value=0,
        write_only=True,
    )
    deletion_mode = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "market",
            "market_id",
            "category",
            "category_id",
            "subcategory",
            "subcategory_id",
            "theme",
            "is_popular",
            "is_available",
            "archived_at",
            "deletion_mode",
            "name",
            "description",
            "image",
            "images",
            "image_uploads",
            "primary_image_index",
            "discount",
            "attributes",
            "attribute_values",
            "variants",
            "additions",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "archived_at",
            "deletion_mode",
            "created_at",
            "updated_at",
        )

    def get_deletion_mode(self, instance):
        return instance.get_deletion_mode()

    def validate_name(self, value):
        return value.strip()

class LikedProductSerializer(serializers.ModelSerializer):
    class LikedProductVariantSerializer(serializers.ModelSerializer):
        class Meta:
            model = ProductVariant
            fields = ("id", "price")

    market = MarketSummarySerializer(read_only=True)
    variants = LikedProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    subcategory = ProductSubcategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "market",
            "subcategory",
            "theme",
            "is_popular",
            "is_available",
            "name",
            "description",
            "image",
            "images",
            "discount",
            "variants",
        )


class ProductAdditionSerializer(serializers.ModelSerializer):
    classification_id = serializers.PrimaryKeyRelatedField(
        queryset=AdditionClassification.objects.all(),
        source="classification",
        write_only=True,
    )
    classification = AdditionClassificationSerializer(read_only=True)
    products = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = ProductAddition
        fields = (
            "id",
            "classification",
            "classification_id",
            "products",
            "image",
            "name_ar",
            "name_en",
            "price",
            "is_active",
        )

    def validate_name_ar(self, value):
        return value.strip()

    def validate_name_en(self, value):
        return value.strip()

    def validate_image(self, value):
        return validate_safe_image(value)
