from rest_framework import serializers

from .models import ClientDevice, Notification


class ClientDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDevice
        fields = (
            "id",
            "token",
            "platform",
            "is_active",
            "last_seen_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "is_active",
            "last_seen_at",
            "created_at",
            "updated_at",
        )


class DeviceTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512, trim_whitespace=False)
    platform = serializers.ChoiceField(
        choices=ClientDevice.Platform.choices,
        required=False,
    )

    def validate_token(self, value):
        if not value.strip():
            raise serializers.ValidationError("FCM token is required.")
        return value.strip()


class NotificationSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(read_only=True)
    offer_id = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(read_only=True)
    offer = serializers.SerializerMethodField()

    def get_offer(self, instance):
        offer = instance.offer
        if offer is None:
            return None
        data = instance.data or {}
        image = None
        if offer.image:
            try:
                image = offer.image.url
            except ValueError:
                image = None
        if image:
            request = self.context.get("request")
            if request is not None:
                image = request.build_absolute_uri(image)
        return {
            "id": instance.offer_id,
            "title": offer.title,
            "image": image,
            "market_id": offer.market_id,
            "market_name": offer.market.name if offer.market is not None else "",
            "discount": f"{offer.discount:.2f}",
            "price": data.get("price"),
            "price_text": data.get("price_text"),
            "region_names": data.get("region_names", []),
        }

    class Meta:
        model = Notification
        fields = (
            "id",
            "audience",
            "type",
            "title",
            "message",
            "order_id",
            "offer_id",
            "product_id",
            "offer",
            "data",
            "is_read",
            "is_blocking",
            "is_resolved",
            "read_at",
            "resolved_at",
            "created_at",
        )
