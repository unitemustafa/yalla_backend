import warnings

from django.apps import AppConfig


class ConfigAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config"

    def ready(self):
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 25_000_000
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        from .api_cache import register_api_cache_signals
        from .media_cleanup import register_media_cleanup_signals

        register_api_cache_signals()
        register_media_cleanup_signals()
