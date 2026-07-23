from django.contrib import admin

from .models import PartnerApplication


@admin.register(PartnerApplication)
class PartnerApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "business_type",
        "applicant",
        "status",
        "created_at",
    )
    list_filter = ("status", "business_type", "has_trade_license")
    search_fields = (
        "business_name",
        "contact_first_name",
        "contact_last_name",
        "email",
        "mobile_number",
    )
    readonly_fields = ("created_at", "updated_at", "reviewed_at")

