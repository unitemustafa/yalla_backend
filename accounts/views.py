from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.views import TokenRefreshView

from .courier_rules import active_assigned_orders_for_user
from .deactivation import handle_client_deactivation
from .models import OneTimePassword
from .serializers import (
    AdminUserDetailSerializer,
    AdminUserSerializer,
    AdminUserWriteSerializer,
    AdminLoginSerializer,
    DeleteAccountSerializer,
    EmailOTPSerializer,
    EmailTokenRefreshSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserUpdateSerializer,
    UserSerializer,
    phone_candidates,
)
from .services import (
    OTPCooldownError,
    clear_otp_cooldown,
    issue_otp,
    otp_cooldown_response_data,
    otp_response_data,
    verify_otp,
)

User = get_user_model()


class IsAdminRole(BasePermission):
    message = "Only admin users can manage users."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsClientRole(BasePermission):
    message = "Only client users can update client information."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.CLIENT
        )


def token_payload(user, request=None, admin_session_lifetime=None, remember=False):
    refresh = RefreshToken.for_user(user)
    refresh["auth_token_version"] = user.auth_token_version
    if admin_session_lifetime is not None:
        admin_session_exp = int(
            (timezone.now() + admin_session_lifetime).timestamp()
        )
        refresh["admin_session_exp"] = admin_session_exp
        refresh["admin_remember"] = bool(remember)
        refresh.set_exp(lifetime=admin_session_lifetime)

    access = refresh.access_token
    if admin_session_lifetime is not None:
        access.set_exp(
            lifetime=min(
                admin_session_lifetime,
                settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
            )
        )
    refresh_value = str(refresh)
    return {
        "accessToken": str(access),
        "refreshToken": refresh_value,
        "expiresIn": int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        "user": UserSerializer(user, context={"request": request}).data,
    }


def update_successful_login(user):
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])


def otp_cooldown_error_response(exc):
    return Response(
        {
            "detail": "Please wait before requesting another code.",
            "retry_after_seconds": exc.retry_after_seconds,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


def soft_delete_user(user, *, notify_disabled=False):
    was_active = user.is_active
    deleted_at = timezone.now()
    deleted_marker = f"deleted-{user.pk}-{int(deleted_at.timestamp())}"
    user.deleted_original_email = user.email
    user.deleted_original_username = user.username
    user.deleted_original_phone = user.phone
    user.deleted_original_is_active = user.is_active
    user.is_active = False
    user.deleted_at = deleted_at
    user.email = f"{deleted_marker}@deleted.local"
    user.username = deleted_marker
    user.phone = deleted_marker
    user.save(
        update_fields=[
            "is_active",
            "deleted_at",
            "email",
            "username",
            "phone",
            "deleted_original_email",
            "deleted_original_username",
            "deleted_original_phone",
            "deleted_original_is_active",
            "updated_at",
        ]
    )
    handle_client_deactivation(
        user,
        was_active=was_active,
        notify_disabled=notify_disabled,
    )


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.filter(
            email__iexact=data["email"],
            deleted_at__isnull=True,
        ).first()

        if user is None:
            user = User(
                email=data["email"],
                username=data["username"],
            )

        user.username = data["username"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.phone = data["phone"]
        user.terms_accepted = True
        user.terms_accepted_at = timezone.now()
        user.is_active = False
        user.set_password(data["password"])
        user.save()

        try:
            _, code, cooldown_data = issue_otp(
                user,
                OneTimePassword.Purpose.REGISTRATION,
            )
        except OTPCooldownError as exc:
            return otp_cooldown_error_response(exc)
        return Response(
            {
                "detail": "Registration OTP sent.",
                "email": user.email,
                **otp_cooldown_response_data(cooldown_data),
                **otp_response_data(code),
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyRegistrationOTPView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = EmailOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"],
            is_active=False,
            deleted_at__isnull=True,
        ).first()
        if user is None:
            return Response(
                {"otp": ["Invalid verification code."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _, error = verify_otp(
            user,
            OneTimePassword.Purpose.REGISTRATION,
            serializer.validated_data["otp"],
        )
        if error:
            return Response(
                {"otp": [error]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = True
        user.save(update_fields=["is_active"])
        clear_otp_cooldown(user.email, OneTimePassword.Purpose.REGISTRATION)
        return Response(token_payload(user, request=request), status=status.HTTP_200_OK)


class ResendRegistrationOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"],
            is_active=False,
            deleted_at__isnull=True,
        ).first()
        if user is None:
            return Response(
                {"detail": "If registration is pending, a new OTP has been sent."}
            )

        try:
            _, code, cooldown_data = issue_otp(
                user,
                OneTimePassword.Purpose.REGISTRATION,
            )
        except OTPCooldownError as exc:
            return otp_cooldown_error_response(exc)
        return Response(
            {
                "detail": "A new registration OTP has been sent.",
                **otp_cooldown_response_data(cooldown_data),
                **otp_response_data(code),
            }
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    role = None
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"expected_role": self.role},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        update_successful_login(user)
        return Response(token_payload(user, request=request))


class ClientLoginView(LoginView):
    role = User.Role.CLIENT


class RepresentativeLoginView(LoginView):
    role = User.Role.REPRESENTATIVE


class AdminLoginView(LoginView):
    role = User.Role.ADMIN
    serializer_class = AdminLoginSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"expected_role": self.role},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        remember = serializer.validated_data["remember"]
        update_successful_login(user)
        lifetime = (
            settings.ADMIN_REMEMBER_SESSION_LIFETIME
            if remember
            else settings.ADMIN_TEMPORARY_SESSION_LIFETIME
        )
        return Response(
            token_payload(
                user,
                request=request,
                admin_session_lifetime=lifetime,
                remember=remember,
            )
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Logout successful."},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user, context={"request": request}).data)

    @transaction.atomic
    def delete(self, request):
        serializer = DeleteAccountSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        BlacklistedToken.objects.bulk_create(
            [
                BlacklistedToken(token=token)
                for token in OutstandingToken.objects.filter(user=user)
            ],
            ignore_conflicts=True,
        )
        soft_delete_user(user, notify_disabled=False)
        return Response({"detail": "Account deleted."}, status=status.HTTP_200_OK)


class ClientProfileView(APIView):
    permission_classes = [IsAuthenticated, IsClientRole]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def update(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user, context={"request": request}).data)

    @transaction.atomic
    def patch(self, request):
        return self.update(request)

    @transaction.atomic
    def put(self, request):
        return self.update(request)


class AdminUserListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        users = (
            User.objects.filter(deleted_at__isnull=True)
            .select_related("market_region_service_city")
            .order_by("-created_at", "-id")
        )
        return Response(AdminUserSerializer(users, many=True).data)

    @transaction.atomic
    def post(self, request):
        serializer = AdminUserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            AdminUserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class AdminRepresentativeListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        representatives = (
            User.objects.filter(
                role=User.Role.REPRESENTATIVE,
                deleted_at__isnull=True,
            )
            .select_related(
                "courier_profile__delivery_area",
                "courier_profile__service_city",
                "market_region_service_city",
            )
            .order_by("-created_at", "-id")
        )
        return Response(AdminUserSerializer(representatives, many=True).data)


class AdminUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_user(self, user_id, *, for_update=False):
        queryset = User.objects.filter(deleted_at__isnull=True)
        if for_update:
            queryset = queryset.select_for_update()
        else:
            queryset = queryset.select_related(
                "market_region_service_city"
            )
        return get_object_or_404(
            queryset,
            id=user_id,
        )

    def get(self, request, user_id):
        user = self.get_user(user_id)
        return Response(AdminUserDetailSerializer(user).data)

    @transaction.atomic
    def patch(self, request, user_id):
        user = self.get_user(user_id, for_update=True)
        serializer = AdminUserWriteSerializer(
            user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserDetailSerializer(user).data)

    @transaction.atomic
    def delete(self, request, user_id):
        user = self.get_user(user_id, for_update=True)
        if user.role == User.Role.REPRESENTATIVE and active_assigned_orders_for_user(user).exists():
            return Response(
                {"detail": "Reassign active orders before deleting this courier."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        soft_delete_user(user, notify_disabled=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserRestoreView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @transaction.atomic
    def post(self, request, user_id):
        user = get_object_or_404(
            User.objects.filter(deleted_at__isnull=False).select_related(
                "market_region_service_city"
            ),
            id=user_id,
        )
        original_email = user.deleted_original_email or request.data.get("email")
        original_username = user.deleted_original_username or request.data.get(
            "username"
        )
        original_phone = user.deleted_original_phone or request.data.get("phone")
        original_is_active = user.deleted_original_is_active
        if original_is_active is None:
            original_is_active = request.data.get("is_active", False)
        if not all([original_email, original_username, original_phone]):
            return Response(
                {"detail": "Original account details are unavailable for restoration."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        conflicts = User.objects.filter(deleted_at__isnull=True).exclude(pk=user.pk)
        if conflicts.filter(email__iexact=original_email).exists():
            return Response(
                {"email": "An active account already uses this email."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if conflicts.filter(username__iexact=original_username).exists():
            return Response(
                {"username": "An active account already uses this username."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if conflicts.filter(phone=original_phone).exists():
            return Response(
                {"phone": "An active account already uses this phone."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.deleted_at = None
        user.email = original_email
        user.username = original_username
        user.phone = original_phone
        user.is_active = bool(original_is_active)
        user.deleted_original_email = None
        user.deleted_original_username = None
        user.deleted_original_phone = None
        user.deleted_original_is_active = None
        user.save(
            update_fields=[
                "deleted_at",
                "email",
                "username",
                "phone",
                "is_active",
                "deleted_original_email",
                "deleted_original_username",
                "deleted_original_phone",
                "deleted_original_is_active",
                "updated_at",
            ]
        )
        return Response(AdminUserDetailSerializer(user).data)


class CheckUsernameView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        username = request.query_params.get("username", "").strip()
        queryset = User.objects.filter(
            username__iexact=username,
            deleted_at__isnull=True,
        )
        if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
            exclude_user_id = request.query_params.get("exclude_user_id")
            if exclude_user_id:
                queryset = queryset.exclude(pk=exclude_user_id)
        registered = bool(username) and queryset.exists()
        return Response({"available": not registered, "registered": registered})


class CheckEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        email = request.query_params.get("email", "").strip()
        queryset = User.objects.filter(
            email__iexact=email,
            deleted_at__isnull=True,
        )
        if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
            exclude_user_id = request.query_params.get("exclude_user_id")
            if exclude_user_id:
                queryset = queryset.exclude(pk=exclude_user_id)
        registered = bool(email) and queryset.exists()
        return Response({"available": not registered, "registered": registered})


class CheckPhoneView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        phone = request.query_params.get("phone", "").strip()
        queryset = User.objects.filter(
            phone__in=phone_candidates(phone),
            deleted_at__isnull=True,
        )
        if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
            exclude_user_id = request.query_params.get("exclude_user_id")
            if exclude_user_id:
                queryset = queryset.exclude(pk=exclude_user_id)
        registered = bool(phone) and queryset.exists()
        return Response({"available": not registered, "registered": registered})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"],
            is_active=True,
            deleted_at__isnull=True,
        ).first()

        response_data = {
            "detail": "If an active account exists, a password reset OTP has been sent."
        }
        if user is not None:
            try:
                _, code, cooldown_data = issue_otp(
                    user,
                    OneTimePassword.Purpose.PASSWORD_RESET,
                )
            except OTPCooldownError as exc:
                return otp_cooldown_error_response(exc)
            response_data.update(otp_cooldown_response_data(cooldown_data))
            response_data.update(otp_response_data(code))
        return Response(response_data)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        otp = serializer.validated_data["otp_instance"]
        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        clear_otp_cooldown(user.email, OneTimePassword.Purpose.PASSWORD_RESET)
        BlacklistedToken.objects.bulk_create(
            [
                BlacklistedToken(token=token)
                for token in OutstandingToken.objects.filter(user=user)
            ],
            ignore_conflicts=True,
        )
        return Response({"detail": "Password reset successfully."})


class RefreshTokenView(TokenRefreshView):
    permission_classes = [AllowAny]
    serializer_class = EmailTokenRefreshSerializer
