from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from config.pagination import paginated_list_response

from .models import CourierProfile, OneTimePassword, PendingRegistration
from .permissions import IsAdminRole, IsClientRole
from .client_sessions import (
    access_expires_in,
    apply_new_client_session,
    client_access_token,
    client_session_metadata,
    sync_outstanding_token,
)
from .serializers import (
    AdminUserDetailSerializer,
    AdminUserSerializer,
    AdminUserWriteSerializer,
    AdminLoginSerializer,
    ClientLoginSerializer,
    DeleteAccountSerializer,
    EmailOTPSerializer,
    EmailTokenRefreshSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    RepresentativeLoginSerializer,
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
    issue_registration_otp,
    otp_cooldown_response_data,
    otp_cooldown_status,
    otp_response_data,
    registration_expires_at,
    verify_registration_otp,
    verify_otp,
)
from .exceptions import EmailVerificationRequired

User = get_user_model()


def token_payload(user, request=None, admin_session_lifetime=None, remember=False):
    if not user.is_verified:
        raise EmailVerificationRequired()
    now = timezone.now()
    refresh = RefreshToken.for_user(user)
    refresh["auth_token_version"] = user.auth_token_version
    is_mobile_app_session = user.role in {
        User.Role.CLIENT,
        User.Role.REPRESENTATIVE,
    }
    if is_mobile_app_session:
        apply_new_client_session(refresh, remember=remember, now=now)
    elif admin_session_lifetime is not None:
        admin_session_exp = int(
            (now + admin_session_lifetime).timestamp()
        )
        refresh["admin_session_exp"] = admin_session_exp
        refresh["admin_remember"] = bool(remember)
        refresh.set_exp(lifetime=admin_session_lifetime)

    access = (
        client_access_token(refresh, now=now)
        if is_mobile_app_session
        else refresh.access_token
    )
    if admin_session_lifetime is not None and not is_mobile_app_session:
        access.set_exp(
            from_time=now,
            lifetime=min(
                admin_session_lifetime,
                settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
            )
        )
    sync_outstanding_token(refresh, user=user)
    payload = {
        "accessToken": str(access),
        "refreshToken": str(refresh),
        "expiresIn": access_expires_in(access, now=now),
        "user": UserSerializer(user, context={"request": request}).data,
    }
    if is_mobile_app_session:
        payload["session"] = client_session_metadata(refresh, access)
    return payload


def update_successful_login(user):
    first_successful_login = user.last_login is None
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    if user.role != user.Role.REPRESENTATIVE:
        return

    profile = CourierProfile.objects.filter(user=user).first()
    became_available = profile is not None and not profile.is_available
    if became_available:
        profile.is_available = True
        profile.save(update_fields=["is_available", "updated_at"])

    if first_successful_login or became_available:
        transaction.on_commit(
            lambda courier_id=user.id: _notify_courier_availability(
                courier_id,
                source="login",
            )
        )


def _notify_courier_availability(courier_id, *, source):
    from .models import User
    from notifications.services import create_admin_courier_availability_notification

    courier = User.objects.filter(
        pk=courier_id,
        role=User.Role.REPRESENTATIVE,
    ).first()
    if courier is None:
        return

    create_admin_courier_availability_notification(
        courier,
        is_available=True,
        source=source,
    )


def otp_cooldown_error_response(exc, *, registration=None):
    data = {
        "code": "otp_cooldown",
        "detail": "Please wait before requesting another code.",
        "retry_after_seconds": exc.retry_after_seconds,
    }
    if registration is not None:
        cooldown = otp_cooldown_status(
            registration.email,
            OneTimePassword.Purpose.REGISTRATION,
        )
        data.update(
            {
                "verification_required": True,
                "email": registration.email,
                "resend_available_at": (
                    cooldown["resend_available_at"].isoformat()
                    if cooldown["resend_available_at"] is not None
                    else None
                ),
                "registration_expires_at": registration_expires_at(
                    registration
                ).isoformat(),
            }
        )
    response = Response(
        data,
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response


class RegisterView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("signup_ip", "signup_email")

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        users = self._matching_users(data)
        if users:
            raise ValidationError(self._duplicate_errors(data, users))

        pending_matches = self._matching_pending_registrations(data)
        registration = next(
            (
                pending
                for pending in pending_matches
                if pending.email.lower() == data["email"]
            ),
            None,
        )
        is_retry = registration is not None
        stale_matches = [
            pending.pk
            for pending in pending_matches
            if registration is None or pending.pk != registration.pk
        ]
        if stale_matches:
            stale_emails = list(
                PendingRegistration.objects.filter(pk__in=stale_matches)
                .values_list("email", flat=True)
            )
            PendingRegistration.objects.filter(pk__in=stale_matches).delete()
            for email in stale_emails:
                clear_otp_cooldown(
                    email,
                    OneTimePassword.Purpose.REGISTRATION,
                )

        if registration is None:
            registration = PendingRegistration(email=data["email"])
        registration.username = data["username"]
        registration.email = data["email"]
        registration.first_name = data["first_name"]
        registration.last_name = data["last_name"]
        registration.phone = data["phone"]
        registration.city = data["city"]
        registration.terms_accepted_at = timezone.now()
        registration.password_hash = make_password(data["password"])
        try:
            with transaction.atomic():
                registration.save()
        except IntegrityError:
            users = self._matching_users(data)
            if users:
                raise ValidationError(self._duplicate_errors(data, users))
            registration = next(
                (
                    pending
                    for pending in self._matching_pending_registrations(data)
                    if pending.email.lower() == data["email"]
                ),
                None,
            )
            if registration is None:
                raise ValidationError(
                    {"detail": "Another registration is using these details."}
                )
            is_retry = True

        try:
            registration, code, cooldown_data = issue_registration_otp(
                registration
            )
        except OTPCooldownError as exc:
            registration.refresh_from_db()
            return otp_cooldown_error_response(
                exc,
                registration=registration,
            )
        return Response(
            {
                "detail": (
                    "A new registration OTP has been sent."
                    if is_retry
                    else "Registration OTP sent."
                ),
                "email": registration.email,
                "verification_required": True,
                "registration_expires_at": registration_expires_at(
                    registration
                ).isoformat(),
                **otp_cooldown_response_data(cooldown_data),
                **otp_response_data(code),
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _matching_users(data):
        return list(
            User.objects.select_for_update()
            .filter(deleted_at__isnull=True)
            .filter(
                Q(email__iexact=data["email"])
                | Q(username__iexact=data["username"])
                | Q(phone__in=phone_candidates(data["phone"]))
            )
            .order_by("pk")
        )

    @staticmethod
    def _matching_pending_registrations(data):
        return list(
            PendingRegistration.objects.select_for_update()
            .filter(
                Q(email__iexact=data["email"])
                | Q(username__iexact=data["username"])
                | Q(phone__in=phone_candidates(data["phone"]))
            )
            .order_by("pk")
        )

    @staticmethod
    def _duplicate_errors(data, users):
        errors = {}
        if any(user.email.lower() == data["email"] for user in users):
            errors["email"] = ["An account with this email already exists."]
        if any(user.username.lower() == data["username"].lower() for user in users):
            errors["username"] = ["This username is already taken."]
        phone_values = set(phone_candidates(data["phone"]))
        if any(user.phone in phone_values for user in users):
            errors["phone"] = ["An account with this phone number already exists."]
        return errors or {"email": ["An account with this email already exists."]}


class VerifyRegistrationOTPView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("otp_verify_ip", "otp_verify_identifier")

    @transaction.atomic
    def post(self, request):
        serializer = EmailOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration = PendingRegistration.objects.select_for_update().filter(
            email__iexact=serializer.validated_data["email"],
        ).first()
        if registration is None:
            return Response(
                {"otp": ["Invalid verification code."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verified, error = verify_registration_otp(
            registration,
            serializer.validated_data["otp"],
        )
        if not verified:
            return Response(
                {"otp": [error]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User(
            username=registration.username,
            email=registration.email,
            phone=registration.phone,
            city=registration.city,
            first_name=registration.first_name,
            last_name=registration.last_name,
            password=registration.password_hash,
            role=User.Role.CLIENT,
            is_active=True,
            is_verified=True,
            terms_accepted=True,
            terms_accepted_at=registration.terms_accepted_at,
            privacy_policy_version=registration.privacy_policy_version,
        )
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:
            return Response(
                {
                    "code": "registration_conflict",
                    "detail": (
                        "Account details became unavailable. Return to signup "
                        "and choose different details."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        registration.delete()
        update_successful_login(user)
        clear_otp_cooldown(user.email, OneTimePassword.Purpose.REGISTRATION)
        return Response(token_payload(user, request=request), status=status.HTTP_200_OK)


class ResendRegistrationOTPView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("otp_send_ip", "otp_send_identifier")

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration = PendingRegistration.objects.filter(
            email__iexact=serializer.validated_data["email"],
        ).first()
        if registration is None:
            return Response(
                {"detail": "If registration is pending, a new OTP has been sent."}
            )

        try:
            registration, code, cooldown_data = issue_registration_otp(
                registration
            )
        except OTPCooldownError as exc:
            registration.refresh_from_db()
            return otp_cooldown_error_response(
                exc,
                registration=registration,
            )
        return Response(
            {
                "detail": "A new registration OTP has been sent.",
                "email": registration.email,
                "verification_required": True,
                "registration_expires_at": registration_expires_at(
                    registration
                ).isoformat(),
                **otp_cooldown_response_data(cooldown_data),
                **otp_response_data(code),
            }
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("login_ip", "login_identifier")
    role = None
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"expected_role": self.role},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        remember = serializer.validated_data.get("remember", False)
        update_successful_login(user)
        return Response(
            token_payload(user, request=request, remember=remember)
        )


class ClientLoginView(LoginView):
    role = User.Role.CLIENT
    serializer_class = ClientLoginSerializer


class RepresentativeLoginView(LoginView):
    role = User.Role.REPRESENTATIVE
    serializer_class = RepresentativeLoginSerializer


class AdminLoginView(LoginView):
    role = User.Role.ADMIN
    serializer_class = AdminLoginSerializer
    rate_limit_scopes = (
        "admin_login_ip",
        "admin_login_identifier",
    )

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

    def delete(self, request):
        serializer = DeleteAccountSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        from .deletion import permanently_delete_client_account

        permanently_delete_client_account(request.user)
        return Response(
            {"detail": "Account deleted successfully."},
            status=status.HTTP_200_OK,
        )


class AdminUserListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        users = (
            User.objects.filter(deleted_at__isnull=True)
            .select_related(
                "market_region_service_city",
                "courier_profile__delivery_area",
                "courier_profile__service_city",
            )
            .order_by("-created_at", "-id")
        )
        return paginated_list_response(
            request,
            users,
            AdminUserSerializer,
        )

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
        return paginated_list_response(
            request,
            representatives,
            AdminUserSerializer,
        )


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

class CheckUsernameView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("availability_ip",)

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
        pending = bool(username) and PendingRegistration.objects.filter(
            username__iexact=username
        ).exists()
        return Response(
            {
                "available": not registered,
                "registered": registered,
                "verification_required": pending and not registered,
            }
        )


class CheckEmailView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("availability_ip",)

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
        pending = bool(email) and PendingRegistration.objects.filter(
            email__iexact=email
        ).exists()
        return Response(
            {
                "available": not registered,
                "registered": registered,
                "verification_required": pending and not registered,
            }
        )


class CheckPhoneView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("availability_ip",)

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
        pending = bool(phone) and PendingRegistration.objects.filter(
            phone__in=phone_candidates(phone)
        ).exists()
        return Response(
            {
                "available": not registered,
                "registered": registered,
                "verification_required": pending and not registered,
            }
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    rate_limit_scopes = ("otp_send_ip", "otp_send_identifier")

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"],
            is_active=True,
            is_verified=True,
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
    rate_limit_scopes = ("otp_verify_ip", "otp_verify_identifier")

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
    rate_limit_scopes = ("refresh_ip", "refresh_token")
