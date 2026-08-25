from django.conf import settings
from django.utils import timezone

from catalog.models import Product
from markets.models import Market
from markets.region import (
    current_market_region_selection,
    visible_market_queryset,
    visible_offer_queryset,
    visible_product_queryset,
)
from .models import HomeCampaign


def _media_is_ready(campaign):
    if campaign.media_type == HomeCampaign.MediaType.NONE:
        return True
    if campaign.media_type == HomeCampaign.MediaType.IMAGE:
        return bool(campaign.sheet_image)
    return bool(campaign.video and campaign.video_poster)


def _target_is_available(campaign, user):
    action_type = campaign.action_type
    if action_type in {
        HomeCampaign.ActionType.NONE,
        HomeCampaign.ActionType.EXTERNAL_URL,
        HomeCampaign.ActionType.COPY_TEXT,
    }:
        return True
    if action_type == HomeCampaign.ActionType.OFFER:
        return visible_offer_queryset(user).filter(pk=campaign.target_offer_id).exists()
    if action_type == HomeCampaign.ActionType.PRODUCT:
        return (
            visible_product_queryset(user)
            .filter(
                pk=campaign.target_product_id,
                archived_at__isnull=True,
                is_available=True,
                market__status=Market.Status.ACTIVE,
                market__archived_at__isnull=True,
                variants__isnull=False,
            )
            .exists()
        )
    if action_type == HomeCampaign.ActionType.MARKET:
        return (
            visible_market_queryset(user)
            .filter(
                pk=campaign.target_market_id,
                status=Market.Status.ACTIVE,
                archived_at__isnull=True,
            )
            .exists()
        )
    if action_type == HomeCampaign.ActionType.PRODUCT_CATEGORY:
        return (
            visible_product_queryset(user)
            .filter(
                category_id=campaign.target_product_category_id,
                archived_at__isnull=True,
                is_available=True,
                market__status=Market.Status.ACTIVE,
                market__archived_at__isnull=True,
                variants__isnull=False,
            )
            .exists()
        )
    return False


def active_home_campaign_for(user):
    selection = current_market_region_selection(user)
    if selection is None:
        return None
    now = timezone.now()
    queryset = HomeCampaign.objects.filter(
        is_active=True,
        start_time__lte=now,
        end_time__gt=now,
    )
    if selection["mode"] == user.MarketRegionMode.GENERAL:
        queryset = queryset.filter(show_in_general=True, service_city__isnull=True)
    else:
        queryset = queryset.filter(
            show_in_general=False,
            service_city_id=selection["service_city"]["id"],
            service_city__is_active=True,
        )
    queryset = queryset.select_related(
        "service_city",
        "target_offer",
        "target_product__market",
        "target_market__classification",
        "target_product_category",
    ).order_by("created_at", "id")
    eligible = [
        campaign
        for campaign in queryset
        if _media_is_ready(campaign) and _target_is_available(campaign, user)
    ]
    if not eligible:
        return None
    rotation_minutes = max(
        1,
        int(getattr(settings, "HOME_CAMPAIGN_ROTATION_MINUTES", 30)),
    )
    slot = int(now.timestamp()) // (rotation_minutes * 60)
    return eligible[slot % len(eligible)]
