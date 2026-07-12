import json
import hashlib
import copy

from django.db import transaction
from rest_framework import serializers

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
    VariantAttributeValue,
)
from markets.models import Market
from .product_images import (
    PRODUCT_IMAGE_MAX_COUNT,
    add_product_images,
    clear_primary_product_image,
    validate_product_image_upload,
)


def deduplicate_image_uploads(uploads):
    unique_uploads = []
    upload_indexes = []
    seen_hashes = {}
    for upload in uploads:
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)
        fingerprint = digest.hexdigest()
        if fingerprint not in seen_hashes:
            seen_hashes[fingerprint] = len(unique_uploads)
            unique_uploads.append(upload)
        upload_indexes.append(seen_hashes[fingerprint])
    return unique_uploads, upload_indexes


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


class AdminProductSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = Product
        fields = (
            "id",
            "market",
            "market_id",
            "category",
            "category_id",
            "theme",
            "is_popular",
            "is_available",
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
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_name(self, value):
        return value.strip()

    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            data = copy.copy(data)
        else:
            data = dict(data)
        if hasattr(data, "getlist"):
            uploads = data.getlist("images")
            if uploads:
                data.setlist("image_uploads", uploads)
        elif isinstance(data.get("images"), (list, tuple)):
            data["image_uploads"] = list(data["images"])
        for key in ("attributes", "variants", "attribute_values", "additions"):
            value = data.get(key)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith("[") or stripped.startswith("{"):
                    try:
                        data[key] = json.loads(stripped)
                    except json.JSONDecodeError:
                        raise serializers.ValidationError(
                            {key: "Invalid JSON payload."}
                        )
        return super().to_internal_value(data)

    def validate(self, attrs):
        repeated_uploads = list(attrs.get("image_uploads", []))
        legacy_image = attrs.get("image", serializers.empty)
        uploads = list(repeated_uploads)
        if legacy_image is not serializers.empty and legacy_image is not None:
            uploads.append(legacy_image)

        if uploads:
            unique_uploads, upload_indexes = deduplicate_image_uploads(uploads)
            attrs["image_uploads"] = unique_uploads

            primary_index = attrs.get("primary_image_index")
            if primary_index is not None:
                selectable_count = len(repeated_uploads) or len(uploads)
                if primary_index >= selectable_count:
                    raise serializers.ValidationError(
                        {"primary_image_index": "Invalid primary image index."}
                    )
                attrs["primary_image_index"] = upload_indexes[primary_index]
            elif legacy_image is not serializers.empty and not repeated_uploads:
                attrs["primary_image_index"] = upload_indexes[0]

            existing_count = self.instance.images.count() if self.instance else 0
            if existing_count + len(unique_uploads) > PRODUCT_IMAGE_MAX_COUNT:
                raise serializers.ValidationError(
                    {"images": "A product can have at most 10 images."}
                )
        elif "primary_image_index" in attrs:
            raise serializers.ValidationError(
                {"primary_image_index": "Upload images before selecting a primary."}
            )

        category = attrs.get("category") or getattr(self.instance, "category", None)
        legacy_attribute_values = attrs.get("attribute_values", [])
        if legacy_attribute_values and category is not None:
            self._validate_legacy_attribute_values(legacy_attribute_values, category)
        attributes = attrs.get("attributes")
        variants = attrs.get("variants")
        if attributes is not None:
            self._validate_attribute_payload(attributes)
        if variants is not None:
            for variant in variants:
                legacy_values = variant.get("attribute_values", [])
                if legacy_values and category is not None:
                    self._validate_legacy_attribute_values(legacy_values, category)
            self._validate_variant_payload(attributes, variants)
        self._validate_sale_variants(attrs, variants)
        return attrs

    def _validate_sale_variants(self, attrs, variants):
        is_available = attrs.get(
            "is_available",
            self.instance.is_available if self.instance is not None else True,
        )

        if variants is not None:
            has_valid_variant = bool(variants) and all(
                variant.get("price") is not None and variant["price"] >= 0
                for variant in variants
            )
        elif self.instance is not None:
            has_valid_variant = self.instance.variants.filter(price__gte=0).exists()
        else:
            has_valid_variant = False

        if is_available and not has_valid_variant:
            raise serializers.ValidationError(
                {"variants": self.SALE_VARIANT_ERROR}
            )

        if is_available and "attributes" in attrs and variants is None:
            raise serializers.ValidationError(
                {"variants": self.SALE_VARIANT_ERROR}
            )

        if variants is not None and any(
            variant.get("price") is None or variant["price"] < 0
            for variant in variants
        ):
            raise serializers.ValidationError(
                {"variants": self.SALE_VARIANT_ERROR}
            )

    def _validate_legacy_attribute_values(self, attribute_values, category):
        seen_attribute_ids = set()
        for value in attribute_values:
            attribute = value["attribute"]
            option = value["option"]
            if attribute.category_id != category.id:
                raise serializers.ValidationError(
                    {
                        "attribute_values": (
                            "Attribute must belong to the selected product category."
                        )
                    }
                )
            if option.attribute_id != attribute.id:
                raise serializers.ValidationError(
                    {
                        "attribute_values": (
                            "Option must belong to the selected attribute."
                        )
                    }
                )
            if attribute.id in seen_attribute_ids:
                raise serializers.ValidationError(
                    {"attribute_values": "Each attribute can be used only once."}
                )
            seen_attribute_ids.add(attribute.id)

    def _validate_attribute_payload(self, attributes):
        names = set()
        for index, attribute in enumerate(attributes, start=1):
            name = attribute.get("name", "").strip()
            if not name:
                raise serializers.ValidationError(
                    {"attributes": f"Attribute {index} name is required."}
                )
            normalized_name = name.casefold()
            if normalized_name in names:
                raise serializers.ValidationError(
                    {"attributes": "Attribute names must be unique per product."}
                )
            names.add(normalized_name)
            option_values = set()
            for option in attribute.get("options", []):
                value = option.get("value", "").strip()
                if not value:
                    raise serializers.ValidationError(
                        {"attributes": f"Option value is required for {name}."}
                    )
                normalized_value = value.casefold()
                if normalized_value in option_values:
                    raise serializers.ValidationError(
                        {"attributes": f"Option values must be unique for {name}."}
                    )
                option_values.add(normalized_value)

    def _validate_variant_payload(self, attributes, variants):
        expected_count = len(attributes or [])
        if expected_count == 0 and len(variants) > 1:
            raise serializers.ValidationError(
                {"variants": "Only one base variant is allowed without attributes."}
            )
        seen_combinations = {}
        expected_attribute_keys = {
            str(attribute.get("client_id") or attribute.get("id"))
            for attribute in attributes or []
        }
        for index, variant in enumerate(variants, start=1):
            selections = self._variant_selections(variant)
            if expected_count and len(selections) != expected_count:
                raise serializers.ValidationError(
                    {"variants": f"Variant {index} is missing attribute selections."}
                )
            if expected_attribute_keys:
                selected_attribute_keys = {
                    str(
                        selection.get("attribute_client_id")
                        or selection.get("attribute_id")
                    )
                    for selection in selections
                }
                if selected_attribute_keys != expected_attribute_keys:
                    raise serializers.ValidationError(
                        {
                            "variants": (
                                f"Variant {index} must select exactly one option "
                                "for every product attribute."
                            )
                        }
                    )
            key = tuple(
                sorted(
                    (
                        str(selection.get("attribute_id") or selection.get("attribute_client_id")),
                        str(selection.get("option_id") or selection.get("option_client_id")),
                    )
                    for selection in selections
                )
            )
            if key in seen_combinations:
                raise serializers.ValidationError(
                    {
                        "variants": (
                            f"Variant {index} duplicates variant "
                            f"{seen_combinations[key]}."
                        )
                    }
                )
            seen_combinations[key] = index

    def _variant_selections(self, variant):
        selections = variant.get("selections")
        if selections is None:
            selections = variant.get("attribute_values", [])
        return selections or []

    @transaction.atomic
    def create(self, validated_data):
        uploads = validated_data.pop("image_uploads", [])
        primary_image_index = validated_data.pop("primary_image_index", None)
        validated_data.pop("image", None)
        attribute_values = validated_data.pop("attribute_values", [])
        attributes = validated_data.pop("attributes", [])
        variants = validated_data.pop("variants", [])
        additions = validated_data.pop("additions", [])
        product = Product.objects.create(**validated_data)
        self._replace_product_attribute_values(product, attribute_values)
        self._replace_attributes(product, attributes)
        self._replace_variants(product, variants)
        product.additions.set(additions)
        if uploads:
            add_product_images(product.id, uploads, primary_image_index)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        uploads = validated_data.pop("image_uploads", [])
        primary_image_index = validated_data.pop("primary_image_index", None)
        legacy_image = validated_data.pop("image", serializers.empty)
        attribute_values = validated_data.pop("attribute_values", None)
        attributes = validated_data.pop("attributes", None)
        variants = validated_data.pop("variants", None)
        additions = validated_data.pop("additions", None)
        instance = super().update(instance, validated_data)
        if attribute_values is not None:
            self._replace_product_attribute_values(instance, attribute_values)
        if attributes is not None:
            self._replace_attributes(instance, attributes)
        if variants is not None:
            self._replace_variants(instance, variants)
        if additions is not None:
            instance.additions.set(additions)
        if uploads:
            add_product_images(instance.id, uploads, primary_image_index)
            instance.refresh_from_db(fields=("image", "updated_at"))
        elif legacy_image is None:
            clear_primary_product_image(instance.id)
            instance.refresh_from_db(fields=("image", "updated_at"))
        return instance

    def _replace_product_attribute_values(self, product, attribute_values):
        product.attribute_values.all().delete()
        ProductAttributeValue.objects.bulk_create(
            ProductAttributeValue(product=product, **value)
            for value in attribute_values
        )

    def _replace_variants(self, product, variants):
        product.variants.all().delete()
        attributes_by_id = {attribute.id: attribute for attribute in product.attributes.all()}
        attributes_by_client_id = getattr(self, "_attribute_client_map", {})
        options_by_id = {
            option.id: option
            for option in ProductAttributeOption.objects.filter(
                attribute__product=product
            ).select_related("attribute")
        }
        options_by_client_id = getattr(self, "_option_client_map", {})
        for variant_data in variants:
            selections = self._variant_selections(variant_data)
            variant_data.pop("selections", None)
            variant_data.pop("attribute_values", None)
            variant = ProductVariant.objects.create(
                product=product,
                **variant_data,
            )
            values = []
            for selection in selections:
                legacy_attribute = selection.get("attribute")
                legacy_option = selection.get("option")
                if legacy_attribute is not None and legacy_option is not None:
                    if legacy_option.attribute_id != legacy_attribute.id:
                        raise serializers.ValidationError(
                            {"variants": "Option must belong to the selected attribute."}
                        )
                    values.append(
                        VariantAttributeValue(
                            variant=variant,
                            attribute=legacy_attribute,
                            option=legacy_option,
                        )
                    )
                    continue
                attribute = None
                option = None
                attribute_id = selection.get("attribute_id")
                option_id = selection.get("option_id")
                attribute_client_id = selection.get("attribute_client_id")
                option_client_id = selection.get("option_client_id")
                if attribute_id is not None:
                    attribute = attributes_by_id.get(int(attribute_id))
                elif attribute_client_id is not None:
                    attribute = attributes_by_client_id.get(str(attribute_client_id))
                if option_id is not None:
                    option = options_by_id.get(int(option_id))
                elif option_client_id is not None:
                    option = options_by_client_id.get(str(option_client_id))
                if attribute is None or option is None:
                    raise serializers.ValidationError(
                        {"variants": "Every selection must include valid attribute and option."}
                    )
                if option.attribute_id != attribute.id:
                    raise serializers.ValidationError(
                        {"variants": "Option must belong to the selected attribute."}
                    )
                values.append(
                    VariantAttributeValue(
                        variant=variant,
                        product_attribute=attribute,
                        product_attribute_option=option,
                    )
                )
            VariantAttributeValue.objects.bulk_create(values)

    def _replace_attributes(self, product, attributes):
        product.attributes.all().delete()
        self._attribute_client_map = {}
        self._option_client_map = {}
        for attr_index, attribute_data in enumerate(attributes, start=1):
            options = attribute_data.pop("options", [])
            client_id = attribute_data.pop("client_id", None)
            attribute_data.pop("id", None)
            attribute = ProductAttribute.objects.create(
                product=product,
                sort_order=attribute_data.pop("sort_order", attr_index - 1),
                **attribute_data,
            )
            if client_id:
                self._attribute_client_map[str(client_id)] = attribute
            for option_index, option_data in enumerate(options, start=1):
                option_client_id = option_data.pop("client_id", None)
                option_data.pop("id", None)
                option = ProductAttributeOption.objects.create(
                    attribute=attribute,
                    sort_order=option_data.pop("sort_order", option_index - 1),
                    **option_data,
                )
                if option_client_id:
                    self._option_client_map[str(option_client_id)] = option


class LikedProductSerializer(serializers.ModelSerializer):
    class LikedProductVariantSerializer(serializers.ModelSerializer):
        class Meta:
            model = ProductVariant
            fields = ("id", "price")

    market = MarketSummarySerializer(read_only=True)
    variants = LikedProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "market",
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
