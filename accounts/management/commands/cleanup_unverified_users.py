from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import OTPCooldown, OneTimePassword, PendingRegistration


class Command(BaseCommand):
    help = "Remove stale pending registrations without touching user accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report affected records without deleting them.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(
            hours=settings.AUTH_UNVERIFIED_USER_RETENTION_HOURS
        )
        registrations = PendingRegistration.objects.filter(updated_at__lt=cutoff)
        stale_emails = list(registrations.values_list("email", flat=True))
        expired_legacy_otps = OneTimePassword.objects.filter(
            purpose=OneTimePassword.Purpose.REGISTRATION,
            expires_at__lte=now,
        )
        registration_count = registrations.count()
        expired_otp_count = expired_legacy_otps.count()

        if not options["dry_run"]:
            with transaction.atomic():
                registrations.delete()
                OTPCooldown.objects.filter(
                    purpose=OneTimePassword.Purpose.REGISTRATION,
                    identifier__in=stale_emails,
                ).delete()
                expired_legacy_otps.delete()

        mode = "Dry run" if options["dry_run"] else "Cleanup complete"
        self.stdout.write(
            f"{mode}: pending registrations={registration_count}, "
            f"expired legacy registration OTPs={expired_otp_count}."
        )
