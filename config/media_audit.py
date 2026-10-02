"""Read-only verification of stored media, including legacy published files."""
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import models
from rest_framework.exceptions import ValidationError

from .image_validation import validate_safe_image
from .media_specs import validate_media_image, VIDEO_MAX_BYTES, VIDEO_OUTPUT_MAX_BYTES
from .video_processing import probe_video

IMAGE_ROLES = {
    ("catalog.product", "image"): "product", ("catalog.productimage", "image"): "product",
    ("catalog.productaddition", "image"): "addon", ("catalog.productcategory", "image"): "classification",
    ("catalog.storesubcategory", "image"): "classification", ("markets.marketclassification", "image"): "classification",
    ("markets.markettype", "image"): "marketType", ("markets.market", "image"): "storeLogo",
    ("markets.market", "cover_image"): "storeCover", ("offers.offer", "image"): "offerBanner",
    ("offers.homecampaign", "sheet_image"): "campaignMedia", ("offers.homecampaign", "teaser_image"): "campaignTeaser",
    ("offers.homecampaignimage", "image"): "campaignMedia", ("accounts.user", "avatar_image"): "avatar",
    ("locations.shippingcompany", "logo"): "shippingLogo", ("dashboard.dashboardsettings", "logo"): "dashboardLogo",
    **{("dashboard.applaunchmedia", name): "onboarding" for name in ("onboarding_one", "onboarding_two", "onboarding_three")},
    ("dashboard.applaunchmedia", "market_login"): "marketLogin", ("dashboard.applaunchmedia", "delivery_login"): "deliveryLogin",
}


def check_stored_media(model, field, storage, name):
    with storage.open(name, "rb") as content:
        if isinstance(field, models.ImageField):
            role = IMAGE_ROLES.get((model._meta.label_lower, field.name))
            try:
                validate_media_image(content, role) if role else validate_safe_image(content)
            except ValidationError as exc:
                raise ValueError(str(exc.detail)) from exc
            return
        if Path(name).suffix.lower() == ".mp4":
            original = model._meta.label_lower == "dashboard.mediajob" and field.name == "source"
            limit = VIDEO_MAX_BYTES if original else VIDEO_OUTPUT_MAX_BYTES
            if content.size > limit:
                raise ValueError("Video file exceeds its permitted size.")
            with TemporaryDirectory(prefix="yalla-audit-") as directory:
                local = Path(directory) / "video.mp4"
                with local.open("wb") as target:
                    for chunk in content.chunks():
                        target.write(chunk)
                probe_video(local, output=not original)
