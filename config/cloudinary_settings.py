def build_cloudinary_storage_settings(environ):
    """Keep CLOUDINARY_URL auto-configuration from being overwritten by nulls."""
    result = {"SECURE": True}
    explicit = {
        "CLOUD_NAME": environ.get("CLOUDINARY_CLOUD_NAME"),
        "API_KEY": environ.get("CLOUDINARY_API_KEY"),
        "API_SECRET": environ.get("CLOUDINARY_API_SECRET"),
    }

    if all(explicit.values()):
        result.update(explicit)
    elif not environ.get("CLOUDINARY_URL"):
        # django-cloudinary-storage imports its settings even when local DEBUG
        # uses FileSystemStorage. Preserve that local/test behavior while
        # avoiding null overrides whenever CLOUDINARY_URL is configured.
        result.update(explicit)

    return result

