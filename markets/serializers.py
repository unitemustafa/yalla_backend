from rest_framework import serializers

from catalog.models import (
    Product,
    ProductAddition,
    ProductAttributeValue,
    ProductCategory,
    ProductVariant,
    VariantAttributeValue,
)
from locations.models import DeliveryArea
from offers.models import Offer

from .models import Market, MarketClassification


class AdminMarketClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketClassification
        fields = ("id", "name")

    def validate_name(self, value):
        name = value.strip()
        queryset = MarketClassification.objects.filter(name__iexact=name)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A market classification with this name already exists."
            )
        return name


class DeliveryAreaSummarySerializer(serializers.ModelSerializer):
    service_city_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = DeliveryArea
        fields = (
            "id",
            "service_city_id",
            "name",
            "delivery_price",
            "center_latitude",
            "center_longitude",
            "radius_km",
            "is_active",
        )


class DeliveryAreaRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        return DeliveryAreaSummarySerializer(value).data


class HomeMarketSerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)
    delivery_areas = DeliveryAreaSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Market
        fields = (
            "id",
            "name",
            "branch",
            "status",
            "classification_id",
            "delivery_areas",
        )


class HomeMarketClassificationSerializer(serializers.ModelSerializer):
    markets = serializers.SerializerMethodField()

    class Meta:
        model = MarketClassification
        fields = ("id", "name", "markets")

    def get_markets(self, classification):
        eligible_market_ids = self.context["eligible_market_ids"]
        markets = classification.markets.filter(
            id__in=eligible_market_ids,
            status=Market.Status.ACTIVE,
        ).prefetch_related("delivery_areas").order_by("name")
        return HomeMarketSerializer(markets, many=True).data


class AdminMarketSerializer(serializers.ModelSerializer):
    classification_id = serializers.PrimaryKeyRelatedField(
        queryset=MarketClassification.objects.all(),
        source="classification",
        write_only=True,
    )
    classification = AdminMarketClassificationSerializer(read_only=True)
    delivery_area_ids = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryArea.objects.all(),
        source="delivery_areas",
        many=True,
        required=False,
        write_only=True,
    )
    delivery_areas = DeliveryAreaRelatedField(
        queryset=DeliveryArea.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = Market
        fields = (
            "id",
            "classification",
            "classification_id",
            "name",
            "branch",
            "status",
            "delivery_areas",
            "delivery_area_ids",
            "created_at",
            "updated_at",
        )

    def validate_name(self, value):
        return value.strip()

    def validate_branch(self, value):
        return value.strip()

    def validate(self, attrs):
        if (
            "delivery_areas" in self.initial_data
            and "delivery_area_ids" in self.initial_data
        ):
            raise serializers.ValidationError(
                {
                    "delivery_areas": (
                        "Use either delivery_areas or delivery_area_ids, not both."
                    )
                }
            )
        return attrs

    def create(self, validated_data):
        delivery_areas = validated_data.pop("delivery_areas", [])
        market = Market.objects.create(**validated_data)
        market.delivery_areas.set(delivery_areas)
        return market

    def update(self, instance, validated_data):
        delivery_areas = validated_data.pop("delivery_areas", None)
        instance = super().update(instance, validated_data)
        if delivery_areas is not None:
            instance.delivery_areas.set(delivery_areas)
        return instance


class MarketClassificationCountSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MarketClassification
        fields = ("id", "name", "product_count")


class HomeCategorySerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductCategory
        fields = (
            "id",
            "name",
            "type",
            "description",
            "image",
            "classification_id",
        )


class HomeVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "price", "sku")


class ProductAttributeValueSerializer(serializers.ModelSerializer):
    attribute_id = serializers.IntegerField(read_only=True)
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    option_id = serializers.IntegerField(read_only=True)
    option_value = serializers.CharField(source="option.value", read_only=True)

    class Meta:
        model = ProductAttributeValue
        fields = (
            "id",
            "attribute_id",
            "attribute_name",
            "option_id",
            "option_value",
        )


class VariantAttributeValueSerializer(serializers.ModelSerializer):
    attribute_id = serializers.IntegerField(read_only=True)
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    option_id = serializers.IntegerField(read_only=True)
    option_value = serializers.CharField(source="option.value", read_only=True)

    class Meta:
        model = VariantAttributeValue
        fields = (
            "id",
            "attribute_id",
            "attribute_name",
            "option_id",
            "option_value",
        )


class ProductDetailVariantSerializer(HomeVariantSerializer):
    attribute_values = VariantAttributeValueSerializer(many=True, read_only=True)

    class Meta(HomeVariantSerializer.Meta):
        fields = HomeVariantSerializer.Meta.fields + ("attribute_values",)


class ProductAdditionSerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)
    classification_name = serializers.CharField(
        source="classification.name",
        read_only=True,
    )

    class Meta:
        model = ProductAddition
        fields = (
            "id",
            "classification_id",
            "classification_name",
            "image",
            "name_ar",
            "name_en",
            "price",
            "is_active",
        )


class HomeProductSerializer(serializers.ModelSerializer):
    category = HomeCategorySerializer(read_only=True)
    market = HomeMarketSerializer(read_only=True)
    variants = HomeVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "image",
            "discount",
            "category",
            "market",
            "variants",
        )


class ProductDetailSerializer(HomeProductSerializer):
    variants = ProductDetailVariantSerializer(many=True, read_only=True)
    attribute_values = ProductAttributeValueSerializer(many=True, read_only=True)
    additions = ProductAdditionSerializer(many=True, read_only=True)

    class Meta(HomeProductSerializer.Meta):
        fields = HomeProductSerializer.Meta.fields + (
            "attribute_values",
            "additions",
            "created_at",
            "updated_at",
        )


class MarketClassificationProductSerializer(serializers.ModelSerializer):
    category = HomeCategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "image",
            "discount",
            "category",
        )


class MarketClassificationWithProductsSerializer(
    MarketClassificationCountSerializer
):
    products = serializers.SerializerMethodField()

    class Meta(MarketClassificationCountSerializer.Meta):
        fields = MarketClassificationCountSerializer.Meta.fields + ("products",)

    def get_products(self, classification):
        products_by_classification = self.context["products_by_classification"]
        products = products_by_classification.get(classification.id, [])
        return MarketClassificationProductSerializer(
            products,
            many=True,
            context=self.context,
        ).data


class MarketWithCommonProductsSerializer(HomeMarketSerializer):
    products = serializers.SerializerMethodField()

    class Meta(HomeMarketSerializer.Meta):
        fields = HomeMarketSerializer.Meta.fields + ("products",)

    def get_products(self, market):
        products_by_market = self.context["products_by_market"]
        products = products_by_market.get(market.id, [])
        return MarketClassificationProductSerializer(
            products,
            many=True,
            context=self.context,
        ).data


class HomeOfferSerializer(serializers.ModelSerializer):
    market = HomeMarketSerializer(read_only=True)
    products = HomeProductSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = (
            "id",
            "title",
            "description",
            "image",
            "type",
            "discount",
            "start_time",
            "end_time",
            "active_days",
            "use_limits",
            "user_limit",
            "status",
            "market",
            "products",
        )
