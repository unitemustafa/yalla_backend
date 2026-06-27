from decimal import Decimal

from rest_framework import serializers

from .models import Address, DeliveryArea


class AddressSerializer(serializers.ModelSerializer):
    fullName = serializers.CharField(source="name", read_only=True)
    line1 = serializers.CharField(source="name", read_only=True)
    street = serializers.CharField(source="name", read_only=True)
    phone = serializers.SerializerMethodField()
    phoneNumber = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    postalCode = serializers.SerializerMethodField()
    isDefault = serializers.BooleanField(source="is_default", read_only=True)

    class Meta:
        model = Address
        fields = (
            "id",
            "name",
            "fullName",
            "phone",
            "phoneNumber",
            "line1",
            "street",
            "city",
            "state",
            "country",
            "postalCode",
            "latitude",
            "longitude",
            "is_default",
            "isDefault",
            "created_at",
        )

    def get_phone(self, instance):
        return getattr(instance.user, "phone", "") or ""

    def get_phoneNumber(self, instance):
        return self.get_phone(instance)

    def get_city(self, instance):
        return ""

    def get_state(self, instance):
        return ""

    def get_country(self, instance):
        return "Egypt"

    def get_postalCode(self, instance):
        return ""


class AddressWriteSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, allow_blank=True)
    fullName = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True)
    line1 = serializers.CharField(required=False, allow_blank=True)
    street = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    postalCode = serializers.CharField(required=False, allow_blank=True)
    postal_code = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
    )
    longitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
    )
    isDefault = serializers.BooleanField(required=False)
    is_default = serializers.BooleanField(required=False)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        if user.role == user.Role.ADMIN:
            user_id = attrs.get("user_id") or self.context.get("user_id")
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

        name = self._address_name(attrs)
        if not name:
            raise serializers.ValidationError(
                {"line1": "Address details are required."}
            )

        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")
        if latitude is None or longitude is None:
            area = self._matching_area(attrs, name)
            if area is None:
                raise serializers.ValidationError(
                    {
                        "city": (
                            "Latitude and longitude are required unless the "
                            "address matches an active delivery area."
                        )
                    }
                )
            latitude = area.center_latitude
            longitude = area.center_longitude

        attrs["user"] = user
        attrs["normalized_name"] = name
        attrs["normalized_latitude"] = Decimal(latitude)
        attrs["normalized_longitude"] = Decimal(longitude)
        attrs["normalized_default"] = attrs.get(
            "is_default",
            attrs.get(
                "isDefault",
                getattr(self.instance, "is_default", False),
            ),
        )
        return attrs

    def create(self, validated_data):
        return Address.objects.create(
            user=validated_data["user"],
            name=validated_data["normalized_name"],
            latitude=validated_data["normalized_latitude"],
            longitude=validated_data["normalized_longitude"],
            is_default=validated_data["normalized_default"],
        )

    def update(self, instance, validated_data):
        instance.name = validated_data["normalized_name"]
        instance.latitude = validated_data["normalized_latitude"]
        instance.longitude = validated_data["normalized_longitude"]
        instance.is_default = validated_data["normalized_default"]
        instance.save(update_fields=["name", "latitude", "longitude", "is_default"])
        return instance

    def _address_name(self, attrs):
        line1 = (
            attrs.get("line1")
            or attrs.get("street")
            or attrs.get("address")
            or ""
        ).strip()
        city = (attrs.get("city") or "").strip()
        state = (attrs.get("state") or "").strip()
        country = (attrs.get("country") or "").strip()
        text = ", ".join(
            part for part in (line1, city, state, country) if part
        )
        return text or (
            attrs.get("name")
            or attrs.get("fullName")
            or attrs.get("full_name")
            or ""
        ).strip()

    def _matching_area(self, attrs, name):
        candidates = [
            attrs.get("city"),
            attrs.get("state"),
            attrs.get("line1"),
            attrs.get("street"),
            attrs.get("address"),
            name,
        ]
        for candidate in candidates:
            text = (candidate or "").strip()
            if not text:
                continue
            area = DeliveryArea.objects.filter(
                is_active=True,
                name__iexact=text,
            ).first()
            if area is not None:
                return area
            area = DeliveryArea.objects.filter(
                is_active=True,
                name__icontains=text,
            ).first()
            if area is not None:
                return area
        return None
