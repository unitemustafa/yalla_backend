"""
Django settings for config project.
"""

from datetime import timedelta
from pathlib import Path
import os
import dj_database_url

from .cloudinary_settings import build_cloudinary_storage_settings

BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS",
    "https://*.ondigitalocean.app"
).split(",")


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Cloudinary media storage
    'cloudinary_storage',
    'cloudinary',

    'accounts',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    "locations",
    "markets",
    "catalog",
    "offers",
    "orders",
    "dashboard",
    "notifications",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

CORS_ALLOW_ALL_ORIGINS = True

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
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=0 if DEBUG else 600,
        ssl_require=not DEBUG,
    )
}


# Distributed rate limiting. The limiter is disabled by default so local
# development never requires Redis. Production enables it explicitly through
# RATE_LIMIT_MODE after provisioning a non-sharded Redis/Valkey primary.
RATE_LIMIT_REDIS_URL = os.environ.get("RATE_LIMIT_REDIS_URL", "").strip()
RATE_LIMIT_MODE = os.environ.get("RATE_LIMIT_MODE", "off").strip().lower()
RATE_LIMIT_ENFORCE_SCOPES = tuple(
    item.strip()
    for item in os.environ.get("RATE_LIMIT_ENFORCE_SCOPES", "").split(",")
    if item.strip()
)
RATE_LIMIT_CLIENT_IP_HEADER = os.environ.get(
    "RATE_LIMIT_CLIENT_IP_HEADER",
    "HTTP_DO_CONNECTING_IP",
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
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "yalla-default-cache",
    },
    "rate_limit": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": RATE_LIMIT_REDIS_URL or "redis://127.0.0.1:6379/1",
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
}


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
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Cloudinary
CLOUDINARY_STORAGE = build_cloudinary_storage_settings(os.environ)

STORAGES = {
    "default": {
        "BACKEND": (
            "django.core.files.storage.FileSystemStorage"
            if DEBUG
            else "cloudinary_storage.storage.MediaCloudinaryStorage"
        ),
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
    'EXCEPTION_HANDLER': 'config.api_exceptions.api_exception_handler',
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
AUTH_UNVERIFIED_USER_RETENTION_HOURS = int(
    os.environ.get("AUTH_UNVERIFIED_USER_RETENTION_HOURS", "24")
)
