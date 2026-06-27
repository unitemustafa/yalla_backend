from rest_framework import serializers

from catalog.models import ProductVariant
from locations.models import Address
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


class OrderItemCreateSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__market"),
        source="variant",
    )
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    delivery_address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.select_related("user"),
        source="delivery_address",
    )
    items = OrderItemCreateSerializer(many=True)
    payment_method = serializers.CharField(max_length=50, default="cash_on_delivery")
    delivery_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        if user.role == user.Role.ADMIN:
            user_id = self.initial_data.get("user_id")
            if not user_id:
                raise serializers.ValidationError({"user_id": "User is required."})
            user_model = user.__class__
            try:
                user = user_model.objects.get(
                    pk=user_id,
                    role=user_model.Role.CLIENT,
                    is_active=True,
                    deleted_at__isnull=True,
                )
            except (user_model.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError(
                    {"user_id": "Active client user not found."}
                )

        address = attrs["delivery_address"]
        if address.user_id != user.id:
            raise serializers.ValidationError(
                {"delivery_address_id": "Address does not belong to this user."}
            )

        items = attrs.get("items") or []
        if not items:
            raise serializers.ValidationError(
                {"items": "At least one order item is required."}
            )

        market_ids = {item["variant"].product.market_id for item in items}
        if len(market_ids) != 1:
            raise serializers.ValidationError(
                {"items": "All order items must belong to the same market."}
            )

        attrs["user"] = user
        attrs["market_id"] = market_ids.pop()
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items")
        user = validated_data.pop("user")
        market_id = validated_data.pop("market_id")
        subtotal = sum(
            item["variant"].price * item["quantity"]
            for item in items
        )
        total = (
            subtotal
            + validated_data["delivery_price"]
            - validated_data["discount"]
        )
        if total < 0:
            total = 0

        order = Order.objects.create(
            user=user,
            market_id=market_id,
            subtotal_price=subtotal,
            total_price=total,
            **validated_data,
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                variant=item["variant"],
                quantity=item["quantity"],
                unit_price=item["variant"].price,
            )
            for item in items
        )
        return order


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            Order.Status.PENDING,
            Order.Status.CONFIRMED,
            Order.Status.UNDER_PREPARATION,
            Order.Status.READY,
            Order.Status.CANCELLED,
        )
    )


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
    order_number = serializers.SerializerMethodField()
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
    placed_at = serializers.DateTimeField(source="created_at", read_only=True)
    shipping_fee = serializers.DecimalField(
        source="delivery_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    subtotal = serializers.DecimalField(
        source="subtotal_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    discount_total = serializers.DecimalField(
        source="discount",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    total = serializers.DecimalField(
        source="total_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    def get_order_number(self, order):
        if not order.created_at:
            return f"YM-{order.id}"
        return f"YM-{order.created_at:%Y%m%d}-{order.id:06d}"

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
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
            "placed_at",
            "shipping_fee",
            "subtotal",
            "discount_total",
            "total",
            "items",
            "offers",
            "created_at",
            "updated_at",
        )
