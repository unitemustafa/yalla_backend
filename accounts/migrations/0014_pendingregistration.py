from django.db import migrations, models
import django.db.models.functions.text


def move_unverified_clients_to_pending(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    PendingRegistration = apps.get_model("accounts", "PendingRegistration")
    OneTimePassword = apps.get_model("accounts", "OneTimePassword")

    pending_users = User.objects.filter(
        role="client",
        is_active=True,
        is_verified=False,
        deleted_at__isnull=True,
        is_staff=False,
        is_superuser=False,
    ).order_by("pk")

    for user in pending_users.iterator():
        otp = (
            OneTimePassword.objects.filter(
                user_id=user.pk,
                purpose="registration",
                used_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        registration = PendingRegistration.objects.create(
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            email=user.email.lower(),
            phone=user.phone,
            password_hash=user.password,
            terms_accepted_at=user.terms_accepted_at or user.created_at,
            privacy_policy_version=user.privacy_policy_version,
            otp_code_hash=otp.code_hash if otp is not None else "",
            otp_expires_at=otp.expires_at if otp is not None else None,
            otp_attempts=otp.attempts if otp is not None else 0,
        )
        PendingRegistration.objects.filter(pk=registration.pk).update(
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        user.delete()

    # Admin and representative accounts are provisioned by trusted operators
    # and do not participate in the mobile email-verification flow.
    User.objects.filter(
        models.Q(role="admin") | models.Q(role="representative"),
        is_active=True,
        is_verified=False,
        deleted_at__isnull=True,
    ).update(is_verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_enforce_privileged_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="PendingRegistration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("first_name", models.CharField(max_length=150)),
                ("last_name", models.CharField(max_length=150)),
                ("username", models.CharField(max_length=150)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("phone", models.CharField(max_length=30, unique=True)),
                ("password_hash", models.CharField(max_length=128)),
                ("terms_accepted_at", models.DateTimeField()),
                (
                    "privacy_policy_version",
                    models.CharField(blank=True, max_length=20),
                ),
                ("otp_code_hash", models.CharField(blank=True, max_length=128)),
                ("otp_expires_at", models.DateTimeField(blank=True, null=True)),
                ("otp_attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, db_index=True),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="pendingregistration",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("username"),
                name="accounts_pending_username_ci_unique",
            ),
        ),
        migrations.RunPython(
            move_unverified_clients_to_pending,
            migrations.RunPython.noop,
        ),
    ]
