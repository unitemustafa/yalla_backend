from pathlib import Path

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers


ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
FORMAT_EXTENSIONS = {
    "JPEG": frozenset({"jpg", "jpeg"}),
    "PNG": frozenset({"png"}),
    "WEBP": frozenset({"webp"}),
}
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_DIMENSION = 12_000


def validate_safe_image(value):
    """Verify decoded image metadata instead of trusting filename or MIME."""

    original_position = value.tell() if hasattr(value, "tell") else None
    try:
        value.seek(0)
        image = Image.open(value)
        detected_format = (image.format or "").upper()
        width, height = image.size
        image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise serializers.ValidationError(
            "Image dimensions are too large to process safely."
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise serializers.ValidationError(
            "Upload a valid, non-corrupted image."
        ) from None
    finally:
        try:
            value.seek(original_position or 0)
        except (AttributeError, OSError):
            pass

    if detected_format not in ALLOWED_IMAGE_FORMATS:
        raise serializers.ValidationError("Unsupported image format.")
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise serializers.ValidationError(
            "Image dimensions are too large to process safely."
        )

    extension = Path(value.name or "").suffix.lower().lstrip(".")
    if extension and extension not in FORMAT_EXTENSIONS[detected_format]:
        raise serializers.ValidationError(
            "Image file extension does not match its content."
        )
    content_type = (getattr(value, "content_type", "") or "").lower()
    if content_type and content_type != FORMAT_CONTENT_TYPES[detected_format]:
        raise serializers.ValidationError(
            "Image content type does not match its content."
        )
    return value
