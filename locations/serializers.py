from decimal import Decimal

from rest_framework import serializers

from .models import Address, DeliveryArea, ServiceCity


class ServiceCitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCity
        fields = (
            "id",
            "name",
            "center_latitude",
            "center_longitude",
            "radius_km",
            "delivery_price",
            "is_active",
        )
        read_only_fields = ("id",)

    def validate_name(self, value):
        return value.strip()

    def validate_center_latitude(self, value):
        if value is None:
            return value
        if not Decimal("-90") <= value <= Decimal("90"):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_center_longitude(self, value):
        if value is None:
            return value
        if not Decimal("-180") <= value <= Decimal("180"):
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180."
            )
        return value

    def validate_radius_km(self, value):
        if value is None:
            return value
        if value <= 0:
            raise serializers.ValidationError("Radius must be greater than zero.")
        return value

    def validate_delivery_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Delivery price cannot be negative.")
        return value


class DeliveryAreaSerializer(ServiceCitySerializer):
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.all(),
        source="service_city",
    )

    class Meta:
        model = DeliveryArea
        fields = (
            "id",
            "service_city_id",
            "name",
            "center_latitude",
            "center_longitude",
            "radius_km",
            "delivery_price",
            "is_active",
        )
        read_only_fields = ("id",)

    def validate_delivery_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Delivery price cannot be negative.")
        return value


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
    service_city = ServiceCitySerializer(read_only=True)
    service_city_id = serializers.IntegerField(read_only=True)

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
            "service_city",
            "service_city_id",
            "is_default",
            "isDefault",
            "created_at",
        )

    def get_phone(self, instance):
        return getattr(instance.user, "phone", "") or ""

    def get_phoneNumber(self, instance):
        return self.get_phone(instance)

    def get_city(self, instance):
        if instance.service_city_id:
            return instance.service_city.name
        return ""

    def get_state(self, instance):
        return ""

    def get_country(self, instance):
        return "Egypt"

    def get_postalCode(self, instance):
        return ""


class AddressWriteSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        source="service_city",
        required=False,
        allow_null=True,
    )
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
        allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
        allow_null=True,
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
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        if service_city is None:
            service_city = self._matching_service_city(attrs, name)

        if latitude is None and longitude is None:
            if service_city is None:
                raise serializers.ValidationError(
                    {
                        "service_city_id": "Service city is required when coordinates are not provided."
                    }
                )
        elif latitude is None or longitude is None:
            raise serializers.ValidationError(
                {"latitude": "Latitude and longitude must be provided together."}
            )

        attrs["user"] = user
        attrs["normalized_name"] = name
        attrs["normalized_latitude"] = Decimal(latitude) if latitude is not None else None
        attrs["normalized_longitude"] = Decimal(longitude) if longitude is not None else None
        attrs["normalized_service_city"] = service_city
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
            service_city=validated_data["normalized_service_city"],
            is_default=validated_data["normalized_default"],
        )

    def update(self, instance, validated_data):
        instance.name = validated_data["normalized_name"]
        instance.latitude = validated_data["normalized_latitude"]
        instance.longitude = validated_data["normalized_longitude"]
        instance.service_city = validated_data["normalized_service_city"]
        instance.is_default = validated_data["normalized_default"]
        instance.save(
            update_fields=[
                "name",
                "latitude",
                "longitude",
                "service_city",
                "is_default",
            ]
        )
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

    def _matching_service_city(self, attrs, name):
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
            city = ServiceCity.objects.filter(
                is_active=True,
                name__iexact=text,
            ).first()
            if city is not None:
                return city
            city = ServiceCity.objects.filter(
                is_active=True,
                name__icontains=text,
            ).first()
            if city is not None:
                return city
        return None
