import re
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

from catalog.models import Product, ProductCategory
from locations.models import ServiceCity
from markets.models import Market

from .campaign_media import validate_campaign_image, validate_campaign_video
from .models import HomeCampaign, Offer


HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TARGET_FIELDS = {
    HomeCampaign.ActionType.OFFER: "target_offer",
    HomeCampaign.ActionType.PRODUCT: "target_product",
    HomeCampaign.ActionType.MARKET: "target_market",
    HomeCampaign.ActionType.PRODUCT_CATEGORY: "target_product_category",
}
class AdminHomeCampaignSerializer(serializers.ModelSerializer):
    effective_status = serializers.SerializerMethodField()
    service_city_id = serializers.PrimaryKeyRelatedField(
        source="service_city",
        queryset=ServiceCity.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    target_offer_id = serializers.PrimaryKeyRelatedField(
        source="target_offer",
        queryset=Offer.objects.filter(archived_at__isnull=True),
        required=False,
        allow_null=True,
    )
    target_product_id = serializers.PrimaryKeyRelatedField(
        source="target_product",
        queryset=Product.objects.filter(archived_at__isnull=True),
        required=False,
        allow_null=True,
    )
    target_market_id = serializers.PrimaryKeyRelatedField(
        source="target_market",
        queryset=Market.objects.filter(archived_at__isnull=True),
        required=False,
        allow_null=True,
    )
    target_product_category_id = serializers.PrimaryKeyRelatedField(
        source="target_product_category",
        queryset=ProductCategory.objects.all(),
        required=False,
        allow_null=True,
    )
    service_city = serializers.SerializerMethodField()
    target_summary = serializers.SerializerMethodField()

    class Meta:
        model = HomeCampaign
        fields = (
            "id",
            "internal_name",
            "is_active",
            "effective_status",
            "start_time",
            "end_time",
            "show_in_general",
            "service_city_id",
            "service_city",
            "teaser_text",
            "title",
            "description",
            "template",
            "sheet_size",
            "content_alignment",
            "use_theme_colors",
            "teaser_background_color",
            "teaser_text_color",
            "sheet_background_color",
            "sheet_text_color",
            "button_background_color",
            "button_text_color",
            "media_type",
            "teaser_image",
            "sheet_image",
            "video",
            "video_poster",
            "open_mode",
            "dismiss_behavior",
            "action_type",
            "cta_label",
            "target_offer_id",
            "target_product_id",
            "target_market_id",
            "target_product_category_id",
            "external_url",
            "copy_text",
            "target_summary",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "effective_status",
            "teaser_image",
            "sheet_image",
            "video",
            "video_poster",
            "target_summary",
            "created_at",
            "updated_at",
        )

    def get_effective_status(self, instance):
        return instance.get_effective_status()

    def get_service_city(self, instance):
        city = instance.service_city
        return None if city is None else {"id": city.id, "name": city.name}

    def get_target_summary(self, instance):
        target = {
            HomeCampaign.ActionType.OFFER: instance.target_offer,
            HomeCampaign.ActionType.PRODUCT: instance.target_product,
            HomeCampaign.ActionType.MARKET: instance.target_market,
            HomeCampaign.ActionType.PRODUCT_CATEGORY: instance.target_product_category,
        }.get(instance.action_type)
        if target is None:
            return None
        name = getattr(target, "title", None) or getattr(target, "name", "")
        return {"id": target.id, "name": name}

    def validate(self, attrs):
        instance = self.instance
        value = lambda name, default=None: attrs.get(
            name, getattr(instance, name, default) if instance is not None else default
        )
        start_time = value("start_time")
        end_time = value("end_time")
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time."}
            )

        show_in_general = value("show_in_general", True)
        service_city = value("service_city")
        if show_in_general and service_city is not None:
            raise serializers.ValidationError(
                {"service_city_id": "General campaigns cannot select a service city."}
            )
        if not show_in_general and service_city is None:
            raise serializers.ValidationError(
                {"service_city_id": "Select one service city for a local campaign."}
            )

        color_defaults = {
            "teaser_background_color": "#FF5A00",
            "teaser_text_color": "#FFFFFF",
            "sheet_background_color": "#FFFFFF",
            "sheet_text_color": "#202124",
            "button_background_color": "#FF5A00",
            "button_text_color": "#FFFFFF",
        }
        for field, default_color in color_defaults.items():
            color = value(field, default_color)
            if not HEX_COLOR_RE.fullmatch(color or ""):
                raise serializers.ValidationError({field: "Use a #RRGGBB color."})

        action_type = value("action_type", HomeCampaign.ActionType.NONE)
        cta_label = (value("cta_label", "") or "").strip()
        if action_type != HomeCampaign.ActionType.NONE and not cta_label:
            raise serializers.ValidationError(
                {"cta_label": "Button label is required for this action."}
            )
        attrs["cta_label"] = cta_label

        required_target = TARGET_FIELDS.get(action_type)
        for field in TARGET_FIELDS.values():
            target = value(field)
            if field == required_target and target is None:
                raise serializers.ValidationError(
                    {f"{field}_id": "Select a target for this action."}
                )
            if field != required_target:
                attrs[field] = None

        external_url = (value("external_url", "") or "").strip()
        copy_text = (value("copy_text", "") or "").strip()
        if action_type == HomeCampaign.ActionType.EXTERNAL_URL:
            parsed = urlparse(external_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise serializers.ValidationError(
                    {"external_url": "A valid HTTPS URL is required."}
                )
        else:
            attrs["external_url"] = ""
        if action_type == HomeCampaign.ActionType.COPY_TEXT:
            if not copy_text:
                raise serializers.ValidationError(
                    {"copy_text": "Enter the text or code to copy."}
                )
        else:
            attrs["copy_text"] = ""

        media_type = value("media_type", HomeCampaign.MediaType.NONE)
        if media_type == HomeCampaign.MediaType.NONE:
            attrs.update(sheet_image=None, video=None, video_poster=None)
        elif media_type == HomeCampaign.MediaType.IMAGE:
            attrs.update(video=None, video_poster=None)
        elif media_type == HomeCampaign.MediaType.VIDEO:
            attrs["sheet_image"] = None

        is_active = value("is_active", False)
        sheet_image = attrs.get(
            "sheet_image", getattr(instance, "sheet_image", None) if instance else None
        )
        video = attrs.get("video", getattr(instance, "video", None) if instance else None)
        poster = attrs.get(
            "video_poster", getattr(instance, "video_poster", None) if instance else None
        )
        if is_active and media_type == HomeCampaign.MediaType.IMAGE and not sheet_image:
            raise serializers.ValidationError(
                {"media_type": "Upload the campaign image before activation."}
            )
        if is_active and media_type == HomeCampaign.MediaType.VIDEO and not (video and poster):
            raise serializers.ValidationError(
                {"media_type": "Upload the MP4 video and poster before activation."}
            )
        return attrs


class HomeCampaignMediaSerializer(serializers.ModelSerializer):
    teaser_image = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_campaign_image],
    )
    sheet_image = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_campaign_image],
    )
    video = serializers.FileField(
        required=False,
        allow_null=True,
        validators=[validate_campaign_video],
    )
    video_poster = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_campaign_image],
    )

    class Meta:
        model = HomeCampaign
        fields = ("teaser_image", "sheet_image", "video", "video_poster")


def _file_url(request, field):
    if not field:
        return ""
    url = field.url
    return request.build_absolute_uri(url) if request is not None else url


class ClientHomeCampaignSerializer(serializers.ModelSerializer):
    teaser = serializers.SerializerMethodField()
    sheet = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    action = serializers.SerializerMethodField()
    behavior = serializers.SerializerMethodField()

    class Meta:
        model = HomeCampaign
        fields = ("id", "updated_at", "teaser", "sheet", "media", "action", "behavior")

    def get_teaser(self, instance):
        request = self.context.get("request")
        return {
            "text": instance.teaser_text,
            "background_color": instance.teaser_background_color,
            "text_color": instance.teaser_text_color,
            "image_url": _file_url(request, instance.teaser_image),
        }

    def get_sheet(self, instance):
        return {
            "title": instance.title,
            "description": instance.description,
            "template": instance.template,
            "size": instance.sheet_size,
            "alignment": instance.content_alignment,
            "use_theme_colors": instance.use_theme_colors,
            "background_color": instance.sheet_background_color,
            "text_color": instance.sheet_text_color,
            "button_background_color": instance.button_background_color,
            "button_text_color": instance.button_text_color,
        }

    def get_media(self, instance):
        request = self.context.get("request")
        return {
            "type": instance.media_type,
            "image_url": _file_url(request, instance.sheet_image),
            "video_url": _file_url(request, instance.video),
            "poster_url": _file_url(request, instance.video_poster),
        }

    def get_action(self, instance):
        request = self.context.get("request")
        target = None
        value = ""
        if instance.action_type == HomeCampaign.ActionType.OFFER:
            offer = instance.target_offer
            target = {"id": offer.id, "title": offer.title, "type": offer.type}
        elif instance.action_type == HomeCampaign.ActionType.PRODUCT:
            product = instance.target_product
            variant = product.variants.order_by("price", "id").first()
            target = {
                "id": product.id,
                "name": product.name,
                "image": _file_url(request, product.image),
                "market_name": product.market.name,
                "price": str(variant.price) if variant else "",
                "discount": str(product.discount),
                "variant_id": variant.id if variant else None,
            }
        elif instance.action_type == HomeCampaign.ActionType.MARKET:
            market = instance.target_market
            target = {
                "id": market.id,
                "name": market.name,
                "image": _file_url(request, market.image),
                "classification_id": market.classification_id,
            }
        elif instance.action_type == HomeCampaign.ActionType.PRODUCT_CATEGORY:
            category = instance.target_product_category
            target = {"id": category.id, "name": category.name}
        elif instance.action_type == HomeCampaign.ActionType.EXTERNAL_URL:
            value = instance.external_url
        elif instance.action_type == HomeCampaign.ActionType.COPY_TEXT:
            value = instance.copy_text
        return {
            "type": instance.action_type,
            "label": instance.cta_label,
            "value": value,
            "target": target,
        }

    def get_behavior(self, instance):
        return {
            "open_mode": instance.open_mode,
            "dismiss_behavior": instance.dismiss_behavior,
            "rotation_seconds": max(
                60,
                int(getattr(settings, "HOME_CAMPAIGN_ROTATION_MINUTES", 30)) * 60,
            ),
        }
