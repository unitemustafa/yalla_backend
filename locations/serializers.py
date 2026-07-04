from decimal import Decimal

from rest_framework import serializers

from accounts.models import User

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
    center_latitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
        allow_null=True,
    )
    center_longitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
        allow_null=True,
    )
    radius_km = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        allow_null=True,
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

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_delivery_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Delivery price cannot be negative.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        if service_city is None:
            raise serializers.ValidationError(
                {"service_city_id": "Service city is required."}
            )
        if not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )

        name = attrs.get("name", getattr(self.instance, "name", "")).strip()
        is_active = attrs.get(
            "is_active",
            getattr(self.instance, "is_active", True),
        )
        if is_active:
            duplicate = DeliveryArea.objects.filter(
                service_city=service_city,
                name__iexact=name,
                is_active=True,
            )
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError(
                    {
                        "name": (
                            "An active delivery area with this name already "
                            "exists in this service city."
                        )
                    }
                )
        return attrs


class DeliveryAreaSummarySerializer(serializers.ModelSerializer):
    service_city_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = DeliveryArea
        fields = (
            "id",
            "service_city_id",
            "name",
            "delivery_price",
            "is_active",
        )


class AddressSerializer(serializers.ModelSerializer):
    fullName = serializers.CharField(source="name", read_only=True)
    line1 = serializers.SerializerMethodField()
    street = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    phoneNumber = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    postalCode = serializers.SerializerMethodField()
    isDefault = serializers.BooleanField(source="is_default", read_only=True)
    service_city = ServiceCitySerializer(read_only=True)
    service_city_id = serializers.IntegerField(read_only=True)
    delivery_area = DeliveryAreaSummarySerializer(read_only=True)
    delivery_area_id = serializers.IntegerField(read_only=True)
    service_city_name = serializers.SerializerMethodField()
    delivery_area_name = serializers.SerializerMethodField()
    delivery_area_price = serializers.SerializerMethodField()
    delivery_price_preview = serializers.SerializerMethodField()

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
            "details",
            "manual_city",
            "manual_area",
            "service_city",
            "service_city_id",
            "service_city_name",
            "delivery_area",
            "delivery_area_id",
            "delivery_area_name",
            "delivery_area_price",
            "delivery_type",
            "delivery_price_preview",
            "is_default",
            "isDefault",
            "created_at",
        )

    def get_phone(self, instance):
        return getattr(instance.user, "phone", "") or ""

    def get_phoneNumber(self, instance):
        return self.get_phone(instance)

    def get_line1(self, instance):
        return instance.details.strip() or instance.name

    def get_street(self, instance):
        return self.get_line1(instance)

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

    def get_delivery_price_preview(self, instance):
        if (
            instance.delivery_type == Address.DeliveryType.FIXED_AREA
            and instance.delivery_area_id
        ):
            return f"{instance.delivery_area.delivery_price:.2f}"
        return None

    def get_service_city_name(self, instance):
        if instance.service_city_id:
            return instance.service_city.name
        return None

    def get_delivery_area_name(self, instance):
        if instance.delivery_area_id:
            return instance.delivery_area.name
        return None

    def get_delivery_area_price(self, instance):
        if instance.delivery_area_id:
            return f"{instance.delivery_area.delivery_price:.2f}"
        return None


class AddressWriteSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        source="service_city",
        required=False,
        allow_null=True,
    )
    delivery_area_id = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryArea.objects.select_related("service_city").all(),
        source="delivery_area",
        required=False,
        allow_null=True,
    )
    delivery_type = serializers.ChoiceField(
        choices=Address.DeliveryType.choices,
        required=False,
    )
    name = serializers.CharField(required=False, allow_blank=True)
    details = serializers.CharField(required=False, allow_blank=True)
    manual_city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    manual_area = serializers.CharField(required=False, allow_blank=True, allow_null=True)
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

        name = self._normalized_name(attrs)
        details = self._normalized_details(attrs)
        if not name:
            raise serializers.ValidationError(
                {"name": "Address name is required."}
            )
        if not details and self.instance is None:
            raise serializers.ValidationError(
                {"line1": "Address details are required."}
            )

        latitude = attrs.get(
            "latitude",
            getattr(self.instance, "latitude", None),
        )
        longitude = attrs.get(
            "longitude",
            getattr(self.instance, "longitude", None),
        )
        manual_city = self._clean_optional(
            attrs["manual_city"]
            if "manual_city" in attrs
            else getattr(self.instance, "manual_city", None)
        )
        manual_area = self._clean_optional(
            attrs["manual_area"]
            if "manual_area" in attrs
            else getattr(self.instance, "manual_area", None)
        )
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        delivery_area = (
            attrs["delivery_area"]
            if "delivery_area" in attrs
            else getattr(self.instance, "delivery_area", None)
        )
        region_mode = getattr(user, "market_region_mode", None)
        region_service_city = getattr(user, "market_region_service_city", None)
        is_general_region = region_mode == User.MarketRegionMode.GENERAL
        is_service_city_region = region_mode == User.MarketRegionMode.SERVICE_CITY

        if service_city is None and not is_general_region:
            service_city = self._matching_service_city(attrs, name)

        if is_general_region:
            if service_city is not None:
                raise serializers.ValidationError(
                    {"service_city_id": "Service city must be empty for General addresses."}
                )
            if delivery_area is not None:
                raise serializers.ValidationError(
                    {"delivery_area_id": "Delivery area must be empty for General addresses."}
                )
            if not manual_city:
                raise serializers.ValidationError(
                    {"manual_city": "Manual city is required for General addresses."}
                )
            if not manual_area:
                raise serializers.ValidationError(
                    {"manual_area": "Manual area is required for General addresses."}
                )
            delivery_type = Address.DeliveryType.DELIVERY
        else:
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
            if service_city is None:
                raise serializers.ValidationError(
                    {"service_city_id": "Service city is required."}
                )
            if not service_city.is_active:
                raise serializers.ValidationError(
                    {"service_city_id": "Service city must be active."}
                )
            if (
                is_service_city_region
                and region_service_city is not None
                and service_city.id != region_service_city.id
            ):
                raise serializers.ValidationError(
                    {"service_city_id": "Service city must match the selected market region."}
                )
            if manual_city:
                raise serializers.ValidationError(
                    {"manual_city": "Manual city must be empty for ServiceCity addresses."}
                )

            if delivery_area is not None:
                if manual_area:
                    raise serializers.ValidationError(
                        {"manual_area": "Manual area must be empty for fixed delivery areas."}
                    )
                if not delivery_area.is_active:
                    raise serializers.ValidationError(
                        {"delivery_area_id": "Delivery area must be active."}
                    )
                if delivery_area.service_city_id != service_city.id:
                    raise serializers.ValidationError(
                        {
                            "delivery_area_id": (
                                "Delivery area must belong to the selected service city."
                            )
                        }
                    )
                delivery_type = Address.DeliveryType.FIXED_AREA
            else:
                if latitude is None and longitude is None and not manual_area:
                    raise serializers.ValidationError(
                        {"manual_area": "Manual area is required when delivery area is not selected."}
                    )
                delivery_type = Address.DeliveryType.DELIVERY

        attrs["user"] = user
        attrs["normalized_name"] = name
        attrs["normalized_details"] = details
        attrs["normalized_manual_city"] = manual_city
        attrs["normalized_manual_area"] = manual_area
        attrs["normalized_latitude"] = Decimal(latitude) if latitude is not None else None
        attrs["normalized_longitude"] = Decimal(longitude) if longitude is not None else None
        attrs["normalized_service_city"] = service_city
        attrs["normalized_delivery_area"] = delivery_area
        attrs["normalized_delivery_type"] = delivery_type
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
            details=validated_data["normalized_details"],
            manual_city=validated_data["normalized_manual_city"],
            manual_area=validated_data["normalized_manual_area"],
            latitude=validated_data["normalized_latitude"],
            longitude=validated_data["normalized_longitude"],
            service_city=validated_data["normalized_service_city"],
            delivery_area=validated_data["normalized_delivery_area"],
            delivery_type=validated_data["normalized_delivery_type"],
            is_default=validated_data["normalized_default"],
        )

    def update(self, instance, validated_data):
        instance.name = validated_data["normalized_name"]
        instance.details = validated_data["normalized_details"]
        instance.manual_city = validated_data["normalized_manual_city"]
        instance.manual_area = validated_data["normalized_manual_area"]
        instance.latitude = validated_data["normalized_latitude"]
        instance.longitude = validated_data["normalized_longitude"]
        instance.service_city = validated_data["normalized_service_city"]
        instance.delivery_area = validated_data["normalized_delivery_area"]
        instance.delivery_type = validated_data["normalized_delivery_type"]
        instance.is_default = validated_data["normalized_default"]
        instance.save(
            update_fields=[
                "name",
                "details",
                "manual_city",
                "manual_area",
                "latitude",
                "longitude",
                "service_city",
                "delivery_area",
                "delivery_type",
                "is_default",
            ]
        )
        return instance

    @staticmethod
    def _clean_optional(value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _normalized_name(self, attrs):
        explicit_name = (
            attrs.get("name")
            or attrs.get("fullName")
            or attrs.get("full_name")
        )
        if explicit_name is not None and str(explicit_name).strip():
            return str(explicit_name).strip()
        if self.instance is not None and self.instance.name:
            return self.instance.name.strip()
        return self._address_detail_text(attrs)

    def _normalized_details(self, attrs):
        for key in ("details", "line1", "street", "address"):
            if key in attrs:
                value = str(attrs.get(key) or "").strip()
                if value:
                    return value
        if self.instance is not None:
            return self.instance.details.strip()
        return ""

    def _address_detail_text(self, attrs):
        line1 = str(
            attrs.get("line1")
            or attrs.get("street")
            or attrs.get("address")
            or ""
        ).strip()
        city = (attrs.get("city") or "").strip()
        state = (attrs.get("state") or "").strip()
        country = (attrs.get("country") or "").strip()
        return ", ".join(
            part for part in (line1, city, state, country) if part
        )

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
