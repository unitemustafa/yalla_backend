"""
Django settings for config project.
"""

from datetime import timedelta
from pathlib import Path
import os
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
DEBUG = os.environ.get(
    "DEBUG",
    "False" if IS_PRODUCTION else "True",
).lower() == "true"
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
    if any(not origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS):
        raise ImproperlyConfigured(
            "Every production CORS_ALLOWED_ORIGINS value must use HTTPS."
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
    'config.apps.ConfigAppConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'accounts',
    'corsheaders',
    'rest_framework',
    'drf_spectacular',
    'rest_framework_simplejwt.token_blacklist',
    "locations",
    "markets",
    "catalog",
    "offers",
    "orders",
    "dashboard",
    "notifications",
    "partners",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'config.observability.RequestContextMiddleware',
    'config.request_limits.RequestBodyLimitMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'config.api_cache.ApiResponseCacheMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if IS_PRODUCTION and not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL is required in production.")
DATABASE_SSL_REQUIRE = os.environ.get(
    "DATABASE_SSL_REQUIRE",
    "False" if not IS_PRODUCTION else "True",
).lower() == "true"

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


# The application limiter is optional. This deployment keeps it disabled and
# enforces coarse per-IP limits at Nginx, so production does not require Redis.
RATE_LIMIT_REDIS_URL = os.environ.get("RATE_LIMIT_REDIS_URL", "").strip()
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
RATE_LIMIT_LOG_SAMPLE_RATE = float(
    os.environ.get("RATE_LIMIT_LOG_SAMPLE_RATE", "0.1")
)
RATE_LIMIT_KEY_SECRET = os.environ.get("RATE_LIMIT_KEY_SECRET", SECRET_KEY)


def _rate_limit_rates(scope, default):
    value = os.environ.get(f"RATE_LIMIT_{scope.upper()}_RATES", default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


RATE_LIMIT_POLICY_RATES = {
    "api_anon": _rate_limit_rates("api_anon", "120/5m"),
    "api_user": _rate_limit_rates("api_user", "600/5m"),
    "api_write": _rate_limit_rates("api_write", "120/5m"),
    "login_ip": _rate_limit_rates("login_ip", "30/5m"),
    "login_identifier": _rate_limit_rates(
        "login_identifier", "5/5m,20/1h"
    ),
    "admin_login_ip": _rate_limit_rates("admin_login_ip", "10/5m"),
    "admin_login_identifier": _rate_limit_rates(
        "admin_login_identifier", "5/5m,15/1h"
    ),
    "signup_ip": _rate_limit_rates("signup_ip", "5/1h"),
    "signup_email": _rate_limit_rates("signup_email", "3/1d"),
    "availability_ip": _rate_limit_rates("availability_ip", "30/1m"),
    "otp_send_ip": _rate_limit_rates("otp_send_ip", "30/1h"),
    "otp_send_identifier": _rate_limit_rates(
        "otp_send_identifier", "10/1h"
    ),
    "otp_verify_ip": _rate_limit_rates("otp_verify_ip", "30/10m"),
    "otp_verify_identifier": _rate_limit_rates(
        "otp_verify_identifier", "10/10m"
    ),
    "refresh_ip": _rate_limit_rates("refresh_ip", "120/5m"),
    "refresh_token": _rate_limit_rates("refresh_token", "30/5m"),
    "order_preview_user": _rate_limit_rates(
        "order_preview_user", "60/5m"
    ),
    "order_create_user": _rate_limit_rates(
        "order_create_user", "10/10m"
    ),
    "upload_user": _rate_limit_rates("upload_user", "30/1h"),
    "notification_send_user": _rate_limit_rates(
        "notification_send_user", "10/1h"
    ),
    "snapshot_ip": _rate_limit_rates("snapshot_ip", "60/5m"),
    "share_ip": _rate_limit_rates("share_ip", "60/5m"),
    "geocoding_user": _rate_limit_rates("geocoding_user", "30/1m"),
    "geocoding_global": _rate_limit_rates("geocoding_global", "4/1s"),
}

GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "").strip()
GEOAPIFY_CONNECT_TIMEOUT = float(
    os.environ.get("GEOAPIFY_CONNECT_TIMEOUT", "3")
)
RATE_LIMIT_FAIL_CLOSED_SCOPES = frozenset(
    item.strip()
    for item in os.environ.get(
        "RATE_LIMIT_FAIL_CLOSED_SCOPES",
        (
            "login_ip,login_identifier,admin_login_ip,"
            "admin_login_identifier,signup_ip,signup_email,"
            "otp_send_ip,otp_send_identifier,otp_verify_ip,"
            "otp_verify_identifier,refresh_ip,refresh_token"
        ),
    ).split(",")
    if item.strip()
)
GEOAPIFY_READ_TIMEOUT = float(
    os.environ.get("GEOAPIFY_READ_TIMEOUT", "5")
)

CACHE_REDIS_URL = os.environ.get("CACHE_REDIS_URL", "").strip()
CACHES = {
    "default": (
        {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": CACHE_REDIS_URL,
            "KEY_PREFIX": "yalla-api",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,
                "SOCKET_CONNECT_TIMEOUT": float(
                    os.environ.get("CACHE_CONNECT_TIMEOUT", "0.5")
                ),
                "SOCKET_TIMEOUT": float(
                    os.environ.get("CACHE_SOCKET_TIMEOUT", "0.5")
                ),
            },
        }
        if CACHE_REDIS_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "yalla-default-cache",
        }
    ),
    "rate_limit": (
        {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": RATE_LIMIT_REDIS_URL,
            "TIMEOUT": None,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": False,
                "SOCKET_CONNECT_TIMEOUT": float(
                    os.environ.get("RATE_LIMIT_CONNECT_TIMEOUT", "0.5")
                ),
                "SOCKET_TIMEOUT": float(
                    os.environ.get("RATE_LIMIT_SOCKET_TIMEOUT", "0.2")
                ),
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": int(
                        os.environ.get("RATE_LIMIT_MAX_CONNECTIONS", "20")
                    ),
                    "health_check_interval": int(
                        os.environ.get("RATE_LIMIT_HEALTH_CHECK_INTERVAL", "30")
                    ),
                    "retry_on_timeout": False,
                },
            },
        }
        if RATE_LIMIT_REDIS_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "yalla-disabled-rate-limit-cache",
        }
    ),
    "geocoding": (
        {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": RATE_LIMIT_REDIS_URL,
            "KEY_PREFIX": "yalla-geocoding",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": False,
                "SOCKET_CONNECT_TIMEOUT": float(
                    os.environ.get("RATE_LIMIT_CONNECT_TIMEOUT", "0.5")
                ),
                "SOCKET_TIMEOUT": float(
                    os.environ.get("RATE_LIMIT_SOCKET_TIMEOUT", "0.2")
                ),
            },
        }
        if RATE_LIMIT_REDIS_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "yalla-geocoding-cache",
        }
    ),
}

API_CACHE_ENABLED = os.environ.get(
    "API_CACHE_ENABLED",
    "True" if CACHE_REDIS_URL else "False",
).lower() == "true"
API_CATALOG_CACHE_TIMEOUT = int(
    os.environ.get("API_CATALOG_CACHE_TIMEOUT", "60")
)
API_LOGIN_SNAPSHOT_CACHE_TIMEOUT = int(
    os.environ.get("API_LOGIN_SNAPSHOT_CACHE_TIMEOUT", "30")
)
API_CACHE_OBSERVABILITY = os.environ.get(
    "API_CACHE_OBSERVABILITY",
    "True" if APP_ENV == "staging" else "False",
).lower() == "true"


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
# Media files
MEDIA_URL = os.environ.get("MEDIA_URL", "/media/").rstrip("/") + "/"
MEDIA_ROOT = Path(
    os.environ.get("PUBLIC_MEDIA_ROOT", str(BASE_DIR / "media"))
)
PRIVATE_MEDIA_ROOT = Path(
    os.environ.get("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private-media"))
)
PRIVATE_MEDIA_INTERNAL_URL = os.environ.get(
    "PRIVATE_MEDIA_INTERNAL_URL",
    "/_protected-media/",
)
PRIVATE_MEDIA_X_ACCEL_REDIRECT = os.environ.get(
    "PRIVATE_MEDIA_X_ACCEL_REDIRECT",
    "True" if IS_PRODUCTION else "False",
).lower() == "true"

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
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'accounts.authentication.DatabaseStateJWTAuthentication',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'config.rate_limit.YallaRateThrottle',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'EXCEPTION_HANDLER': 'config.api_exceptions.api_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'config.schema.YallaAutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'config.pagination.V2PageNumberPagination',
    'PAGE_SIZE': 50,
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

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://127.0.0.1:6379/0",
)
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BEAT_SCHEDULE = {
    "publish-pending-push-outbox": {
        "task": "notifications.tasks.publish_pending_push_outbox",
        "schedule": 60.0,
    },
}
PUSH_DELIVERY_ASYNC = os.environ.get(
    "PUSH_DELIVERY_ASYNC",
    "True" if IS_PRODUCTION else "False",
).lower() == "true"
PUSH_OUTBOX_MAX_ATTEMPTS = int(
    os.environ.get("PUSH_OUTBOX_MAX_ATTEMPTS", "6")
)

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

FIREBASE_SERVICE_ACCOUNT_BASE64 = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT_BASE64", ""
)
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
API_PRODUCT_UPLOAD_REQUEST_SIZE = int(
    os.environ.get("API_PRODUCT_UPLOAD_REQUEST_SIZE", str(55 * 1024 * 1024))
)
