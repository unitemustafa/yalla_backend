from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PartnerApplication(models.Model):
    class BusinessType(models.TextChoices):
        SHOP = "shop", "Shop"
        RESTAURANT = "restaurant", "Restaurant"
        SERVICE_PROVIDER = "service_provider", "Service Provider"

    class ApplicantRole(models.TextChoices):
        OWNER_PARTNER = "owner_partner", "Owner / Partner"
        MANAGER_LEGAL_REPRESENTATIVE = (
            "manager_legal_representative",
            "Manager / Legal Representative",
        )

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_REVIEW = "in_review", "In Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="partner_applications",
    )
    business_name = models.CharField(max_length=180)
    contact_first_name = models.CharField(max_length=100)
    contact_last_name = models.CharField(max_length=100)
    business_type = models.CharField(max_length=30, choices=BusinessType.choices)
    branches_count = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    applicant_role = models.CharField(
        max_length=40,
        choices=ApplicantRole.choices,
    )
    has_trade_license = models.BooleanField()
    email = models.EmailField()
    mobile_number = models.CharField(max_length=30)
    landline = models.CharField(max_length=30, blank=True)
    whatsapp_opt_in = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_partner_applications",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["applicant", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(branches_count__gte=1)
                & models.Q(branches_count__lte=5),
                name="partners_application_branches_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.business_name} ({self.get_status_display()})"

