"""Versioned design and safety contract for uploaded application media."""
import math

from PIL import Image, ImageOps
from rest_framework import serializers

from .image_validation import validate_safe_image

VERSION = 1
IMAGE_MAX_BYTES = 5 * 1024 * 1024
VIDEO_MAX_BYTES = 30 * 1024 * 1024
VIDEO_OUTPUT_MAX_BYTES = 15 * 1024 * 1024
VIDEO_MAX_SECONDS = 30


def _spec(key, width, height, minimum_width, minimum_height, fit, required=None):
    return dict(key=key, width=width, height=height, minimumWidth=minimum_width,
                minimumHeight=minimum_height, fit=fit,
                ratioRequired=(fit == "cover") if required is None else required,
                maxBytes=IMAGE_MAX_BYTES, contentTypes=["image/jpeg", "image/png", "image/webp"])


MEDIA_SPECS = {
    "product": _spec("product", 1600, 1600, 800, 800, "contain"),
    "addon": _spec("addon", 1200, 1200, 600, 600, "contain"),
    "storeLogo": _spec("store-logo", 1024, 1024, 512, 512, "contain"),
    "storeCover": _spec("store-cover", 1600, 900, 1200, 675, "cover", False),
    "classification": _spec("classification", 1200, 1200, 600, 600, "contain"),
    "marketType": _spec("market-type", 1000, 1000, 512, 512, "contain"),
    "offerBanner": _spec("offer-banner", 1600, 600, 1200, 450, "cover"),
    "campaignTeaser": _spec("campaign-teaser", 800, 800, 400, 400, "cover"),
    "campaignMedia": _spec("campaign-media", 1600, 900, 1200, 675, "cover"),
    "avatar": _spec("avatar", 800, 800, 400, 400, "cover"),
    "shippingLogo": _spec("shipping-logo", 800, 800, 400, 400, "contain"),
    "dashboardLogo": _spec("dashboard-logo", 1024, 1024, 512, 512, "contain"),
    "onboarding": _spec("onboarding", 1200, 1200, 400, 400, "contain"),
    "marketLogin": _spec("market-login", 1600, 1000, 640, 400, "cover", False),
    "deliveryLogin": _spec("delivery-login", 1600, 1000, 640, 400, "cover", False),
}


def media_contract():
    return {"version": VERSION, "images": MEDIA_SPECS, "video": {
        "contentTypes": ["video/mp4"], "maxBytes": VIDEO_MAX_BYTES,
        "maxSeconds": VIDEO_MAX_SECONDS, "outputMaxBytes": VIDEO_OUTPUT_MAX_BYTES,
        "maxDimension": 1280, "maxFrameRate": 30,
    }}


def validate_media_image(value, spec_key):
    if value is None:
        return value
    validate_safe_image(value)
    position = value.tell()
    try:
        value.seek(0)
        with Image.open(value) as image:
            width, height = ImageOps.exif_transpose(image).size
    finally:
        value.seek(position)
    spec = MEDIA_SPECS[spec_key]
    if width < spec["minimumWidth"] or height < spec["minimumHeight"]:
        raise serializers.ValidationError(
            f"Minimum image size is {spec['minimumWidth']}x{spec['minimumHeight']}px."
        )
    if spec["ratioRequired"]:
        ratio = spec["width"] / spec["height"]
        if abs(width / height - ratio) / ratio > 0.04:
            raise serializers.ValidationError(
                f"Use the {spec['width']}:{spec['height']} aspect ratio."
            )
    return value


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
