from django.db import models
from django.utils import timezone

from config.media import raw_public_media_storage


class Offer(models.Model):
    class OfferType(models.TextChoices):
        PACKAGE = "package", "Package"
        FLASH = "flash", "Flash"
        DISCOUNT = "discount", "Discount"
        ANNOUNCEMENT = "announcement" , "Announcement"
        DELIVERY = "delivery" , "Delivery"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        EXPIRED = "expired", "Expired"

    market = models.ForeignKey(
        "markets.Market",
        on_delete=models.SET_NULL,
        related_name="offers",
        blank=True,
        null=True,
    )
    show_in_general = models.BooleanField(default=False)
    service_cities = models.ManyToManyField(
        "locations.ServiceCity",
        related_name="offers",
        blank=True,
    )

    products = models.ManyToManyField(
        "catalog.Product",
        related_name="offers",
        blank=True,
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="offers/", blank=True, null=True)

    type = models.CharField(
        max_length=30,
        choices=OfferType.choices,
        default=OfferType.PACKAGE,
    )

    discount = models.DecimalField(max_digits=10, decimal_places=2)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    active_days = models.JSONField(default=list, blank=True)
    use_limits = models.PositiveIntegerField(null=True, blank=True)
    user_limit = models.PositiveIntegerField(null=True, blank=True)
    announcement_url = models.URLField(blank=True, default="")
    announcement_cta_label = models.CharField(max_length=80, blank=True, default="")
    announcement_priority = models.PositiveSmallIntegerField(default=0)
    announcement_display_seconds = models.PositiveSmallIntegerField(default=15)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    send_push_notification = models.BooleanField(default=False)
    push_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(blank=True, null=True, db_index=True)

    def __str__(self):
        return self.title

    def get_deletion_mode(self):
        annotated_mode = getattr(self, "deletion_mode_is_archive", None)
        if annotated_mode is not None:
            return "archive" if annotated_mode else "delete"
        if self.order_offers.exists() or self.notification_dispatches.exists():
            return "archive"
        return "delete"

    def get_effective_status(self, now=None):
        now = now or timezone.now()
        if self.status == self.Status.INACTIVE:
            return self.Status.INACTIVE
        if self.end_time <= now:
            return self.Status.EXPIRED
        if self.start_time > now:
            return "scheduled"
        return self.Status.ACTIVE

    def has_valid_visibility_scope(self):
        active_cities = self.service_cities.filter(is_active=True).count()
        return active_cities == 0 if self.show_in_general else active_cities == 1

    def has_active_markets(self):
        from markets.models import Market

        if self.market_id and self.market.status != Market.Status.ACTIVE:
            return False
        return not self.products.exclude(market__status=Market.Status.ACTIVE).exists()

    def is_currently_visible(self, now=None):
        return self.get_effective_status(now) == self.Status.ACTIVE and self.has_valid_visibility_scope()

    def can_send_notification(self, now=None):
        return self.is_currently_visible(now) and self.has_active_markets()


class OfferItem(models.Model):
    offer = models.ForeignKey(
        Offer,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="offer_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    apply_product_discount = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "variant"),
                name="unique_offer_variant",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.variant} x{self.quantity}"


class HomeCampaign(models.Model):
    class Audience(models.TextChoices):
        ALL_CLIENTS = "all_clients", "All clients"
        NEW_CLIENTS = "new_clients", "New clients"
        RETURNING_CLIENTS = "returning_clients", "Returning clients"

    class Template(models.TextChoices):
        HERO = "hero", "Hero"
        SPLIT = "split", "Split"
        MEDIA_FOCUS = "media_focus", "Media focus"

    class SheetSize(models.TextChoices):
        MEDIUM = "medium", "Medium"
        LARGE = "large", "Large"
        NEAR_FULL = "near_full", "Near full"

    class Alignment(models.TextChoices):
        START = "start", "Start"
        CENTER = "center", "Center"

    class MediaType(models.TextChoices):
        NONE = "none", "None"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    class OpenMode(models.TextChoices):
        TAP_ONLY = "tap_only", "Tap only"
        ONCE_PER_SESSION = "once_per_session", "Once per session"
        ONCE_PER_DAY = "once_per_day", "Once per day"

    class DismissBehavior(models.TextChoices):
        COLLAPSE_ONLY = "collapse_only", "Collapse only"
        HIDE_SESSION = "hide_session", "Hide for session"
        HIDE_DAY = "hide_day", "Hide for day"

    class ActionType(models.TextChoices):
        NONE = "none", "None"
        OFFER = "offer", "Offer"
        PRODUCT = "product", "Product"
        MARKET = "market", "Market"
        PRODUCT_CATEGORY = "product_category", "Product category"
        EXTERNAL_URL = "external_url", "External URL"
        COPY_TEXT = "copy_text", "Copy text"

    internal_name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=False, db_index=True)
    priority = models.PositiveIntegerField(default=0, db_index=True)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)

    show_in_general = models.BooleanField(default=True)
    service_city = models.ForeignKey(
        "locations.ServiceCity",
        on_delete=models.PROTECT,
        related_name="home_campaigns",
        blank=True,
        null=True,
    )
    audience = models.CharField(
        max_length=24,
        choices=Audience.choices,
        default=Audience.ALL_CLIENTS,
    )

    teaser_text = models.CharField(max_length=160)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    template = models.CharField(
        max_length=24,
        choices=Template.choices,
        default=Template.HERO,
    )
    sheet_size = models.CharField(
        max_length=24,
        choices=SheetSize.choices,
        default=SheetSize.LARGE,
    )
    content_alignment = models.CharField(
        max_length=12,
        choices=Alignment.choices,
        default=Alignment.CENTER,
    )
    teaser_background_color = models.CharField(max_length=7, default="#FF5A00")
    teaser_text_color = models.CharField(max_length=7, default="#FFFFFF")
    sheet_background_color = models.CharField(max_length=7, default="#FFFFFF")
    sheet_text_color = models.CharField(max_length=7, default="#202124")
    button_background_color = models.CharField(max_length=7, default="#FF5A00")
    button_text_color = models.CharField(max_length=7, default="#FFFFFF")

    media_type = models.CharField(
        max_length=12,
        choices=MediaType.choices,
        default=MediaType.NONE,
    )
    teaser_image = models.ImageField(
        upload_to="home-campaigns/teasers/",
        blank=True,
        null=True,
    )
    sheet_image = models.ImageField(
        upload_to="home-campaigns/images/",
        blank=True,
        null=True,
    )
    video = models.FileField(
        upload_to="home-campaigns/videos/",
        storage=raw_public_media_storage,
        blank=True,
        null=True,
    )
    video_poster = models.ImageField(
        upload_to="home-campaigns/posters/",
        blank=True,
        null=True,
    )

    open_mode = models.CharField(
        max_length=24,
        choices=OpenMode.choices,
        default=OpenMode.TAP_ONLY,
    )
    dismiss_behavior = models.CharField(
        max_length=24,
        choices=DismissBehavior.choices,
        default=DismissBehavior.COLLAPSE_ONLY,
    )

    action_type = models.CharField(
        max_length=24,
        choices=ActionType.choices,
        default=ActionType.NONE,
    )
    cta_label = models.CharField(max_length=80, blank=True, default="")
    target_offer = models.ForeignKey(
        Offer,
        on_delete=models.SET_NULL,
        related_name="home_campaigns",
        blank=True,
        null=True,
    )
    target_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        related_name="home_campaigns",
        blank=True,
        null=True,
    )
    target_market = models.ForeignKey(
        "markets.Market",
        on_delete=models.SET_NULL,
        related_name="home_campaigns",
        blank=True,
        null=True,
    )
    target_product_category = models.ForeignKey(
        "catalog.ProductCategory",
        on_delete=models.SET_NULL,
        related_name="home_campaigns",
        blank=True,
        null=True,
    )
    external_url = models.URLField(blank=True, default="")
    copy_text = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-priority", "-updated_at", "-id")
        constraints = (
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="offers_home_campaign_end_after_start",
            ),
        )

    def __str__(self):
        return self.internal_name

    def get_effective_status(self, now=None):
        now = now or timezone.now()
        if not self.is_active:
            return "inactive"
        if self.end_time <= now:
            return "expired"
        if self.start_time > now:
            return "scheduled"
        return "active"
