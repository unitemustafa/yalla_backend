from rest_framework import serializers

from catalog.models import Product
from markets.models import Market
from markets.serializers import AdminMarketSerializer

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
    )
    market = AdminMarketSerializer(read_only=True)
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
                return attrs
            invalid_product_ids = [
                product.id
                for product in products_to_check
                if product.market_id != market.id
            ]
            if invalid_product_ids:
                raise serializers.ValidationError(
                    {
                        "product_ids": (
                            "All selected products must belong to the offer market."
                        )
                    }
                )

        return attrs

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
