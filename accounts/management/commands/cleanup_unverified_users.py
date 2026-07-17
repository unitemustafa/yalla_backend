from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import OneTimePassword, User


class Command(BaseCommand):
    help = "Remove stale unverified accounts and expired registration OTPs."

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
        users = User.objects.filter(
            is_verified=False,
            is_staff=False,
            is_superuser=False,
            created_at__lt=cutoff,
        )
        expired_otps = OneTimePassword.objects.filter(
            purpose=OneTimePassword.Purpose.REGISTRATION,
            expires_at__lte=now,
        )
        user_count = users.count()

        # OTPs belonging to deleted users are included in the user cascade, not
        # counted again as standalone expired OTP cleanup.
        expired_otp_count = expired_otps.exclude(user__in=users).count()

        if not options["dry_run"]:
            with transaction.atomic():
                users.delete()
                expired_otps.delete()

        mode = "Dry run" if options["dry_run"] else "Cleanup complete"
        self.stdout.write(
            f"{mode}: affected users={user_count}, "
            f"expired registration OTPs={expired_otp_count}."
        )
