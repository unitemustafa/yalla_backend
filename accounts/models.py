from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CLIENT = "client", "Client"
        REPRESENTATIVE = "representative", "Representative"

    phone = models.CharField(max_length=30, unique=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.CLIENT)

    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_policy_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivery_area = models.ForeignKey(
    "locations.DeliveryArea",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="users",
)