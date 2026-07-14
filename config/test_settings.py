import os
import tempfile


# Force tests to remain completely local.
# Never inherit a production database or production secret.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
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

# Password strength belongs to production. Tests only need deterministic
# hashing semantics, and the production hasher makes the full suite needlessly
# CPU-bound because every test creates several users.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# Temporary local directories prevent tests from touching Cloudinary
# or leaving uploaded files inside the repository.
_TEST_MEDIA_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="yalla-test-media-",
)
_TEST_STATIC_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="yalla-test-static-",
)

MEDIA_ROOT = _TEST_MEDIA_DIRECTORY.name
STATIC_ROOT = _TEST_STATIC_DIRECTORY.name

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}
