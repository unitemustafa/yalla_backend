from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
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


def is_s3_storage_active():
    return getattr(settings, "STORAGE_BACKEND", "local") == "s3"


def _create_s3_public_storage(**kwargs):
    from storages.backends.s3 import S3Storage

    settings_dict = {
        "access_key": getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
        "secret_key": getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
        "bucket_name": getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""),
        "region_name": getattr(settings, "AWS_S3_REGION_NAME", "auto"),
        "endpoint_url": getattr(settings, "AWS_S3_ENDPOINT_URL", None),
        "custom_domain": getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None),
        "signature_version": getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4"),
        "file_overwrite": getattr(settings, "AWS_S3_FILE_OVERWRITE", False),
        "default_acl": getattr(settings, "AWS_DEFAULT_ACL", None),
        "querystring_auth": False,
    }
    settings_dict.update(kwargs)
    return S3Storage(**settings_dict)


def _create_s3_private_storage(**kwargs):
    from storages.backends.s3 import S3Storage

    private_bucket = getattr(
        settings, "AWS_STORAGE_PRIVATE_BUCKET_NAME", ""
    ) or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    settings_dict = {
        "access_key": getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
        "secret_key": getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
        "bucket_name": private_bucket,
        "region_name": getattr(settings, "AWS_S3_REGION_NAME", "auto"),
        "endpoint_url": getattr(settings, "AWS_S3_ENDPOINT_URL", None),
        "signature_version": getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4"),
        "file_overwrite": False,
        "default_acl": "private",
        "querystring_auth": True,
        "querystring_expire": getattr(settings, "AWS_PRESIGNED_EXPIRY", 300),
        "custom_domain": None,
    }
    settings_dict.update(kwargs)
    return S3Storage(**settings_dict)


class OptimizedImageStorageMixin:
    def save(self, name, content, max_length=None):
        optimized = optimize_image(content)
        name = _uuid_name(name, extension="webp")
        return super().save(name, optimized, max_length=max_length)


@deconstructible
class DelegatingStorage(Storage):
    """Abstract delegating storage that dynamically resolves between S3 and Local Filesystem."""

    def __init__(self, **kwargs):
        self._init_kwargs = kwargs
        self._backend = None
        self._backend_type = None

    def _create_backend(self, backend_type: str, **kwargs):
        raise NotImplementedError

    def get_backend(self):
        current_type = "s3" if is_s3_storage_active() else "local"
        if self._backend is None or self._backend_type != current_type:
            self._backend_type = current_type
            self._backend = self._create_backend(current_type, **self._init_kwargs)
        return self._backend

    def save(self, name, content, max_length=None):
        return self.get_backend().save(name, content, max_length=max_length)

    def open(self, name, mode="rb"):
        return self.get_backend().open(name, mode)

    def _save(self, name, content):
        return self.get_backend()._save(name, content)

    def _open(self, name, mode="rb"):
        return self.get_backend()._open(name, mode)

    def delete(self, name):
        return self.get_backend().delete(name)

    def exists(self, name):
        return self.get_backend().exists(name)

    def url(self, name):
        return self.get_backend().url(name)

    def listdir(self, path):
        return self.get_backend().listdir(path)

    def size(self, name):
        return self.get_backend().size(name)

    def path(self, name):
        return self.get_backend().path(name)

    def get_available_name(self, name, max_length=None):
        return self.get_backend().get_available_name(name, max_length=max_length)

    def get_valid_name(self, name):
        return self.get_backend().get_valid_name(name)

    def get_alternative_name(self, file_root, file_ext):
        return self.get_backend().get_alternative_name(file_root, file_ext)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.get_backend(), name)


@deconstructible
class OptimizedPublicMediaStorage(
    OptimizedImageStorageMixin,
    DelegatingStorage,
):
    def _create_backend(self, backend_type: str, **kwargs):
        if backend_type == "s3":
            return _create_s3_public_storage(**kwargs)
        local_kwargs = {"location": settings.MEDIA_ROOT, "base_url": settings.MEDIA_URL}
        local_kwargs.update(kwargs)
        return FileSystemStorage(**local_kwargs)


@deconstructible
class RawPublicMediaStorage(DelegatingStorage):
    """Public storage for validated non-image media such as campaign MP4s."""

    def _create_backend(self, backend_type: str, **kwargs):
        if backend_type == "s3":
            return _create_s3_public_storage(**kwargs)
        local_kwargs = {"location": settings.MEDIA_ROOT, "base_url": settings.MEDIA_URL}
        local_kwargs.update(kwargs)
        return FileSystemStorage(**local_kwargs)

    def save(self, name, content, max_length=None):
        name = _uuid_name(name, extension="mp4")
        return super().save(name, content, max_length=max_length)


@deconstructible
class OptimizedPrivateMediaStorage(
    OptimizedImageStorageMixin,
    DelegatingStorage,
):
    def _create_backend(self, backend_type: str, **kwargs):
        if backend_type == "s3":
            return _create_s3_private_storage(**kwargs)
        local_kwargs = {
            "location": settings.PRIVATE_MEDIA_ROOT,
            "base_url": None,
        }
        local_kwargs.update(kwargs)
        return FileSystemStorage(**local_kwargs)


private_media_storage = OptimizedPrivateMediaStorage()
raw_public_media_storage = RawPublicMediaStorage()
