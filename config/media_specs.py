"""Versioned design and safety contract for uploaded application media."""
import math

from rest_framework import serializers

from .image_validation import validate_safe_image

VERSION = 1
IMAGE_MAX_BYTES = 5 * 1024 * 1024
VIDEO_MAX_BYTES = 30 * 1024 * 1024
VIDEO_OUTPUT_MAX_BYTES = 15 * 1024 * 1024
VIDEO_MAX_SECONDS = 30


def _spec(key, width, height, fit):
    return dict(key=key, width=width, height=height, minimumWidth=1,
                minimumHeight=1, fit=fit, ratioRequired=False,
                maxBytes=IMAGE_MAX_BYTES, contentTypes=["image/jpeg", "image/png", "image/webp"])


MEDIA_SPECS = {
    "product": _spec("product", 1600, 1600, "contain"),
    "addon": _spec("addon", 1200, 1200, "contain"),
    "storeLogo": _spec("store-logo", 1024, 1024, "contain"),
    "storeCover": _spec("store-cover", 1600, 900, "contain"),
    "classification": _spec("classification", 1200, 1200, "contain"),
    "marketType": _spec("market-type", 1000, 1000, "contain"),
    "offerBanner": _spec("offer-banner", 1600, 600, "cover"),
    "campaignTeaser": _spec("campaign-teaser", 800, 800, "cover"),
    "campaignMedia": _spec("campaign-media", 1600, 900, "cover"),
    "avatar": _spec("avatar", 800, 800, "cover"),
    "shippingLogo": _spec("shipping-logo", 800, 800, "contain"),
    "dashboardLogo": _spec("dashboard-logo", 1024, 1024, "contain"),
    "onboarding": _spec("onboarding", 1200, 1200, "contain"),
    "marketLogin": _spec("market-login", 1600, 1000, "cover"),
    "deliveryLogin": _spec("delivery-login", 1600, 1000, "cover"),
}


def media_contract():
    return {"version": VERSION, "images": MEDIA_SPECS, "video": {
        "contentTypes": ["video/mp4"], "maxBytes": VIDEO_MAX_BYTES,
        "maxSeconds": VIDEO_MAX_SECONDS, "outputMaxBytes": VIDEO_OUTPUT_MAX_BYTES,
        "maxDimension": 1280, "maxFrameRate": 30,
    }}


def validate_media_image(value, spec_key):
    """Accept any image size or ratio; slot dimensions are recommendations only."""
    if value is None:
        return value
    return validate_safe_image(value)


def validate_focal_point(value):
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise serializers.ValidationError("Use a focal point with x and y coordinates.")
    for coordinate in value.values():
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not math.isfinite(coordinate) or not 0 <= coordinate <= 1:
            raise serializers.ValidationError("Focal coordinates must be between 0 and 1.")
    return value


def center_focus():
    return {"x": 0.5, "y": 0.5}


def top_focus():
    return {"x": 0.5, "y": 0.0}
