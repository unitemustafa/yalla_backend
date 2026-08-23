import os
import tempfile


# Force tests to remain completely local.
# Never inherit a production database or production secret.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "True"
os.environ["SECRET_KEY"] = (
    "yalla-test-only-secret-key-2026-"
    "never-use-this-value-in-production"
)

from .settings import *  # noqa: F401,F403,E402


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ALLOWED_HOSTS = [
    "testserver",
    "localhost",
    "127.0.0.1",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Rate limiter behavior has focused unit tests. Keep unrelated endpoint suites
# independent from process-local limiter state.
RATE_LIMIT_MODE = "off"

# Expected 4xx branches are exercised heavily; keep test output readable while
# assertLogs continues to opt in for the specific loggers it verifies.
LOGGING["root"]["level"] = "CRITICAL"
LOGGING["loggers"]["django"]["level"] = "CRITICAL"

# Password strength belongs to production. Tests only need deterministic
# hashing semantics, and the production hasher makes the full suite needlessly
# CPU-bound because every test creates several users.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# Temporary local directories keep uploaded files out of the repository.
_TEST_MEDIA_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="yalla-test-media-",
)
_TEST_STATIC_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="yalla-test-static-",
)

MEDIA_ROOT = _TEST_MEDIA_DIRECTORY.name
PRIVATE_MEDIA_ROOT = os.path.join(_TEST_MEDIA_DIRECTORY.name, "private")
STATIC_ROOT = _TEST_STATIC_DIRECTORY.name

STORAGES = {
    "default": {
        "BACKEND": "config.media.OptimizedPublicMediaStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}
