import base64
import binascii
import json

from django.conf import settings


class FirebaseConfigurationError(RuntimeError):
    """Raised when Firebase Admin credentials are missing or invalid."""


def load_service_account_data():
    credentials_base64 = settings.FIREBASE_SERVICE_ACCOUNT_BASE64.strip()
    if credentials_base64:
        try:
            credentials_json = base64.b64decode(
                credentials_base64,
                validate=True,
            ).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise FirebaseConfigurationError(
                "FIREBASE_SERVICE_ACCOUNT_BASE64 must be valid "
                "Base64-encoded UTF-8 JSON."
            ) from None
        source_name = "FIREBASE_SERVICE_ACCOUNT_BASE64"
    else:
        credentials_json = settings.FIREBASE_SERVICE_ACCOUNT_JSON.strip()
        source_name = "FIREBASE_SERVICE_ACCOUNT_JSON"
        if not credentials_json:
            raise FirebaseConfigurationError(
                "Firebase configuration is missing. Set "
                "FIREBASE_SERVICE_ACCOUNT_BASE64 or "
                "FIREBASE_SERVICE_ACCOUNT_JSON."
            )

    try:
        credentials_data = json.loads(credentials_json)
    except (json.JSONDecodeError, TypeError):
        raise FirebaseConfigurationError(
            f"{source_name} must contain a valid JSON object."
        ) from None
    if not isinstance(credentials_data, dict):
        raise FirebaseConfigurationError(
            f"{source_name} must contain a JSON object."
        )
    return credentials_data


def get_firebase_app():
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        try:
            certificate = credentials.Certificate(load_service_account_data())
        except FirebaseConfigurationError:
            raise
        except Exception:
            raise FirebaseConfigurationError(
                "Firebase service account credentials are invalid."
            ) from None
        return firebase_admin.initialize_app(certificate)
