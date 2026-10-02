"""
Django settings for config project.
"""

from datetime import timedelta
from pathlib import Path
import os
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development keeps secrets in a git-ignored .env file. Values already
# supplied by the shell or hosting platform remain authoritative.
if os.environ.get("APP_ENV", "development").strip().lower() == "development":
    load_dotenv(BASE_DIR / ".env", override=False)


# SECURITY
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
DEBUG = (
    os.environ.get(
        "DEBUG",
        "False" if IS_PRODUCTION else "True",
    ).lower()
    == "true"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise ImproperlyConfigured("SECRET_KEY is required in production.")
    SECRET_KEY = "dev-only-secret-key-not-for-production"
if IS_PRODUCTION and (
    len(SECRET_KEY) < 50 or SECRET_KEY.startswith(("dev-", "replace-"))
):
    raise ImproperlyConfigured(
        "SECRET_KEY must be a unique random value of at least 50 characters."
    )


def _environment_list(name, default=""):
    return [
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    ]


def _is_allowed_production_cors_origin(origin):
    try:
        parsed = urlsplit(origin)
        parsed.port
    except ValueError:
        return False

    if (
        not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return False

    if parsed.scheme == "https":
        return True

    return parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


ALLOWED_HOSTS = _environment_list(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1" if not IS_PRODUCTION else "",
)
CSRF_TRUSTED_ORIGINS = _environment_list("CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = _environment_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_ALL_ORIGINS = (
    not IS_PRODUCTION
    and os.environ.get("CORS_ALLOW_ALL_ORIGINS", "True").lower() == "true"
)

if IS_PRODUCTION:
    if DEBUG:
        raise ImproperlyConfigured("DEBUG must be False in production.")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "Set ALLOWED_HOSTS to the exact production host names."
        )
    if not CORS_ALLOWED_ORIGINS:
        raise ImproperlyConfigured(
            "CORS_ALLOWED_ORIGINS must contain the dashboard HTTPS origin."
        )
    if any(
        not _is_allowed_production_cors_origin(origin)
        for origin in CORS_ALLOWED_ORIGINS
    ):
        raise ImproperlyConfigured(
            "Production CORS origins must use HTTPS; HTTP is allowed only "
            "for localhost and loopback development origins."
        )

SECURE_SSL_REDIRECT = IS_PRODUCTION
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SECURE_HSTS_SECONDS = int(
    os.environ.get("SECURE_HSTS_SECONDS", "31536000" if IS_PRODUCTION else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = IS_PRODUCTION
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
if IS_PRODUCTION:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Application definition
INSTALLED_APPS = [
    "config.apps.ConfigAppConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "locations",
    "markets",
    "catalog",
    "offers",
    "orders",
    "dashboard",
    "notifications",
    "partners",
    "storages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.observability.RequestContextMiddleware",
    "config.request_limits.RequestBodyLimitMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.api_cache.ApiResponseCacheMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if IS_PRODUCTION and not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL is required in production.")
DATABASE_SSL_REQUIRE = (
    os.environ.get(
        "DATABASE_SSL_REQUIRE",
        "False" if not IS_PRODUCTION else "True",
    ).lower()
    == "true"
)

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL or None,
        conn_max_age=0 if DEBUG else 600,
        ssl_require=DATABASE_SSL_REQUIRE,
    )
}
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "")
if DATABASE_PASSWORD:
    DATABASES["default"]["PASSWORD"] = DATABASE_PASSWORD


# Nginx is the authoritative production limiter. The optional application
# limiter is process-local and is intended for development and focused tests.
RATE_LIMIT_MODE = os.environ.get("RATE_LIMIT_MODE", "off").strip().lower()
RATE_LIMIT_ENFORCE_SCOPES = tuple(
    item.strip()
    for item in os.environ.get("RATE_LIMIT_ENFORCE_SCOPES", "").split(",")
    if item.strip()
)
RATE_LIMIT_CLIENT_IP_HEADER = os.environ.get(
    "RATE_LIMIT_CLIENT_IP_HEADER",
    "HTTP_CF_CONNECTING_IP",
).strip()
RATE_LIMIT_TRUSTED_PROXY_CIDRS = tuple(
    item.strip()
    for item in os.environ.get("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "").split(",")
    if item.strip()
)
RATE_LIMIT_EXEMPT_PATHS = tuple(
    item.strip()
    for item in os.environ.get(
        "RATE_LIMIT_EXEMPT_PATHS",
        "/health/,/healthz/,/readyz/",
    ).split(",")
    if item.strip()
)
RATE_LIMIT_LOG_SAMPLE_RATE = float(os.environ.get("RATE_LIMIT_LOG_SAMPLE_RATE", "0.1"))
RATE_LIMIT_KEY_SECRET = os.environ.get("RATE_LIMIT_KEY_SECRET", SECRET_KEY)
RATE_LIMIT_FAIL_CLOSED_SCOPES = tuple(
    item.strip()
    for item in os.environ.get(
        "RATE_LIMIT_FAIL_CLOSED_SCOPES",
        "admin_login_ip,admin_login_identifier,otp_verify_ip,otp_verify_identifier",
    ).split(",")
    if item.strip()
)


def _rate_limit_rates(scope, default):
    value = os.environ.get(f"RATE_LIMIT_{scope.upper()}_RATES", default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


RATE_LIMIT_POLICY_RATES = {
    "api_anon": _rate_limit_rates("api_anon", "120/5m"),
    "api_user": _rate_limit_rates("api_user", "600/5m"),
    "api_write": _rate_limit_rates("api_write", "120/5m"),
    "login_ip": _rate_limit_rates("login_ip", "30/5m"),
    "login_identifier": _rate_limit_rates("login_identifier", "5/5m,20/1h"),
    "admin_login_ip": _rate_limit_rates("admin_login_ip", "10/5m"),
    "admin_login_identifier": _rate_limit_rates("admin_login_identifier", "5/5m,15/1h"),
    "signup_ip": _rate_limit_rates("signup_ip", "5/1h"),
    "signup_email": _rate_limit_rates("signup_email", "3/1d"),
    "availability_ip": _rate_limit_rates("availability_ip", "30/1m"),
    "otp_send_ip": _rate_limit_rates("otp_send_ip", "30/1h"),
    "otp_send_identifier": _rate_limit_rates("otp_send_identifier", "10/1h"),
    "otp_verify_ip": _rate_limit_rates("otp_verify_ip", "30/10m"),
    "otp_verify_identifier": _rate_limit_rates("otp_verify_identifier", "10/10m"),
    "refresh_ip": _rate_limit_rates("refresh_ip", "120/5m"),
    "refresh_token": _rate_limit_rates("refresh_token", "30/5m"),
    "order_preview_user": _rate_limit_rates("order_preview_user", "60/5m"),
    "order_create_user": _rate_limit_rates("order_create_user", "10/10m"),
    "upload_user": _rate_limit_rates("upload_user", "30/1h"),
    "notification_send_user": _rate_limit_rates("notification_send_user", "10/1h"),
    "snapshot_ip": _rate_limit_rates("snapshot_ip", "60/5m"),
    "share_ip": _rate_limit_rates("share_ip", "60/5m"),
    "geocoding_user": _rate_limit_rates("geocoding_user", "30/1m"),
    "geocoding_global": _rate_limit_rates("geocoding_global", "4/1s"),
}

GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "").strip()
GEOAPIFY_CONNECT_TIMEOUT = float(os.environ.get("GEOAPIFY_CONNECT_TIMEOUT", "3"))
GEOAPIFY_READ_TIMEOUT = float(os.environ.get("GEOAPIFY_READ_TIMEOUT", "5"))

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_CACHE_URL = os.environ.get(
    "REDIS_CACHE_URL",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
)
REDIS_RATE_LIMIT_URL = os.environ.get(
    "REDIS_RATE_LIMIT_URL",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/2"),
)
REDIS_RATE_LIMIT_ENABLED = os.environ.get(
    "REDIS_RATE_LIMIT_ENABLED", "True"
).strip().lower() in ("true", "1", "yes")

CACHES = {
    "default": {
        "BACKEND": "config.cache.ResilientRedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "TIMEOUT": 300,
        "KEY_PREFIX": "yalla:default",
    },
    "geocoding": {
        "BACKEND": "config.cache.ResilientRedisCache",
        "LOCATION": os.environ.get("REDIS_GEOCODING_URL", REDIS_CACHE_URL),
        "TIMEOUT": 86400 * 7,
        "KEY_PREFIX": "yalla:geocoding",
    },
}

API_CACHE_ENABLED = (
    os.environ.get(
        "API_CACHE_ENABLED",
        "False",
    ).lower()
    == "true"
)
API_CATALOG_CACHE_TIMEOUT = int(os.environ.get("API_CATALOG_CACHE_TIMEOUT", "60"))
API_LOGIN_SNAPSHOT_CACHE_TIMEOUT = int(
    os.environ.get("API_LOGIN_SNAPSHOT_CACHE_TIMEOUT", "30")
)
API_CACHE_OBSERVABILITY = (
    os.environ.get(
        "API_CACHE_OBSERVABILITY",
        "True" if APP_ENV == "staging" else "False",
    ).lower()
    == "true"
)


# Celery Configuration
REDIS_CELERY_BROKER_URL = os.environ.get(
    "REDIS_CELERY_BROKER_URL",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/3").rsplit("/", 1)[0] + "/3",
)
CELERY_BROKER_URL = REDIS_CELERY_BROKER_URL
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", None)
CELERY_TASK_ALWAYS_EAGER = os.environ.get(
    "CELERY_TASK_ALWAYS_EAGER",
    "False",
).lower() in ("true", "1", "yes")
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "dashboard.tasks.process_media_job": {"queue": "media"},
    "dashboard.tasks.monitor_media_jobs": {"queue": "default"},
    "notifications.tasks.*": {"queue": "notifications"},
    "accounts.tasks.send_email_task": {"queue": "mail"},
    "config.tasks.delete_storage_file_task": {"queue": "default"},
    "accounts.tasks.cleanup_unverified_users_task": {"queue": "default"},
}
CELERY_BEAT_SCHEDULE = {
    "cleanup-media": {"task": "dashboard.tasks.cleanup_due_media", "schedule": 3600.0},
    "monitor-media-jobs": {"task": "dashboard.tasks.monitor_media_jobs", "schedule": 60.0},
    "cleanup-stale-unverified-users-hourly": {
        "task": "accounts.tasks.cleanup_unverified_users_task",
        "schedule": 3600.0,
    },
}
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True
CELERY_RESULT_EXPIRES = 3600
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "60"))
CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "120"))
FFMPEG_BINARY = os.environ.get("FFMPEG_BINARY", "ffmpeg")
FFPROBE_BINARY = os.environ.get("FFPROBE_BINARY", "ffprobe")


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Media files & Object Storage
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").strip().lower()

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
AWS_STORAGE_PRIVATE_BUCKET_NAME = os.environ.get(
    "AWS_STORAGE_PRIVATE_BUCKET_NAME",
    AWS_STORAGE_BUCKET_NAME,
).strip()
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "auto").strip()
AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "").strip() or None
AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "").strip() or None
AWS_S3_SIGNATURE_VERSION = os.environ.get("AWS_S3_SIGNATURE_VERSION", "s3v4").strip()
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None
AWS_PRESIGNED_EXPIRY = int(os.environ.get("AWS_PRESIGNED_EXPIRY", "300"))

if IS_PRODUCTION and STORAGE_BACKEND == "s3":
    if not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured(
            "AWS_STORAGE_BUCKET_NAME is required when STORAGE_BACKEND is 's3'."
        )
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        raise ImproperlyConfigured(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required when STORAGE_BACKEND is 's3'."
        )

if STORAGE_BACKEND == "s3" and AWS_S3_CUSTOM_DOMAIN:
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
else:
    MEDIA_URL = os.environ.get("MEDIA_URL", "/media/").rstrip("/") + "/"

MEDIA_ROOT = Path(os.environ.get("PUBLIC_MEDIA_ROOT", str(BASE_DIR / "media")))
PRIVATE_MEDIA_ROOT = Path(
    os.environ.get("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private-media"))
)
PRIVATE_MEDIA_INTERNAL_URL = os.environ.get(
    "PRIVATE_MEDIA_INTERNAL_URL",
    "/_protected-media/",
)
PRIVATE_MEDIA_X_ACCEL_REDIRECT = (
    os.environ.get(
        "PRIVATE_MEDIA_X_ACCEL_REDIRECT",
        "True" if IS_PRODUCTION else "False",
    ).lower()
    == "true"
)

STORAGES = {
    "default": {
        "BACKEND": "config.media.OptimizedPublicMediaStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.DatabaseStateJWTAuthentication",
    ),
    "DEFAULT_THROTTLE_CLASSES": ("config.rate_limit.YallaRateThrottle",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "config.api_exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "config.schema.YallaAutoSchema",
    "DEFAULT_PAGINATION_CLASS": "config.pagination.YallaPageNumberPagination",
    "PAGE_SIZE": 50,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Yalla Backend API",
    "DESCRIPTION": "Versioned API contract for Yalla clients and dashboard.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "orders.models.Order.Status",
    },
    "PREPROCESSING_HOOKS": [
        "config.schema.remove_duplicate_optional_slash_routes",
    ],
    # CI generates and validates the complete schema explicitly. Keeping this
    # separate prevents advisory schema warnings from masking Django's own
    # security deployment checks.
    "ENABLE_DJANGO_DEPLOY_CHECK": False,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.observability.RequestIdFilter"},
    },
    "formatters": {
        "json": {"()": "config.observability.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# Client and representative mobile sessions use per-token lifetimes enforced
# by the accounts JWT helpers.
CLIENT_REMEMBERED_SESSION_LIFETIME = timedelta(days=7)
CLIENT_TEMPORARY_SESSION_LIFETIME = timedelta(hours=8)

# These lifetimes apply only to tokens issued by the dashboard admin login.
ADMIN_REMEMBER_SESSION_LIFETIME = timedelta(days=7)
ADMIN_TEMPORARY_SESSION_LIFETIME = timedelta(hours=8)

FIREBASE_SERVICE_ACCOUNT_BASE64 = os.environ.get("FIREBASE_SERVICE_ACCOUNT_BASE64", "")
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)


AUTH_OTP_EXPIRY_SECONDS = 10 * 60
AUTH_OTP_INCLUDE_IN_RESPONSE = (
    os.environ.get("AUTH_OTP_INCLUDE_IN_RESPONSE", "False") == "True"
)
if IS_PRODUCTION and AUTH_OTP_INCLUDE_IN_RESPONSE:
    raise ImproperlyConfigured(
        "AUTH_OTP_INCLUDE_IN_RESPONSE must be False in production."
    )
AUTH_UNVERIFIED_USER_RETENTION_HOURS = int(
    os.environ.get("AUTH_UNVERIFIED_USER_RETENTION_HOURS", "24")
)


# Application-side request limits complement the mandatory ingress limit. The
# middleware can reject requests with Content-Length before multipart parsing;
# the reverse proxy must also reject oversized chunked requests.
API_MAX_REQUEST_BODY_SIZE = int(
    os.environ.get("API_MAX_REQUEST_BODY_SIZE", str(2 * 1024 * 1024))
)
API_SINGLE_UPLOAD_REQUEST_SIZE = int(
    os.environ.get("API_SINGLE_UPLOAD_REQUEST_SIZE", str(8 * 1024 * 1024))
)
DATA_UPLOAD_MAX_MEMORY_SIZE = API_MAX_REQUEST_BODY_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 12
API_PRODUCT_UPLOAD_REQUEST_SIZE = int(
    os.environ.get("API_PRODUCT_UPLOAD_REQUEST_SIZE", str(55 * 1024 * 1024))
)
# Eligible home campaigns rotate automatically instead of using manual priority.
HOME_CAMPAIGN_ROTATION_MINUTES = int(
    os.environ.get("HOME_CAMPAIGN_ROTATION_MINUTES", "30")
)
