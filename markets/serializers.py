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
    StoreSubcategory,
    VariantAttributeValue,
)
from catalog.serializers import ProductImageSerializer, ProductSubcategorySerializer
from locations.models import DeliveryArea, ServiceCity
from offers.models import Offer

from .models import Market, MarketClassification, MarketSubcategory, MarketType


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


class MarketTypeSerializer(serializers.ModelSerializer):
    classification_id = serializers.PrimaryKeyRelatedField(
        queryset=MarketClassification.objects.all(),
        source="classification",
    )
    market_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = MarketType
        fields = (
            "id",
            "classification_id",
            "name_ar",
            "name_en",
            "image",
            "sort_order",
            "is_active",
            "market_count",
        )
        read_only_fields = ("id", "market_count")

    def validate_name_ar(self, value):
        return value.strip()

    def validate_name_en(self, value):
        return value.strip()

    def validate(self, attrs):
        classification = attrs.get(
            "classification",
            getattr(self.instance, "classification", None),
        )
        for field_name in ("name_ar", "name_en"):
            value = attrs.get(field_name, getattr(self.instance, field_name, ""))
            if not value or classification is None:
                continue
            queryset = MarketType.objects.filter(
                classification=classification,
                **{f"{field_name}__iexact": value},
            )
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {field_name: "A market type with this name already exists."}
                )
        return attrs


class ClientMarketTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketType
        fields = (
            "id",
            "name_ar",
            "name_en",
            "image",
            "sort_order",
        )


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


class AssignedStoreSubcategorySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="subcategory_id", read_only=True)
    name_ar = serializers.CharField(
        source="subcategory.name_ar",
        read_only=True,
    )
    name_en = serializers.CharField(
        source="subcategory.name_en",
        read_only=True,
    )
    description_ar = serializers.CharField(
        source="subcategory.description_ar",
        read_only=True,
    )
    description_en = serializers.CharField(
        source="subcategory.description_en",
        read_only=True,
    )
    image = serializers.ImageField(
        source="subcategory.image",
        read_only=True,
        allow_null=True,
    )
    is_active = serializers.BooleanField(
        source="subcategory.is_active",
        read_only=True,
    )

    class Meta:
        model = MarketSubcategory
        fields = (
            "id",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "image",
            "is_active",
            "sort_order",
        )


class HomeMarketSerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)
    service_cities = ServiceCitySummarySerializer(many=True, read_only=True)
    delivery_areas = DeliveryAreaSummarySerializer(many=True, read_only=True)
    subcategories = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True, default=0)
    minimum_product_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    is_liked = serializers.BooleanField(read_only=True, default=False)
    market_type_ids = serializers.PrimaryKeyRelatedField(
        source="market_types",
        many=True,
        read_only=True,
    )

    class Meta:
        model = Market
        fields = (
            "id",
            "name",
            "description",
            "image",
            "cover_image",
            "delivery_time_min_minutes",
            "delivery_time_max_minutes",
            "branch",
            "scope",
            "status",
            "is_popular",
            "product_count",
            "minimum_product_price",
            "is_liked",
            "market_type_ids",
            "classification_id",
            "service_cities",
            "delivery_areas",
            "subcategories",
        )

    def get_subcategories(self, market):
        if "subcategory_assignments" in getattr(
            market,
            "_prefetched_objects_cache",
            {},
        ):
            assignments = sorted(
                (
                    assignment
                    for assignment in market.subcategory_assignments.all()
                    if assignment.subcategory.is_active
                ),
                key=lambda assignment: (
                    assignment.sort_order,
                    assignment.id,
                ),
            )
        else:
            assignments = market.subcategory_assignments.filter(
                subcategory__is_active=True,
            ).select_related("subcategory").order_by("sort_order", "id")
        return AssignedStoreSubcategorySerializer(
            assignments,
            many=True,
            context=self.context,
        ).data


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
        ).with_client_metrics(
            self.context.get("request").user
            if self.context.get("request") is not None
            else None
        ).prefetch_related("service_cities", "delivery_areas").order_by("name")
        return HomeMarketSerializer(markets, many=True).data


class AdminMarketSerializer(serializers.ModelSerializer):
    deletion_mode = serializers.SerializerMethodField()
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
    subcategory_ids = serializers.PrimaryKeyRelatedField(
        queryset=StoreSubcategory.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )
    subcategories = serializers.SerializerMethodField()
    market_type_ids = serializers.PrimaryKeyRelatedField(
        queryset=MarketType.objects.all(),
        source="market_types",
        many=True,
        required=False,
        write_only=True,
    )
    market_types = ClientMarketTypeSerializer(many=True, read_only=True)
    delivery_time_min_minutes = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )
    delivery_time_max_minutes = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
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
            "cover_image",
            "delivery_time_min_minutes",
            "delivery_time_max_minutes",
            "branch",
            "scope",
            "status",
            "archived_at",
            "deletion_mode",
            "is_popular",
            "send_notification",
            "service_cities",
            "service_city_ids",
            "delivery_areas",
            "delivery_area_ids",
            "subcategories",
            "subcategory_ids",
            "market_types",
            "market_type_ids",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "archived_at", "deletion_mode")

    def get_deletion_mode(self, instance):
        return instance.get_deletion_mode()

    def validate_name(self, value):
        return value.strip()

    def validate_branch(self, value):
        return value.strip()

    def validate(self, attrs):
        if self.instance is None:
            required_errors = {}
            if not attrs.get("image"):
                required_errors["image"] = "Store logo is required."
            if not attrs.get("cover_image"):
                required_errors["cover_image"] = "Store cover image is required."
            if attrs.get("delivery_time_min_minutes") is None:
                required_errors["delivery_time_min_minutes"] = (
                    "Minimum delivery time is required."
                )
            if attrs.get("delivery_time_max_minutes") is None:
                required_errors["delivery_time_max_minutes"] = (
                    "Maximum delivery time is required."
                )
            if required_errors:
                raise serializers.ValidationError(required_errors)

        minimum_delivery_time = attrs.get(
            "delivery_time_min_minutes",
            getattr(self.instance, "delivery_time_min_minutes", None),
        )
        maximum_delivery_time = attrs.get(
            "delivery_time_max_minutes",
            getattr(self.instance, "delivery_time_max_minutes", None),
        )
        if (minimum_delivery_time is None) != (maximum_delivery_time is None):
            raise serializers.ValidationError(
                {
                    "delivery_time_max_minutes": (
                        "Both delivery time values must be provided together."
                    )
                }
            )
        if (
            minimum_delivery_time is not None
            and maximum_delivery_time < minimum_delivery_time
        ):
            raise serializers.ValidationError(
                {
                    "delivery_time_max_minutes": (
                        "Maximum delivery time cannot be less than the minimum."
                    )
                }
            )

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

        selected_subcategories = attrs.get("subcategory_ids")
        if (
            self.instance is None
            or selected_subcategories is not None
        ) and not selected_subcategories:
            raise serializers.ValidationError(
                {
                    "subcategory_ids": (
                        "At least one active store subcategory is required."
                    )
                }
            )
        if selected_subcategories is not None:
            if hasattr(self.initial_data, "getlist"):
                raw_ids = self.initial_data.getlist("subcategory_ids")
            else:
                raw_ids = self.initial_data.get("subcategory_ids", [])
            if not isinstance(raw_ids, (list, tuple)):
                raw_ids = [raw_ids]
            normalized_raw_ids = [str(value) for value in raw_ids]
            if len(normalized_raw_ids) != len(set(normalized_raw_ids)):
                raise serializers.ValidationError(
                    {"subcategory_ids": "Subcategories must be unique."}
                )
            existing_ids = (
                set(
                    self.instance.subcategory_assignments.values_list(
                        "subcategory_id",
                        flat=True,
                    )
                )
                if self.instance is not None
                else set()
            )
            newly_added = [
                subcategory
                for subcategory in selected_subcategories
                if subcategory.id not in existing_ids
            ]
            if any(not subcategory.is_active for subcategory in newly_added):
                raise serializers.ValidationError(
                    {
                        "subcategory_ids": (
                            "Only active store subcategories can be assigned."
                        )
                    }
                )
            if self.instance is not None:
                selected_ids = {
                    subcategory.id for subcategory in selected_subcategories
                }
                removed_ids = existing_ids - selected_ids
                if removed_ids and Product.objects.filter(
                    market=self.instance,
                    subcategory_id__in=removed_ids,
                ).exists():
                    raise serializers.ValidationError(
                        {
                            "subcategory_ids": (
                                "Move products to another subcategory before "
                                "removing it from this market."
                            )
                        }
                    )

        selected_market_types = attrs.get("market_types")
        prospective_classification = attrs.get(
            "classification",
            getattr(self.instance, "classification", None),
        )
        if selected_market_types is not None:
            if hasattr(self.initial_data, "getlist"):
                raw_type_ids = self.initial_data.getlist("market_type_ids")
            else:
                raw_type_ids = self.initial_data.get("market_type_ids", [])
            if not isinstance(raw_type_ids, (list, tuple)):
                raw_type_ids = [raw_type_ids]
            normalized_type_ids = [str(value) for value in raw_type_ids]
            if len(normalized_type_ids) != len(set(normalized_type_ids)):
                raise serializers.ValidationError(
                    {"market_type_ids": "Market types must be unique."}
                )
            invalid_types = [
                market_type
                for market_type in selected_market_types
                if (
                    not market_type.is_active
                    or market_type.classification_id
                    != getattr(prospective_classification, "id", None)
                )
            ]
            if invalid_types:
                raise serializers.ValidationError(
                    {
                        "market_type_ids": (
                            "Only active market types from the selected "
                            "classification can be assigned."
                        )
                    }
                )
        elif (
            self.instance is not None
            and prospective_classification is not None
            and prospective_classification.id != self.instance.classification_id
            and self.instance.market_types.exclude(
                classification=prospective_classification
            ).exists()
        ):
            raise serializers.ValidationError(
                {
                    "market_type_ids": (
                        "Select market types that belong to the new classification."
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
        subcategories = validated_data.pop("subcategory_ids")
        market_types = validated_data.pop("market_types", [])
        market = Market.objects.create(**validated_data)
        market.service_cities.set(service_cities)
        market.delivery_areas.set(delivery_areas)
        self._replace_subcategories(market, subcategories)
        market.market_types.set(market_types)
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
        subcategories = validated_data.pop("subcategory_ids", None)
        market_types = validated_data.pop("market_types", None)
        instance = super().update(instance, validated_data)
        if service_cities is not None:
            instance.service_cities.set(service_cities)
        if delivery_areas is not None:
            instance.delivery_areas.set(delivery_areas)
        if subcategories is not None:
            self._replace_subcategories(instance, subcategories)
        if market_types is not None:
            instance.market_types.set(market_types)
        return instance

    def get_subcategories(self, market):
        assignments = market.subcategory_assignments.select_related(
            "subcategory",
        ).order_by("sort_order", "id")
        return AssignedStoreSubcategorySerializer(
            assignments,
            many=True,
            context=self.context,
        ).data

    def _replace_subcategories(self, market, subcategories):
        market.subcategory_assignments.all().delete()
        MarketSubcategory.objects.bulk_create(
            MarketSubcategory(
                market=market,
                subcategory=subcategory,
                sort_order=index,
            )
            for index, subcategory in enumerate(subcategories)
        )
        if hasattr(market, "_prefetched_objects_cache"):
            market._prefetched_objects_cache.pop(
                "subcategory_assignments",
                None,
            )


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
    subcategory = ProductSubcategorySerializer(read_only=True)

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
            "subcategory",
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
    subcategory = ProductSubcategorySerializer(read_only=True)

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
            "subcategory",
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
    products = serializers.SerializerMethodField()

    class Meta:
        model = Market
        fields = (
            "id",
            "name",
            "description",
            "image",
            "cover_image",
            "delivery_time_min_minutes",
            "delivery_time_max_minutes",
            "branch",
            "status",
            "is_popular",
            "product_count",
            "minimum_product_price",
            "is_liked",
            "market_type_ids",
            "classification_id",
            "subcategories",
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
    market_types = serializers.SerializerMethodField()

    class Meta(MarketClassificationCountSerializer.Meta):
        fields = MarketClassificationCountSerializer.Meta.fields + (
            "market_types",
            "markets",
        )

    def get_market_types(self, classification):
        cached_types = getattr(classification, "active_market_types", None)
        if cached_types is None:
            cached_types = classification.market_types.filter(
                is_active=True,
            ).order_by("sort_order", "id")
        return ClientMarketTypeSerializer(
            cached_types,
            many=True,
            context=self.context,
        ).data

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
        return [
            {
                "id": market.id,
                "name": market.name,
                "branch": market.branch,
                "classification_id": market.classification_id,
            }
            for market in self._markets(instance)
        ]

    def get_market_count(self, instance):
        return len(self._markets(instance))

    def get_is_multi_market(self, instance):
        return self.get_market_count(instance) > 1

    def get_market_names_summary(self, instance):
        return "، ".join(market.name for market in self._markets(instance))
