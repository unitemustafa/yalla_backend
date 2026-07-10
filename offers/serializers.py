import json

from rest_framework import serializers

from catalog.models import Product
from catalog.serializers import ProductImageSerializer
from locations.models import ServiceCity
from markets.models import Market
from markets.serializers import AdminMarketSerializer, ServiceCitySummarySerializer

from .models import Offer


class PrimaryKeyListField(serializers.Field):
    def __init__(self, *, queryset, **kwargs):
        self.queryset = queryset
        super().__init__(**kwargs)

    def get_value(self, dictionary):
        if hasattr(dictionary, "getlist"):
            values = dictionary.getlist(self.field_name)
            if len(values) > 1:
                return values
        return super().get_value(dictionary)

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError("Expected a list of ids.") from exc

        if isinstance(data, tuple):
            data = list(data)

        if not isinstance(data, list):
            raise serializers.ValidationError("Expected a list of ids.")

        ids = []
        for item in data:
            try:
                ids.append(int(item))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("Expected a list of ids.") from exc

        objects_by_id = self.queryset.in_bulk(ids)
        missing_ids = [item_id for item_id in ids if item_id not in objects_by_id]
        if missing_ids:
            raise serializers.ValidationError(
                f"Invalid pk \"{missing_ids[0]}\" - object does not exist."
            )
        return [objects_by_id[item_id] for item_id in ids]

    def to_representation(self, value):
        if hasattr(value, "all"):
            value = value.all()
        return [item.pk for item in value]


class OfferProductSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(read_only=True)
    market_id = serializers.IntegerField(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

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
            "images",
            "discount",
            "created_at",
            "updated_at",
        )


class AdminOfferSerializer(serializers.ModelSerializer):
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.all(),
        source="market",
        required=False,
    )
    market = AdminMarketSerializer(read_only=True)
    service_city_ids = PrimaryKeyListField(
        queryset=ServiceCity.objects.all(),
        source="service_cities",
        required=False,
    )
    service_cities = ServiceCitySummarySerializer(many=True, read_only=True)
    product_ids = PrimaryKeyListField(
        queryset=Product.objects.all(),
        source="products",
    )
    products = OfferProductSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = (
            "id",
            "market",
            "market_id",
            "show_in_general",
            "service_cities",
            "service_city_ids",
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
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError(
                    "Active days must be a list."
                ) from exc
        if not isinstance(value, list):
            raise serializers.ValidationError("Active days must be a list.")
        return value

    def validate(self, attrs):
        market = attrs.get("market") or getattr(self.instance, "market", None)
        products = attrs.get("products")
        show_in_general = attrs.get(
            "show_in_general",
            getattr(self.instance, "show_in_general", False),
        )
        service_cities = attrs.get("service_cities")
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

        if service_cities is None:
            service_cities_to_check = (
                list(self.instance.service_cities.all())
                if self.instance is not None
                else []
            )
        else:
            service_cities_to_check = list(service_cities)

        if not show_in_general and not service_cities_to_check:
            message = (
                "اختر الظهور في العام أو مدينة خدمة واحدة على الأقل."
            )
            raise serializers.ValidationError(
                {
                    "show_in_general": message,
                    "service_city_ids": message,
                }
            )

        if show_in_general:
            if market.scope != Market.Scope.GENERAL:
                raise serializers.ValidationError(
                    {
                        "market_id": (
                            "Offer market must support general visibility."
                        )
                    }
                )

        existing_city_ids = set()
        if self.instance is not None:
            existing_city_ids = set(
                self.instance.service_cities.values_list("id", flat=True)
            )

        inactive_new_city_ids = [
            service_city.id
            for service_city in service_cities_to_check
            if not service_city.is_active and service_city.id not in existing_city_ids
        ]
        if inactive_new_city_ids:
            raise serializers.ValidationError(
                {"service_city_ids": "Only active service cities may be selected."}
            )

        unserved_city_ids = [
            service_city.id
            for service_city in service_cities_to_check
            if not self._market_serves_service_city(market, service_city)
        ]
        if unserved_city_ids:
            raise serializers.ValidationError(
                {"service_city_ids": "Offer market does not serve every selected city."}
            )

        if products_to_check is not None:
            invalid_product_ids = [
                product.id
                for product in products_to_check
                if product.market_id != market.id
            ]
            if invalid_product_ids:
                raise serializers.ValidationError(
                    {
                        "product_ids": (
                            "All selected products must belong to the selected "
                            "market."
                        )
                    }
                )

        return attrs

    @staticmethod
    def _market_serves_service_city(market, service_city):
        return (
            market.service_cities.filter(
                pk=service_city.pk,
                is_active=True,
            ).exists()
        )

    def create(self, validated_data):
        products = validated_data.pop("products")
        service_cities = validated_data.pop("service_cities", [])
        offer = Offer.objects.create(**validated_data)
        offer.products.set(products)
        offer.service_cities.set(service_cities)
        return offer

    def update(self, instance, validated_data):
        products = validated_data.pop("products", None)
        service_cities = validated_data.pop("service_cities", None)
        instance = super().update(instance, validated_data)
        if products is not None:
            instance.products.set(products)
        if service_cities is not None:
            instance.service_cities.set(service_cities)
        return instance
