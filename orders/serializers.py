from rest_framework import serializers

from catalog.models import ProductVariant
from markets.serializers import HomeMarketSerializer, MarketClassificationProductSerializer

from .models import Order, OrderItem, OrderOffer


class OrderVariantSerializer(serializers.ModelSerializer):
    product = MarketClassificationProductSerializer(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ("id", "price", "sku", "product")


class OrderItemSerializer(serializers.ModelSerializer):
    variant = OrderVariantSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "variant", "quantity", "unit_price")


class OrderOfferDetailSerializer(serializers.ModelSerializer):
    offer_id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(source="offer.title", read_only=True)
    description = serializers.CharField(source="offer.description", read_only=True)
    image = serializers.ImageField(source="offer.image", read_only=True)
    type = serializers.CharField(source="offer.type", read_only=True)
    discount = serializers.DecimalField(
        source="offer.discount",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = OrderOffer
        fields = (
            "id",
            "offer_id",
            "title",
            "description",
            "image",
            "type",
            "discount",
            "discount_amount",
            "created_at",
        )


class OrderSerializer(serializers.ModelSerializer):
    market = HomeMarketSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    offers = OrderOfferDetailSerializer(
        source="order_offers",
        many=True,
        read_only=True,
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "market",
            "payment_method",
            "discount",
            "description",
            "status",
            "delivery_price",
            "subtotal_price",
            "total_price",
            "image",
            "items",
            "offers",
            "created_at",
            "updated_at",
        )
