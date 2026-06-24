from django.urls import path

from .views import (
    CheckEmailView,
    CheckPhoneView,
    CheckUsernameView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshTokenView,
    RegisterView,
    ResendRegistrationOTPView,
    ResetPasswordView,
    VerifyRegistrationOTPView,
)

urlpatterns = [
    path("signup/", RegisterView.as_view(), name="signup"),
    path("verify-email/", VerifyRegistrationOTPView.as_view(), name="verify-email"),
    path(
        "resend-verification",
        ResendRegistrationOTPView.as_view(),
        name="resend-verification",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("check-username/", CheckUsernameView.as_view(), name="check-username"),
    path("check-email/", CheckEmailView.as_view(), name="check-email"),
    path("check-phone/", CheckPhoneView.as_view(), name="check-phone"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
]
