from collections import defaultdict
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models, transaction


class Command(BaseCommand):
    help = "Report missing media references and unreferenced files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help="Delete files that have no database reference.",
        )
        parser.add_argument(
            "--clear-missing",
            action="store_true",
            help="Clear database fields whose files are missing.",
        )

    def handle(self, *args, **options):
        storage_references = defaultdict(set)
        storage_objects = {}
        missing = []

        for model in apps.get_models():
            for field in model._meta.concrete_fields:
                if not isinstance(field, models.FileField):
                    continue
                storage = field.storage
                location = getattr(storage, "location", None)
                if not location:
                    continue
                storage_key = str(Path(location).resolve())
                storage_objects[storage_key] = storage
                rows = model._default_manager.exclude(
                    **{field.name: ""}
                ).exclude(**{f"{field.name}__isnull": True}).values_list(
                    model._meta.pk.name,
                    field.name,
                )
                for pk, name in rows.iterator():
                    if not name:
                        continue
                    storage_references[storage_key].add(name)
                    if not storage.exists(name):
                        missing.append((model, field, pk, name))

        orphans = []
        for storage_key, storage in storage_objects.items():
            root = Path(storage_key)
            if not root.exists():
                continue
            referenced = storage_references[storage_key]
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                name = path.relative_to(root).as_posix()
                if name not in referenced:
                    orphans.append((storage, name))

        for model, field, pk, name in missing:
            self.stdout.write(
                f"MISSING {model._meta.label}.{field.name} pk={pk} {name}"
            )
        for _, name in orphans:
            self.stdout.write(f"ORPHAN {name}")

        if options["clear_missing"]:
            with transaction.atomic():
                for model, field, pk, _ in missing:
                    empty_value = None if field.null else ""
                    model._default_manager.filter(pk=pk).update(
                        **{field.name: empty_value}
                    )
        if options["delete_orphans"]:
            for storage, name in orphans:
                storage.delete(name)

        self.stdout.write(
            self.style.SUCCESS(
                "Media audit complete: "
                f"missing={len(missing)}, orphans={len(orphans)}, "
                f"cleared={len(missing) if options['clear_missing'] else 0}, "
                f"deleted={len(orphans) if options['delete_orphans'] else 0}."
            )
        )
