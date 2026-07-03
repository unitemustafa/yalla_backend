from rest_framework import serializers

from catalog.models import Product
from locations.models import ServiceCity
from markets.models import Market
from markets.serializers import AdminMarketSerializer, ServiceCitySummarySerializer

from .models import Offer


class OfferProductSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(read_only=True)
    market_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "market_id",
            "category_id",
            "is_available",
            "name",
            "description",
            "image",
            "discount",
            "created_at",
            "updated_at",
        )


class AdminOfferSerializer(serializers.ModelSerializer):
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.all(),
        source="market",
        write_only=True,
        required=False,
    )
    market = AdminMarketSerializer(read_only=True)
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.all(),
        source="service_city",
        write_only=True,
        required=False,
        allow_null=True,
    )
    service_city = ServiceCitySummarySerializer(read_only=True)
    product_ids = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="products",
        many=True,
        write_only=True,
    )
    products = OfferProductSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = (
            "id",
            "market",
            "market_id",
            "scope",
            "service_city",
            "service_city_id",
            "products",
            "product_ids",
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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_title(self, value):
        return value.strip()

    def validate_description(self, value):
        return value.strip()

    def validate_discount(self, value):
        if value < 0:
            raise serializers.ValidationError("Discount cannot be negative.")
        return value

    def validate_active_days(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Active days must be a list.")
        return value

    def validate(self, attrs):
        market = attrs.get("market") or getattr(self.instance, "market", None)
        products = attrs.get("products")
        scope = attrs.get(
            "scope",
            getattr(self.instance, "scope", Offer.Scope.SERVICE_CITY),
        )
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        start_time = attrs.get("start_time") or getattr(
            self.instance,
            "start_time",
            None,
        )
        end_time = attrs.get("end_time") or getattr(
            self.instance,
            "end_time",
            None,
        )

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time."}
            )

        products_to_check = products
        if products_to_check is None and self.instance is not None and market:
            products_to_check = list(self.instance.products.all())

        if products_to_check is not None:
            if not products_to_check:
                raise serializers.ValidationError(
                    {"product_ids": "Choose at least one product for this offer."}
                )
            if market is None:
                market = products_to_check[0].market
                attrs["market"] = market

        if market is None:
            raise serializers.ValidationError(
                {"market_id": "Offer market is required."}
            )

        if scope == Offer.Scope.GENERAL:
            if service_city is not None:
                raise serializers.ValidationError(
                    {
                        "service_city_id": (
                            "Service city must be empty for general offers."
                        )
                    }
                )
            if market.scope != Market.Scope.GENERAL:
                raise serializers.ValidationError(
                    {"market_id": "Offer market must be a general market."}
                )
            if products_to_check is not None:
                invalid_product_ids = [
                    product.id
                    for product in products_to_check
                    if product.market.scope != Market.Scope.GENERAL
                ]
                if invalid_product_ids:
                    raise serializers.ValidationError(
                        {
                            "product_ids": (
                                "All selected products must belong to the "
                                "offer region."
                            )
                        }
                    )
            return attrs

        if service_city is None:
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "Service city is required for service-city offers."
                    )
                }
            )
        if not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        if not self._market_serves_service_city(market, service_city):
            raise serializers.ValidationError(
                {
                    "market_id": (
                        "Offer market must belong to the selected service "
                        "city region."
                    )
                }
            )
        if products_to_check is not None:
            invalid_product_ids = [
                product.id
                for product in products_to_check
                if not self._market_serves_service_city(
                    product.market,
                    service_city,
                )
            ]
            if invalid_product_ids:
                raise serializers.ValidationError(
                    {
                        "product_ids": (
                            "All selected products must belong to the offer "
                            "region."
                        )
                    }
                )

        return attrs

    @staticmethod
    def _market_serves_service_city(market, service_city):
        return (
            market.scope == Market.Scope.SERVICE_CITY
            and market.service_cities.filter(
                pk=service_city.pk,
                is_active=True,
            ).exists()
        )

    def create(self, validated_data):
        products = validated_data.pop("products")
        offer = Offer.objects.create(**validated_data)
        offer.products.set(products)
        return offer

    def update(self, instance, validated_data):
        products = validated_data.pop("products", None)
        instance = super().update(instance, validated_data)
        if products is not None:
            instance.products.set(products)
        return instance
