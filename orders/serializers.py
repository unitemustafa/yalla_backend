from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from catalog.models import ProductVariant
from locations.models import Address
from markets.models import Market
from offers.models import Offer

from .models import Order, OrderItem, OrderOffer

User = get_user_model()


class OrderItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product"),
        source="variant",
    )

    class Meta:
        model = OrderItem
        fields = ("id", "variant_id", "quantity", "unit_price")
        read_only_fields = ("id",)


class OrderOfferSerializer(serializers.ModelSerializer):
    offer_id = serializers.PrimaryKeyRelatedField(
        queryset=Offer.objects.all(),
        source="offer",
    )

    class Meta:
        model = OrderOffer
        fields = ("id", "offer_id", "discount_amount", "created_at")
        read_only_fields = ("id", "created_at")


class OrderSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.CLIENT),
        source="user",
    )
    delivery_address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
        source="delivery_address",
        required=False,
        allow_null=True,
    )
    assigned_representative_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            role=User.Role.REPRESENTATIVE,
            is_active=True,
            deleted_at__isnull=True,
        ),
        source="assigned_representative",
        required=False,
        allow_null=True,
    )
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.all(),
        source="market",
    )
    items = OrderItemSerializer(many=True, required=False)
    offers = OrderOfferSerializer(
        source="order_offers",
        many=True,
        required=False,
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "user_id",
            "delivery_address_id",
            "assigned_representative_id",
            "market_id",
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
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        address = attrs.get(
            "delivery_address",
            getattr(self.instance, "delivery_address", None),
        )
        market = attrs.get("market", getattr(self.instance, "market", None))
        representative = attrs.get(
            "assigned_representative",
            getattr(self.instance, "assigned_representative", None),
        )
        items = attrs.get("items")
        offers = attrs.get("order_offers")

        if address and user and address.user_id != user.id:
            raise serializers.ValidationError(
                {"delivery_address_id": "Address does not belong to the order user."}
            )
        if items is not None and market:
            if any(item["variant"].product.market_id != market.id for item in items):
                raise serializers.ValidationError(
                    {"items": "All item variants must belong to the order market."}
                )
        if offers is not None and market:
            if any(item["offer"].market_id != market.id for item in offers):
                raise serializers.ValidationError(
                    {"offers": "All offers must belong to the order market."}
                )
        if "assigned_representative" in attrs:
            if representative:
                attrs["status"] = Order.Status.READY
                if not attrs.get("assigned_at"):
                    attrs["assigned_at"] = timezone.now()
            else:
                attrs["assigned_at"] = None
                if self.instance and self.instance.assigned_representative_id:
                    attrs["status"] = Order.Status.PENDING
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        offers = validated_data.pop("order_offers", [])
        order = Order.objects.create(**validated_data)
        self._replace_items(order, items)
        self._replace_offers(order, offers)
        return order

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        offers = validated_data.pop("order_offers", None)
        instance = super().update(instance, validated_data)
        if items is not None:
            instance.items.all().delete()
            self._replace_items(instance, items)
        if offers is not None:
            instance.order_offers.all().delete()
            self._replace_offers(instance, offers)
        return instance

    @staticmethod
    def _replace_items(order, items):
        OrderItem.objects.bulk_create(
            OrderItem(order=order, **item) for item in items
        )

    @staticmethod
    def _replace_offers(order, offers):
        OrderOffer.objects.bulk_create(
            OrderOffer(order=order, **item) for item in offers
        )


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class OrderAssignmentSerializer(serializers.Serializer):
    representative_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            role=User.Role.REPRESENTATIVE,
            is_active=True,
            deleted_at__isnull=True,
        ),
        source="representative",
        allow_null=True,
    )
