from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dashboard.seeders import DemoSeedMixin


class Command(DemoSeedMixin, BaseCommand):
    help = "Destructively reset and seed a rich local Egyptian demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Required. Delete all project/domain data before seeding.",
        )
        parser.add_argument(
            "--yes-delete-all",
            action="store_true",
            help="Required with --reset. Confirms destructive local/demo reset.",
        )
        parser.add_argument(
            "--force-production-risk",
            action="store_true",
            help="Allow destructive reset when DEBUG is false.",
        )
        parser.add_argument(
            "--no-media",
            action="store_true",
            help="Skip local placeholder image creation.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Reduce progress output.",
        )

    def handle(self, *args, **options):
        self.quiet = options["quiet"]
        self.no_media = options["no_media"]
        self.skipped = []

        if not options["reset"] or not options["yes_delete_all"]:
            raise CommandError(
                "Refusing to run. Use --reset --yes-delete-all for the "
                "destructive local/demo seed reset."
            )
        if not settings.DEBUG and not options["force_production_risk"]:
            raise CommandError(
                "Refusing to run because DEBUG is false. Add "
                "--force-production-risk only if this is a safe demo database."
            )

        self.stdout.write(
            self.style.WARNING(
                "DESTRUCTIVE RESET: deleting all project/domain data before "
                "creating the Egyptian demo dataset."
            )
        )

        self._delete_seed_media_files()
        with transaction.atomic():
            deleted = self._delete_project_data()
            self._reset_sequences()
            context = self._create_seed_data()
            assertions = self._assert_seed_data(context)

        self._print_summary(context, deleted, assertions)
