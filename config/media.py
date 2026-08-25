from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from PIL import Image, ImageOps


MAX_OUTPUT_DIMENSION = 1600
WEBP_QUALITY = 82


def _uuid_name(name, *, extension):
    directory = Path(name).parent.as_posix()
    filename = f"{uuid4().hex}.{extension}"
    return filename if directory in ("", ".") else f"{directory}/{filename}"


def _has_transparency(image):
    return image.mode in {"LA", "PA", "RGBA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def optimize_image(content):
    """Return metadata-free WebP bytes for a validated image upload."""

    original_position = content.tell() if hasattr(content, "tell") else None
    try:
        content.seek(0)
        with Image.open(content) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (MAX_OUTPUT_DIMENSION, MAX_OUTPUT_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            transparent = _has_transparency(image)
            image = image.convert("RGBA" if transparent else "RGB")
            output = BytesIO()
            if transparent:
                image.save(output, format="WEBP", lossless=True, method=6)
            else:
                image.save(
                    output,
                    format="WEBP",
                    quality=WEBP_QUALITY,
                    method=6,
                )
            return ContentFile(output.getvalue(), name="image.webp")
    finally:
        try:
            content.seek(original_position or 0)
        except (AttributeError, OSError):
            pass


class OptimizedImageStorageMixin:
    def save(self, name, content, max_length=None):
        optimized = optimize_image(content)
        name = _uuid_name(name, extension="webp")
        return super().save(name, optimized, max_length=max_length)


class OptimizedPublicMediaStorage(
    OptimizedImageStorageMixin,
    FileSystemStorage,
):
    pass


@deconstructible
class RawPublicMediaStorage(FileSystemStorage):
    """Public storage for validated non-image media such as campaign MP4s."""

    def save(self, name, content, max_length=None):
        name = _uuid_name(name, extension="mp4")
        return super().save(name, content, max_length=max_length)


@deconstructible
class OptimizedPrivateMediaStorage(
    OptimizedImageStorageMixin,
    FileSystemStorage,
):
    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_MEDIA_ROOT,
            base_url=None,
        )


private_media_storage = OptimizedPrivateMediaStorage()
raw_public_media_storage = RawPublicMediaStorage()
