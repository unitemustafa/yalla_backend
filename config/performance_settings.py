"""Opt-in settings for the disposable local performance stack only."""

import os

from django.core.exceptions import ImproperlyConfigured

if os.environ.get("PERF_LOCAL_STAGING") != "1":
    raise ImproperlyConfigured("Performance settings require PERF_LOCAL_STAGING=1")
if os.environ.get("APP_ENV") != "performance":
    raise ImproperlyConfigured("Performance settings require APP_ENV=performance")
if os.environ.get("DATABASE_URL") != "postgresql://perf@postgres:5432/yalla_perf":
    raise ImproperlyConfigured("Performance stack must use its isolated database")

from .settings import *  # noqa: E402,F403

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "nginx", "app", "testserver"]
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "mail"
EMAIL_PORT = 1025
EMAIL_USE_TLS = False
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
DEFAULT_FROM_EMAIL = "performance@example.invalid"
FIREBASE_SERVICE_ACCOUNT_BASE64 = ""
FIREBASE_SERVICE_ACCOUNT_JSON = ""
GEOAPIFY_API_KEY = ""
API_CACHE_ENABLED = False
CELERY_TASK_ALWAYS_EAGER = False
PUBLIC_MEDIA_ROOT = "/perf-media/public"
MEDIA_ROOT = PUBLIC_MEDIA_ROOT
PRIVATE_MEDIA_ROOT = "/perf-media/private"
STATIC_ROOT = "/perf-media/static"
MEDIA_URL = "/media/"
STORAGE_BACKEND = "local"
# No device tokens are seeded: notification/outbox workers still run, with no
# external FCM recipients. Delivery latency is explicitly a coverage gap.
LOGGING["formatters"]["json"]["()"] = "tools.performance.telemetry.PerformanceFormatter"
# Celery's CLI log level may replace the root level; retain test task timing
# without changing production logging or logging task arguments/results.
LOGGING["loggers"]["performance.tasks"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}
