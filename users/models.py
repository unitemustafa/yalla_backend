from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone = models.CharField(max_length=20, unique=True)

    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("client", "Client"),
        ("inspector", "Inspector"),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="client"
    )

    email = models.EmailField(unique=True)

    REQUIRED_FIELDS = [
        "email",
        "first_name",
        "last_name",
        "phone",
    ]

    def __str__(self):
        return self.username