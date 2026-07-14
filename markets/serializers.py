from django.db import transaction
from rest_framework import serializers

from catalog.models import (
    Product,
    ProductAddition,
    ProductAttribute,
    ProductAttributeOption,
    ProductAttributeValue,
    ProductCategory,
    ProductVariant,
    VariantAttributeValue,
)
from catalog.serializers import ProductImageSerializer
from locations.models import DeliveryArea, ServiceCity
from offers.models import Offer

from .models import Market, MarketClassification


class AdminMarketClassificationSerializer(serializers.ModelSerializer):
    max_active_featured_classifications = 4

    class Meta:
        model = MarketClassification
        fields = (
            "id",
            "name",
            "description",
            "image",
            "classification_type",
            "is_active",
        )

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

    def validate(self, attrs):
        classification_type = attrs.get(
            "classification_type",
            getattr(
                self.instance,
                "classification_type",
                MarketClassification.ClassificationType.NORMAL,
            ),
        )
        is_active = attrs.get(
            "is_active",
            getattr(self.instance, "is_active", True),
        )

        if (
            classification_type
            == MarketClassification.ClassificationType.FEATURED
            and is_active
        ):
            featured = MarketClassification.objects.filter(
                classification_type=MarketClassification.ClassificationType.FEATURED,
                is_active=True,
            )
            if self.instance is not None:
                featured = featured.exclude(pk=self.instance.pk)
            if featured.count() >= self.max_active_featured_classifications:
                raise serializers.ValidationError(
                    {
                        "classification_type": (
                            "Only four active featured market classifications "
                            "are allowed."
                        )
                    }
                )

        return attrs


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


class ServiceCitySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCity
        fields = (
            "id",
            "name",
            "delivery_price",
            "is_active",
        )


class DeliveryAreaRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        return DeliveryAreaSummarySerializer(value).data


class ServiceCityRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        return ServiceCitySummarySerializer(value).data


class HomeMarketSerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)
    service_cities = ServiceCitySummarySerializer(many=True, read_only=True)
    delivery_areas = DeliveryAreaSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Market
        fields = (
            "id",
            "name",
            "description",
            "image",
            "branch",
            "scope",
            "status",
            "is_popular",
            "classification_id",
            "service_cities",
            "delivery_areas",
        )


class HomeMarketClassificationSerializer(serializers.ModelSerializer):
    markets = serializers.SerializerMethodField()

    class Meta:
        model = MarketClassification
        fields = (
            "id",
            "name",
            "description",
            "image",
            "classification_type",
            "markets",
        )

    def get_markets(self, classification):
        eligible_market_ids = self.context["eligible_market_ids"]
        markets = classification.markets.filter(
            id__in=eligible_market_ids,
            status=Market.Status.ACTIVE,
        ).prefetch_related("service_cities", "delivery_areas").order_by("name")
        return HomeMarketSerializer(markets, many=True).data


class AdminMarketSerializer(serializers.ModelSerializer):
    send_notification = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
    )
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
    service_city_ids = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        source="service_cities",
        many=True,
        required=False,
        write_only=True,
    )
    service_cities = ServiceCityRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        many=True,
        required=False,
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
            "description",
            "image",
            "branch",
            "scope",
            "status",
            "is_popular",
            "send_notification",
            "service_cities",
            "service_city_ids",
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
        if "delivery_areas" in self.initial_data and "delivery_area_ids" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "delivery_areas": (
                        "Use either delivery_areas or delivery_area_ids, not both."
                    )
                }
            )
        if "service_cities" in self.initial_data and "service_city_ids" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "service_cities": (
                        "Use either service_cities or service_city_ids, not both."
                    )
                }
            )

        scope = attrs.get(
            "scope",
            getattr(self.instance, "scope", Market.Scope.SERVICE_CITY),
        )
        service_cities = attrs.get("service_cities")
        delivery_areas = attrs.get("delivery_areas")
        if service_cities is None and delivery_areas is not None:
            service_cities = list(
                ServiceCity.objects.filter(
                    delivery_areas__in=delivery_areas,
                    is_active=True,
                ).distinct()
            )
            attrs["service_cities"] = service_cities

        if scope == Market.Scope.GENERAL:
            if service_cities:
                raise serializers.ValidationError(
                    {
                        "service_city_ids": (
                            "General markets cannot target a service city."
                        )
                    }
                )
            attrs["service_cities"] = []
            return attrs

        existing_count = (
            self.instance.service_cities.count()
            if self.instance is not None and service_cities is None
            else 0
        )
        if service_cities is not None:
            if not service_cities:
                raise serializers.ValidationError(
                    {"service_city_ids": "At least one service city is required."}
                )
            if len(service_cities) > 1:
                raise serializers.ValidationError(
                    {"service_city_ids": "Only one service city may be selected."}
                )
        elif existing_count > 1:
            raise serializers.ValidationError(
                {"service_city_ids": "Only one service city may be selected."}
            )
        elif self.instance is None or existing_count == 0:
            raise serializers.ValidationError(
                {"service_city_ids": "At least one service city is required."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        send_notification = validated_data.pop("send_notification", False)
        delivery_areas = validated_data.pop("delivery_areas", [])
        service_cities = validated_data.pop("service_cities", [])
        market = Market.objects.create(**validated_data)
        market.service_cities.set(service_cities)
        market.delivery_areas.set(delivery_areas)
        if send_notification:
            from notifications.market_services import (
                create_market_notification_intent,
            )

            request = self.context.get("request")
            requested_by_id = (
                request.user.id
                if request is not None and request.user.is_authenticated
                else None
            )
            create_market_notification_intent(market, requested_by_id)
        return market

    def update(self, instance, validated_data):
        validated_data.pop("send_notification", None)
        delivery_areas = validated_data.pop("delivery_areas", None)
        service_cities = validated_data.pop("service_cities", None)
        instance = super().update(instance, validated_data)
        if service_cities is not None:
            instance.service_cities.set(service_cities)
        if delivery_areas is not None:
            instance.delivery_areas.set(delivery_areas)
        return instance


class MarketClassificationCountSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)
    market_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MarketClassification
        fields = (
            "id",
            "name",
            "description",
            "image",
            "classification_type",
            "product_count",
            "market_count",
        )


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
        fields = ("id", "price")


class HomeProductAttributeOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttributeOption
        fields = ("id", "value", "sort_order")


class HomeProductAttributeSerializer(serializers.ModelSerializer):
    options = HomeProductAttributeOptionSerializer(many=True, read_only=True)

    class Meta:
        model = ProductAttribute
        fields = ("id", "name", "sort_order", "options")


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
    attribute_id = serializers.SerializerMethodField()
    attribute_name = serializers.SerializerMethodField()
    option_id = serializers.SerializerMethodField()
    option_value = serializers.SerializerMethodField()

    class Meta:
        model = VariantAttributeValue
        fields = (
            "id",
            "attribute_id",
            "attribute_name",
            "option_id",
            "option_value",
        )

    def get_attribute_id(self, value):
        return value.product_attribute_id or value.attribute_id

    def get_attribute_name(self, value):
        if value.product_attribute_id:
            return value.product_attribute.name
        if value.attribute_id:
            return value.attribute.name
        return ""

    def get_option_id(self, value):
        return value.product_attribute_option_id or value.option_id

    def get_option_value(self, value):
        if value.product_attribute_option_id:
            return value.product_attribute_option.value
        if value.option_id:
            return value.option.value
        return ""


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
    market = HomeMarketSerializer(read_only=True)
    variants = HomeVariantSerializer(many=True, read_only=True)
    attributes = HomeProductAttributeSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "image",
            "images",
            "discount",
            "theme",
            "is_popular",
            "is_available",
            "market",
            "attributes",
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
    images = ProductImageSerializer(many=True, read_only=True)
    variants = HomeVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "image",
            "images",
            "discount",
            "theme",
            "is_popular",
            "variants",
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


class MarketWithStoreProductsSerializer(HomeMarketSerializer):
    product_count = serializers.IntegerField(read_only=True)
    products = serializers.SerializerMethodField()

    class Meta:
        model = Market
        fields = (
            "id",
            "name",
            "image",
            "branch",
            "status",
            "is_popular",
            "classification_id",
            "product_count",
            "products",
            "created_at",
        )

    def get_products(self, market):
        products_by_market = self.context["products_by_market"]
        products = products_by_market.get(market.id, [])
        return MarketClassificationProductSerializer(
            products,
            many=True,
            context=self.context,
        ).data


class StoreMarketClassificationSerializer(MarketClassificationCountSerializer):
    markets = serializers.SerializerMethodField()

    class Meta(MarketClassificationCountSerializer.Meta):
        fields = MarketClassificationCountSerializer.Meta.fields + ("markets",)

    def get_markets(self, classification):
        markets_by_classification = self.context["markets_by_classification"]
        markets = markets_by_classification.get(classification.id, [])
        return MarketWithStoreProductsSerializer(
            markets,
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
    is_multi_market = serializers.SerializerMethodField()
    market_count = serializers.SerializerMethodField()
    markets = serializers.SerializerMethodField()
    market_names_summary = serializers.SerializerMethodField()
    market = HomeMarketSerializer(read_only=True)
    products = serializers.SerializerMethodField()
    service_cities = ServiceCitySummarySerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = (
            "id",
            "show_in_general",
            "service_cities",
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
            "announcement_url",
            "announcement_cta_label",
            "announcement_priority",
            "announcement_display_seconds",
            "status",
            "market",
            "products",
            "is_multi_market",
            "market_count",
            "markets",
            "market_names_summary",
        )

    def _markets(self, instance):
        values = {product.market_id: product.market for product in instance.products.all() if product.market_id}
        return [values[key] for key in sorted(values)]

    def get_products(self, instance):
        offer_items = list(instance.items.all())
        if not offer_items:
            return HomeProductSerializer(
                instance.products.all(),
                many=True,
                context=self.context,
            ).data

        products = []
        for item in offer_items:
            product_data = dict(
                HomeProductSerializer(
                    item.variant.product,
                    context=self.context,
                ).data
            )
            product_data["variants"] = [
                ProductDetailVariantSerializer(
                    item.variant,
                    context=self.context,
                ).data
            ]
            product_data["offer_variant_id"] = item.variant_id
            product_data["offer_quantity"] = item.quantity
            product_data["apply_product_discount"] = item.apply_product_discount
            products.append(product_data)
        return products

    def get_markets(self, instance):
        return [{"id": market.id, "name": market.name, "branch": market.branch} for market in self._markets(instance)]

    def get_market_count(self, instance):
        return len(self._markets(instance))

    def get_is_multi_market(self, instance):
        return self.get_market_count(instance) > 1

    def get_market_names_summary(self, instance):
        return "، ".join(market.name for market in self._markets(instance))
