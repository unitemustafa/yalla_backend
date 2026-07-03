from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from locations.models import ServiceCity


class MarketRegionUpdateSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(
        choices=User.MarketRegionMode.choices,
        allow_null=True,
    )
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.all(),
        source="service_city",
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        mode = attrs.get("mode")
        service_city = attrs.get("service_city")

        if mode is None:
            if service_city is not None:
                raise serializers.ValidationError(
                    {
                        "service_city_id": (
                            "Service city must be empty when clearing the "
                            "market region."
                        )
                    }
                )
            return attrs

        if mode == User.MarketRegionMode.GENERAL:
            if service_city is not None:
                raise serializers.ValidationError(
                    {
                        "service_city_id": (
                            "Service city must be empty for general market "
                            "browsing."
                        )
                    }
                )
            return attrs

        if service_city is None:
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "Service city is required for service-city market "
                        "browsing."
                    )
                }
            )
        if not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        mode = self.validated_data["mode"]
        service_city = self.validated_data.get("service_city")

        user.market_region_mode = mode
        user.market_region_service_city = service_city
        user.market_region_updated_at = timezone.now() if mode else None
        user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
                "updated_at",
            ]
        )
        return user


class MarketRegionDetectSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)

    def validate_latitude(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError(
                "Latitude must be between -90 and 90."
            )
        return value

    def validate_longitude(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180."
            )
        return value
