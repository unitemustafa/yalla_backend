from django.apps import apps
from django.core.files.storage import Storage
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone
from datetime import timedelta


def storage_name_is_referenced(name, *, storage=None):
    if not name:
        return False
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if not isinstance(field, models.FileField):
                continue
            if storage is not None and field.storage != storage:
                continue
            if model._default_manager.filter(**{field.name: name}).exists():
                return True
    return False


def get_identifier_by_storage(storage):
    from config.media import raw_public_media_storage, private_media_storage, raw_private_media_storage

    if isinstance(storage, type(raw_private_media_storage)):
        return "raw_private"

    if storage is raw_public_media_storage or isinstance(
        storage, type(raw_public_media_storage)
    ):
        return "raw_public"
    if storage is private_media_storage or isinstance(
        storage, type(private_media_storage)
    ):
        return "private"
    return "default"


def get_storage_by_identifier(storage_id: str):
    if storage_id == "raw_private":
        from config.media import raw_private_media_storage
        return raw_private_media_storage
    if storage_id == "raw_public":
        from config.media import raw_public_media_storage

        return raw_public_media_storage
    if storage_id == "private":
        from config.media import private_media_storage

        return private_media_storage
    from django.core.files.storage import default_storage

    return default_storage


def delete_storage_file_if_unreferenced(storage: Storage, name):
    if name and not storage_name_is_referenced(name, storage=storage):
        storage.delete(name)


def schedule_storage_cleanup(storage, name):
    if name:
        from dashboard.models import MediaCleanup
        storage_id = get_identifier_by_storage(storage)
        # Persist within the caller's transaction so a broker outage cannot lose cleanup.
        MediaCleanup.objects.update_or_create(
            storage_id=storage_id, name=name,
            defaults={"delete_after": timezone.now() + timedelta(hours=24)},
        )


def _old_file_values(instance):
    if not instance.pk:
        return {}
    file_fields = tuple(
        field
        for field in instance._meta.concrete_fields
        if isinstance(field, models.FileField)
    )
    if not file_fields:
        return {}
    old_instance = instance.__class__._default_manager.filter(pk=instance.pk).first()
    if old_instance is None:
        return {}
    return {field.name: getattr(old_instance, field.name) for field in file_fields}


def capture_replaced_files(sender, instance, raw=False, **kwargs):
    if raw:
        return
    replacements = []
    for field_name, old_file in _old_file_values(instance).items():
        new_file = getattr(instance, field_name)
        old_name = old_file.name if old_file else ""
        new_name = new_file.name if new_file else ""
        if old_name and old_name != new_name:
            replacements.append((old_file.storage, old_name))
    instance._media_cleanup_replacements = replacements


def cleanup_replaced_files(sender, instance, raw=False, **kwargs):
    if raw:
        return
    replacements = getattr(instance, "_media_cleanup_replacements", ())
    for storage, name in replacements:
        schedule_storage_cleanup(storage, name)
    if hasattr(instance, "_media_cleanup_replacements"):
        del instance._media_cleanup_replacements


def cleanup_deleted_files(sender, instance, **kwargs):
    for field in instance._meta.concrete_fields:
        if not isinstance(field, models.FileField):
            continue
        file = getattr(instance, field.name)
        if file and file.name:
            schedule_storage_cleanup(file.storage, file.name)


def register_media_cleanup_signals():
    for model in apps.get_models():
        if not any(
            isinstance(field, models.FileField) for field in model._meta.concrete_fields
        ):
            continue
        label = model._meta.label_lower
        pre_save.connect(
            capture_replaced_files,
            sender=model,
            dispatch_uid=f"media-cleanup-pre-save:{label}",
            weak=False,
        )
        post_save.connect(
            cleanup_replaced_files,
            sender=model,
            dispatch_uid=f"media-cleanup-post-save:{label}",
            weak=False,
        )
        post_delete.connect(
            cleanup_deleted_files,
            sender=model,
            dispatch_uid=f"media-cleanup-post-delete:{label}",
            weak=False,
        )
