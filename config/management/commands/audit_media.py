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
                bucket_name = getattr(storage, "bucket_name", None)
                if not location and not bucket_name:
                    continue
                if location and not bucket_name:
                    try:
                        storage_key = str(Path(location).resolve())
                    except Exception:
                        storage_key = str(location)
                else:
                    storage_key = f"s3://{bucket_name}/{location or ''}".rstrip("/")
                storage_objects[storage_key] = storage
                rows = (
                    model._default_manager.exclude(**{field.name: ""})
                    .exclude(**{f"{field.name}__isnull": True})
                    .values_list(
                        model._meta.pk.name,
                        field.name,
                    )
                )
                for pk, name in rows.iterator():
                    if not name:
                        continue
                    storage_references[storage_key].add(name)
                    if not storage.exists(name):
                        missing.append((model, field, pk, name))

        orphans = []
        for storage_key, storage in storage_objects.items():
            referenced = storage_references[storage_key]
            location = getattr(storage, "location", None)
            is_local = False
            if location:
                try:
                    root = Path(location).resolve()
                    if root.exists():
                        is_local = True
                        for path in root.rglob("*"):
                            if not path.is_file():
                                continue
                            name = path.relative_to(root).as_posix()
                            if name not in referenced:
                                orphans.append((storage, name))
                except (ValueError, OSError):
                    is_local = False

            if not is_local:
                bucket = getattr(storage, "bucket", None)
                if bucket is not None and hasattr(bucket, "objects"):
                    try:
                        prefix = getattr(storage, "location", "") or ""
                        for obj in bucket.objects.filter(Prefix=prefix):
                            name = obj.key
                            if prefix and name.startswith(f"{prefix}/"):
                                name = name[len(prefix) + 1 :]
                            if name and name not in referenced:
                                orphans.append((storage, name))
                    except Exception:
                        pass
                elif hasattr(storage, "listdir"):
                    try:

                        def _scan_dir(current_dir):
                            dirs, files = storage.listdir(current_dir)
                            for f in files:
                                full_name = (
                                    f"{current_dir}/{f}".lstrip("/")
                                    if current_dir
                                    else f
                                )
                                if full_name not in referenced:
                                    orphans.append((storage, full_name))
                            for d in dirs:
                                sub = (
                                    f"{current_dir}/{d}".lstrip("/")
                                    if current_dir
                                    else d
                                )
                                _scan_dir(sub)

                        _scan_dir("")
                    except Exception:
                        pass

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
