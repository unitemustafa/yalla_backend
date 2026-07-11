from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings

from .token_security import token_user, validate_client_token_state


class DatabaseStateJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = token_user(validated_token)
        if user.role in {user.Role.CLIENT, user.Role.REPRESENTATIVE}:
            return validate_client_token_state(validated_token, user=user)
        if not api_settings.USER_AUTHENTICATION_RULE(user):
            from rest_framework.exceptions import AuthenticationFailed

            raise AuthenticationFailed(
                "User is inactive.",
                code="user_inactive",
            )
        return user
