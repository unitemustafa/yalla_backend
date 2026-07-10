from django.apps import apps
from django.core.files.storage import Storage
from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers

from .models import Product, ProductImage


PRODUCT_IMAGE_MAX_COUNT = 10
PRODUCT_IMAGE_MAX_SIZE = 5 * 1024 * 1024
PRODUCT_IMAGE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PRODUCT_IMAGE_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def validate_product_image_upload(value):
    name = value.name or ""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in PRODUCT_IMAGE_ALLOWED_EXTENSIONS:
        raise serializers.ValidationError(
            "Upload a valid product image: JPG, JPEG, PNG, or WEBP."
        )
    content_type = (getattr(value, "content_type", "") or "").lower()
    if content_type not in PRODUCT_IMAGE_ALLOWED_CONTENT_TYPES:
        raise serializers.ValidationError("Unsupported product image type.")
    if value.size > PRODUCT_IMAGE_MAX_SIZE:
        raise serializers.ValidationError(
            "Product images must be 5 MB or smaller."
        )
    return value


def _sync_legacy_image(product):
    primary = product.images.filter(is_primary=True).order_by(
        "sort_order", "id"
    ).first()
    if primary is None:
        primary = product.images.order_by("sort_order", "id").first()
        if primary is not None:
            ProductImage.objects.filter(pk=primary.pk).update(is_primary=True)
            primary.is_primary = True

    image_name = primary.image.name if primary is not None else None
    current_name = product.image.name if product.image else None
    if current_name != image_name:
        Product.objects.filter(pk=product.pk).update(
            image=image_name,
            updated_at=timezone.now(),
        )
        product.image = image_name
    return primary


def add_product_images(product_id, uploads, primary_index=None):
    if not uploads:
        return []

    stored_files = []
    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product_id)
            existing = list(
                ProductImage.objects.select_for_update()
                .filter(product=product)
                .order_by("sort_order", "id")
            )
            if len(existing) + len(uploads) > PRODUCT_IMAGE_MAX_COUNT:
                raise serializers.ValidationError(
                    {"images": "A product can have at most 10 images."}
                )
            if primary_index is not None and not 0 <= primary_index < len(uploads):
                raise serializers.ValidationError(
                    {"primary_image_index": "Invalid primary image index."}
                )

            has_primary = any(image.is_primary for image in existing)
            selected_index = primary_index
            if selected_index is None and not has_primary:
                selected_index = 0
            if selected_index is not None:
                ProductImage.objects.filter(
                    product=product,
                    is_primary=True,
                ).update(is_primary=False)

            max_order = (
                ProductImage.objects.filter(product=product).aggregate(
                    value=Max("sort_order")
                )["value"]
            )
            next_order = 0 if max_order is None else max_order + 1
            created = []
            for index, upload in enumerate(uploads):
                product_image = ProductImage.objects.create(
                    product=product,
                    image=upload,
                    is_primary=index == selected_index,
                    sort_order=next_order + index,
                )
                stored_files.append((product_image.image.storage, product_image.image.name))
                created.append(product_image)

            _sync_legacy_image(product)
            return created
    except Exception:
        for storage, name in stored_files:
            delete_storage_file_if_unreferenced(storage, name)
        raise


def delete_product_image(product_id, image_id):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        product_image = ProductImage.objects.select_for_update().get(
            pk=image_id,
            product=product,
        )
        was_primary = product_image.is_primary
        product_image.delete()
        if was_primary:
            _sync_legacy_image(product)
        return product


def set_primary_product_image(product_id, image_id):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        images = ProductImage.objects.select_for_update().filter(product=product)
        product_image = images.get(pk=image_id)
        images.filter(is_primary=True).exclude(pk=image_id).update(is_primary=False)
        if not product_image.is_primary:
            ProductImage.objects.filter(pk=image_id).update(is_primary=True)
            product_image.is_primary = True
        _sync_legacy_image(product)
        return product


def reorder_product_images(product_id, image_ids):
    if len(image_ids) != len(set(image_ids)):
        raise serializers.ValidationError(
            {"image_ids": "Duplicate image ids are not allowed."}
        )

    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        images = list(
            ProductImage.objects.select_for_update()
            .filter(product=product)
            .order_by("sort_order", "id")
        )
        images_by_id = {image.id: image for image in images}
        if set(image_ids) != set(images_by_id):
            raise serializers.ValidationError(
                {
                    "image_ids": (
                        "Provide every image belonging to this product exactly once."
                    )
                }
            )
        for sort_order, image_id in enumerate(image_ids):
            images_by_id[image_id].sort_order = sort_order
        ProductImage.objects.bulk_update(images_by_id.values(), ["sort_order"])
        _sync_legacy_image(product)
        return product


def clear_primary_product_image(product_id):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        primary = ProductImage.objects.select_for_update().filter(
            product=product,
            is_primary=True,
        ).first()
        if primary is not None:
            primary.delete()
            _sync_legacy_image(product)
        elif product.image:
            Product.objects.filter(pk=product.pk).update(
                image=None,
                updated_at=timezone.now(),
            )


def storage_name_is_referenced(name):
    if not name:
        return False
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not isinstance(field, models.FileField):
                continue
            if model._default_manager.filter(**{field.name: name}).exists():
                return True
    return False


def delete_storage_file_if_unreferenced(storage: Storage, name):
    if name and not storage_name_is_referenced(name):
        storage.delete(name)


def schedule_storage_cleanup(storage, name):
    if name:
        transaction.on_commit(
            lambda: delete_storage_file_if_unreferenced(storage, name)
        )
