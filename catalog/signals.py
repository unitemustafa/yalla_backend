from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Product, ProductImage
from .product_images import schedule_storage_cleanup


@receiver(post_delete, sender=ProductImage)
def cleanup_deleted_product_image(sender, instance, **kwargs):
    if instance.image and instance.image.name:
        schedule_storage_cleanup(instance.image.storage, instance.image.name)


@receiver(post_delete, sender=Product)
def cleanup_deleted_legacy_product_image(sender, instance, **kwargs):
    if instance.image and instance.image.name:
        schedule_storage_cleanup(instance.image.storage, instance.image.name)
