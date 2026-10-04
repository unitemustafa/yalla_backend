import re
from pathlib import Path

from rest_framework import serializers
from django.db import transaction

from config.image_validation import validate_safe_image
from config.media_specs import validate_media_image, validate_focal_point
from .media_jobs import create_media_job, ready_job, apply_ready_job, job_data, validate_video_upload

from .models import AppLaunchMedia, DashboardSettings


DASHBOARD_LOGO_MAX_SIZE = 5 * 1024 * 1024
DASHBOARD_LOGO_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DASHBOARD_FONT_CHOICES = ("Cairo", "Tajawal", "Alexandria", "System")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class AppLaunchMediaSerializer(serializers.ModelSerializer):
    onboarding_one_url = serializers.SerializerMethodField()
    onboarding_two_url = serializers.SerializerMethodField()
    onboarding_three_url = serializers.SerializerMethodField()
    market_login_url = serializers.SerializerMethodField()
    delivery_login_url = serializers.SerializerMethodField()
    market_login_poster_url = serializers.SerializerMethodField()
    market_login_processing = serializers.SerializerMethodField()
    video_job_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = AppLaunchMedia
        fields = (
            "market_login", "market_login_video", "delivery_login", "onboarding_one_url",
            "onboarding_two_url", "onboarding_three_url", "market_login_url",
            "delivery_login_url", "updated_at",
            "market_login_poster", "market_login_poster_url", "market_login_focus", "delivery_login_focus", "market_login_processing", "video_job_id",
        )
        extra_kwargs = {
            key: {"write_only": True, "required": False}
            for key in ("market_login", "market_login_video", "delivery_login", "market_login_poster")
        }
        read_only_fields = ("updated_at",)

    def _url(self, obj, field):
        file = getattr(obj, field)
        if not file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(file.url) if request else file.url

    # Keep null URLs for older apps so they use their bundled artwork.
    def get_onboarding_one_url(self, obj):
        return None

    def get_onboarding_two_url(self, obj):
        return None

    def get_onboarding_three_url(self, obj):
        return None

    def get_market_login_url(self, obj):
        return self._url(obj, "market_login_video") or self._url(obj, "market_login")

    def get_delivery_login_url(self, obj):
        return self._url(obj, "delivery_login")

    def get_market_login_poster_url(self, obj):
        return self._url(obj, "market_login_poster")

    def get_market_login_processing(self, obj):
        request = self.context.get("request")
        if getattr(getattr(request, "user", None), "role", None) != "admin":
            return None
        return job_data(obj.market_login_pending_job, request) if obj.market_login_pending_job_id else None

    def validate_market_login_focus(self, value):
        return validate_focal_point(value)

    def validate_delivery_login_focus(self, value):
        return validate_focal_point(value)

    def validate(self, attrs):
        retired_fields = ("onboarding_one", "onboarding_two", "onboarding_three")
        errors = {
            field: "Onboarding images are bundled with the app and cannot be changed."
            for field in retired_fields if field in self.initial_data
        }
        if errors:
            raise serializers.ValidationError(errors)
        image_fields = {"market_login": "marketLogin", "delivery_login": "deliveryLogin", "market_login_poster": "marketLogin"}
        for field, spec in image_fields.items():
            file = attrs.get(field)
            if file is not None:
                try:
                    self._validate_image(file)
                    validate_media_image(file, spec)
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({field: exc.detail}) from exc
        file = attrs.get("market_login_video")
        if file is not None:
            try:
                validate_video_upload(file)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"market_login_video": exc.detail}) from exc
        if sum(bool(attrs.get(field)) for field in ("market_login", "market_login_video", "video_job_id")) > 1:
            raise serializers.ValidationError("Choose one login image or video.")
        if attrs.get("video_job_id"):
            ready_job(attrs["video_job_id"], "market_login")
        return attrs

    def update(self, instance, validated_data):
        job_id = validated_data.pop("video_job_id", None)
        has_video = "market_login_video" in validated_data
        upload = validated_data.pop("market_login_video", None)
        with transaction.atomic():
            job = ready_job(job_id, "market_login", lock=True) if job_id else None
            instance = AppLaunchMedia.objects.select_for_update().get(pk=instance.pk)
            if upload is not None:
                job = create_media_job(upload, self.context["request"].user, "market_login", validated=True, poster=validated_data.pop("market_login_poster", None))
                validated_data["market_login_pending_job"] = job
            elif job is not None:
                apply_ready_job(instance, job, poster=validated_data.pop("market_login_poster", None))
            elif "market_login" in validated_data or has_video:
                validated_data.update(market_login_video=None, market_login_poster=None, market_login_pending_job=None)
            return super().update(instance, validated_data)

    @staticmethod
    def _validate_image(file):
        extension = Path(file.name or "").suffix.lower().lstrip(".")
        if extension not in DASHBOARD_LOGO_ALLOWED_EXTENSIONS or file.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image must be JPG, PNG, or WEBP and 5 MB or smaller.")
        validate_safe_image(file)

class DashboardSettingsSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(write_only=True, required=False, allow_null=False)
    remove_logo = serializers.BooleanField(write_only=True, required=False)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = DashboardSettings
        fields = (
            "primary_color",
            "subtle_color",
            "accent_color",
            "font_family",
            "brand_name",
            "brand_tagline",
            "logo",
            "remove_logo",
            "logo_url",
            "updated_at",
        )
        read_only_fields = ("logo_url", "updated_at")

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        try:
            url = obj.logo.url
        except ValueError:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def validate_primary_color(self, value):
        return self._validate_color(value)

    def validate_subtle_color(self, value):
        return self._validate_color(value)

    def validate_accent_color(self, value):
        return self._validate_color(value)

    def _validate_color(self, value):
        if not HEX_COLOR_RE.fullmatch(value or ""):
            raise serializers.ValidationError(
                "Color must be a hex value in the form #RRGGBB."
            )
        return value

    def validate_font_family(self, value):
        if value not in DASHBOARD_FONT_CHOICES:
            raise serializers.ValidationError("Unsupported font family.")
        return value

    def validate_brand_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Brand name is required.")
        return value

    def validate_brand_tagline(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Brand tagline is required.")
        return value

    def validate_logo(self, value):
        extension = Path(value.name or "").suffix.lower().lstrip(".")
        if extension not in DASHBOARD_LOGO_ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Upload a valid dashboard logo: JPG, JPEG, PNG, or WEBP."
            )
        if value.size > DASHBOARD_LOGO_MAX_SIZE:
            raise serializers.ValidationError("Dashboard logo must be 5 MB or smaller.")
        return validate_media_image(value, "dashboardLogo")

    def update(self, instance, validated_data):
        logo = validated_data.pop("logo", None)
        remove_logo = validated_data.pop("remove_logo", False)
        old_logo = instance.logo if logo is not None or remove_logo else None
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if logo is not None:
            instance.logo = logo
        elif remove_logo:
            instance.logo = None
        instance.save()
        if old_logo and old_logo.name and old_logo.name != instance.logo.name:
            from config.media_cleanup import schedule_storage_cleanup
            schedule_storage_cleanup(old_logo.storage, old_logo.name)
        return instance


class DashboardRangeQuerySerializer(serializers.Serializer):
    from_date = serializers.DateField(source="from")
    to_date = serializers.DateField(source="to")

    def validate(self, attrs):
        if attrs["from"] > attrs["to"]:
            raise serializers.ValidationError(
                {"to": "The to date must be on or after the from date."}
            )
        return attrs


class DashboardRangeSerializer(serializers.Serializer):
    from_date = serializers.DateField(source="from")
    to_date = serializers.DateField(source="to")
    timezone = serializers.CharField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            "from": data["from_date"],
            "to": data["to_date"],
            "timezone": data["timezone"],
        }


class RevenueSerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=20, decimal_places=2)
    percentage = serializers.FloatField()


class OrderMetricsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    incomplete = serializers.IntegerField()
    completion_rate = serializers.FloatField()


class CustomerMetricsSerializer(serializers.Serializer):
    new = serializers.IntegerField()
    returning = serializers.IntegerField()
    return_rate = serializers.FloatField()


class TopProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    quantity_sold = serializers.IntegerField()
    orders_count = serializers.IntegerField()


class ActiveOrderCustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ActiveOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    customer = ActiveOrderCustomerSerializer()
    total = serializers.DecimalField(max_digits=20, decimal_places=2)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    market_count = serializers.IntegerField()
    market_names_summary = serializers.CharField()
    is_multi_market = serializers.BooleanField()


class TopShopSerializer(serializers.Serializer):
    market_id = serializers.IntegerField()
    name = serializers.CharField()
    zone = serializers.CharField()
    orders_count = serializers.IntegerField()
    average_items_per_order = serializers.FloatField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)


class DashboardOverviewSerializer(serializers.Serializer):
    range = DashboardRangeSerializer()
    currency = serializers.CharField()
    revenue = RevenueSerializer()
    orders = OrderMetricsSerializer()
    customers = CustomerMetricsSerializer()
    top_products = TopProductSerializer(many=True)
    active_orders = ActiveOrderSerializer(many=True)
    top_shops = TopShopSerializer(many=True)
