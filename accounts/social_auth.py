from dataclasses import dataclass

from firebase_admin import auth

from config.firebase_admin import FirebaseConfigurationError, get_firebase_app

from .services import normalize_email


SUPPORTED_PROVIDER_IDS = {
    "google.com": "google",
    "facebook.com": "facebook",
    "apple.com": "apple",
}


class SocialTokenError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedSocialIdentity:
    firebase_uid: str
    provider: str
    email: str
    email_verified: bool
    first_name: str
    last_name: str
    avatar_url: str | None


def verify_social_id_token(id_token):
    try:
        claims = auth.verify_id_token(
            id_token,
            app=get_firebase_app(),
            check_revoked=True,
        )
    except auth.ExpiredIdTokenError:
        raise SocialTokenError("The social sign-in token has expired.") from None
    except auth.RevokedIdTokenError:
        raise SocialTokenError("Social sign-in was revoked. Please try again.") from None
    except auth.UserDisabledError:
        raise SocialTokenError("This social account is disabled.") from None
    except (FirebaseConfigurationError, ValueError, auth.InvalidIdTokenError):
        raise SocialTokenError("The social sign-in token is invalid.") from None
    except Exception:
        raise SocialTokenError("Social sign-in could not be verified.") from None

    firebase_uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    firebase_claims = claims.get("firebase") or {}
    provider_id = str(firebase_claims.get("sign_in_provider") or "").strip()
    provider = SUPPORTED_PROVIDER_IDS.get(provider_id)
    email = normalize_email(str(claims.get("email") or ""))
    if not firebase_uid or provider is None or not email:
        raise SocialTokenError(
            "The social account must provide a valid email address."
        )

    first_name, last_name = _names_from_claims(claims)
    picture = str(claims.get("picture") or "").strip() or None
    return VerifiedSocialIdentity(
        firebase_uid=firebase_uid,
        provider=provider,
        email=email,
        email_verified=bool(claims.get("email_verified")),
        first_name=first_name,
        last_name=last_name,
        avatar_url=picture,
    )


def _names_from_claims(claims):
    first_name = str(claims.get("given_name") or "").strip()
    last_name = str(claims.get("family_name") or "").strip()
    if first_name or last_name:
        return first_name, last_name
    parts = str(claims.get("name") or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""
