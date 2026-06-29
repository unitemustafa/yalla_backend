from rest_framework import serializers

from .models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductCategory,
    ProductAddition,
    ProductAttributeValue,
    ProductVariant,
    VariantAttributeValue,
)
from markets.models import Market


class AdditionClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdditionClassification
        fields = ("id", "name")

    def validate_name(self, value):
        name = value.strip()
        if AdditionClassification.objects.filter(name__iexact=name).exists():
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
    class Meta(AttributeValueSerializer.Meta):
        model = VariantAttributeValue


class ProductVariantSerializer(serializers.ModelSerializer):
    attribute_values = VariantAttributeValueSerializer(many=True, required=False)

    class Meta:
        model = ProductVariant
        fields = ("id", "price", "sku", "attribute_values")
        read_only_fields = ("id",)

    def validate_sku(self, value):
        return value.strip()


class AdminProductSerializer(serializers.ModelSerializer):
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
    )
    category = ProductCategoryDetailSerializer(read_only=True)
    attribute_values = AttributeValueSerializer(many=True, required=False)
    variants = ProductVariantSerializer(many=True, required=False)
    additions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ProductAddition.objects.all(),
        required=False,
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "market",
            "market_id",
            "category",
            "category_id",
            "is_available",
            "name",
            "description",
            "image",
            "discount",
            "attribute_values",
            "variants",
            "additions",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        category = attrs.get("category") or getattr(self.instance, "category", None)
        if category is None:
            return attrs

        self._validate_attribute_values(
            attrs.get("attribute_values", []),
            category,
        )
        for variant in attrs.get("variants", []):
            self._validate_attribute_values(
                variant.get("attribute_values", []),
                category,
            )
        return attrs

    def _validate_attribute_values(self, attribute_values, category):
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

    def create(self, validated_data):
        attribute_values = validated_data.pop("attribute_values", [])
        variants = validated_data.pop("variants", [])
        additions = validated_data.pop("additions", [])
        product = Product.objects.create(**validated_data)
        self._replace_product_attribute_values(product, attribute_values)
        self._replace_variants(product, variants)
        product.additions.set(additions)
        return product

    def update(self, instance, validated_data):
        attribute_values = validated_data.pop("attribute_values", None)
        variants = validated_data.pop("variants", None)
        additions = validated_data.pop("additions", None)
        instance = super().update(instance, validated_data)
        if attribute_values is not None:
            self._replace_product_attribute_values(instance, attribute_values)
        if variants is not None:
            self._replace_variants(instance, variants)
        if additions is not None:
            instance.additions.set(additions)
        return instance

    def _replace_product_attribute_values(self, product, attribute_values):
        product.attribute_values.all().delete()
        ProductAttributeValue.objects.bulk_create(
            ProductAttributeValue(product=product, **value)
            for value in attribute_values
        )

    def _replace_variants(self, product, variants):
        product.variants.all().delete()
        for variant_data in variants:
            attribute_values = variant_data.pop("attribute_values", [])
            variant = ProductVariant.objects.create(
                product=product,
                **variant_data,
            )
            VariantAttributeValue.objects.bulk_create(
                VariantAttributeValue(variant=variant, **value)
                for value in attribute_values
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
