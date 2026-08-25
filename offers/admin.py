from django.contrib import admin

from .models import HomeCampaign


@admin.register(HomeCampaign)
class HomeCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "internal_name",
        "is_active",
        "priority",
        "audience",
        "start_time",
        "end_time",
    )
    list_filter = ("is_active", "audience", "media_type", "action_type")
    search_fields = ("internal_name", "teaser_text", "title")

# Register your models here.
