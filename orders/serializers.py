from rest_framework import serializers

from catalog.models import ProductVariant
from markets.serializers import HomeMarketSerializer, MarketClassificationProductSerializer

from .models import Order, OrderItem, OrderOffer


class OrderAddressSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, read_only=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, read_only=True)


class OrderCustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    avatar_url = serializers.URLField(read_only=True, allow_null=True)


class AssignedRepresentativeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    avatar_url = serializers.URLField(read_only=True, allow_null=True)


class DeliverOrderSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    proof = serializers.ImageField(required=False)

    def validate_proof(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Proof image must not exceed 10 MB.")
        return value

    def validate(self, attrs):
        if not attrs.get("note") and attrs.get("proof") is None:
            raise serializers.ValidationError(
                "A delivery proof image or note is required."
            )
        return attrs


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
    customer = OrderCustomerSerializer(source="user", read_only=True)
    delivery_address = OrderAddressSerializer(read_only=True)
    assigned_representative = AssignedRepresentativeSerializer(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "market",
            "customer",
            "delivery_address",
            "assigned_representative",
            "payment_method",
            "discount",
            "description",
            "status",
            "delivery_price",
            "subtotal_price",
            "total_price",
            "image",
            "assigned_at",
            "delivered_at",
            "delivery_note",
            "delivery_proof",
            "items",
            "offers",
            "created_at",
            "updated_at",
        )
