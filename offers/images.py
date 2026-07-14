import logging

from django.db import transaction
from rest_framework import serializers

from catalog.product_images import (
    delete_storage_file_if_unreferenced,
    schedule_storage_cleanup,
)

from .models import Offer


logger = logging.getLogger(__name__)

OFFER_IMAGE_MAX_SIZE = 5 * 1024 * 1024
OFFER_IMAGE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
OFFER_IMAGE_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


class OfferImageStorageError(Exception):
    pass


def validate_offer_image_upload(value):
    name = value.name or ""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in OFFER_IMAGE_ALLOWED_EXTENSIONS:
        raise serializers.ValidationError(
            "Upload a valid offer image: JPG, JPEG, PNG, or WEBP."
        )
    content_type = (getattr(value, "content_type", "") or "").lower()
    if content_type not in OFFER_IMAGE_ALLOWED_CONTENT_TYPES:
        raise serializers.ValidationError("Unsupported offer image type.")
    if value.size > OFFER_IMAGE_MAX_SIZE:
        raise serializers.ValidationError(
            "Offer images must be 5 MB or smaller."
        )
    return value


def replace_offer_image(offer_id, upload):
    """Store a new image without coupling the upload to the full offer update."""
    offer = None
    old_name = ""
    old_storage = None
    try:
        with transaction.atomic():
            offer = Offer.objects.select_for_update().get(pk=offer_id)
            if offer.image:
                old_name = offer.image.name
                old_storage = offer.image.storage

            offer.image = upload
            offer.save(update_fields=["image", "updated_at"])

            if old_name and old_name != offer.image.name:
                schedule_storage_cleanup(old_storage, old_name)
            return offer
    except Exception as exc:
        # FieldFile is committed only after the storage backend successfully saved it.
        # Remove that new object if the following database write was the failing step.
        if (
            offer is not None
            and offer.image
            and offer.image.name != old_name
            and getattr(offer.image, "_committed", False)
        ):
            try:
                delete_storage_file_if_unreferenced(
                    offer.image.storage,
                    offer.image.name,
                )
            except Exception:
                logger.exception(
                    "Failed to clean an unreferenced offer image after upload failure"
                )
        raise OfferImageStorageError from exc
