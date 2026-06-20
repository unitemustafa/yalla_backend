from django.urls import path

from .views import (
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RefreshTokenView,
    RegisterView,
    ResendRegistrationOTPView,
    ResetPasswordView,
    VerifyRegistrationOTPView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path(
        "register/verify-otp/",
        VerifyRegistrationOTPView.as_view(),
        name="register-verify-otp",
    ),
    path(
        "register/resend-otp/",
        ResendRegistrationOTPView.as_view(),
        name="register-resend-otp",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot-password",
    ),
    path(
        "reset-password/",
        ResetPasswordView.as_view(),
        name="reset-password",
    ),
]
