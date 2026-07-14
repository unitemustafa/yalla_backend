import json
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Product, ProductVariant
from catalog.serializers import ProductImageSerializer, VariantAttributeValueSerializer
from locations.models import ServiceCity
from markets.models import Market
from markets.serializers import AdminMarketSerializer, ServiceCitySummarySerializer

from .models import Offer, OfferItem


class PrimaryKeyListField(serializers.Field):
    def __init__(self, *, queryset, **kwargs):
        self.queryset = queryset
        super().__init__(**kwargs)

    def get_value(self, dictionary):
        if hasattr(dictionary, "getlist"):
            values = dictionary.getlist(self.field_name)
            if len(values) > 1:
                return values
        return super().get_value(dictionary)

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError("Expected a list of ids.") from exc

        if isinstance(data, tuple):
            data = list(data)

        if not isinstance(data, list):
            raise serializers.ValidationError("Expected a list of ids.")

        ids = []
        for item in data:
            try:
                ids.append(int(item))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("Expected a list of ids.") from exc

        objects_by_id = self.queryset.in_bulk(ids)
        missing_ids = [item_id for item_id in ids if item_id not in objects_by_id]
        if missing_ids:
            raise serializers.ValidationError(
                f"Invalid pk \"{missing_ids[0]}\" - object does not exist."
            )
        return [objects_by_id[item_id] for item_id in ids]

    def to_representation(self, value):
        if hasattr(value, "all"):
            value = value.all()
        return [item.pk for item in value]


class OfferProductSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(read_only=True)
    market_id = serializers.IntegerField(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "market_id",
            "category_id",
            "is_available",
            "name",
            "description",
            "image",
            "images",
            "discount",
            "created_at",
            "updated_at",
        )


class OfferItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product__market").prefetch_related(
            "attribute_values__attribute",
            "attribute_values__option",
            "attribute_values__product_attribute",
            "attribute_values__product_attribute_option",
        ),
        source="variant",
    )
    product_id = serializers.IntegerField(source="variant.product_id", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    price = serializers.DecimalField(
        source="variant.price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    attribute_values = VariantAttributeValueSerializer(
        source="variant.attribute_values",
        many=True,
        read_only=True,
    )

    class Meta:
        model = OfferItem
        fields = (
            "id",
            "variant_id",
            "product_id",
            "product_name",
            "price",
            "attribute_values",
            "quantity",
            "apply_product_discount",
        )
        read_only_fields = ("id",)

    def validate_quantity(self, value):
        if value < 1 or value > 99:
            raise serializers.ValidationError("Quantity must be between 1 and 99.")
        return value


class AdminOfferSerializer(serializers.ModelSerializer):
    effective_status = serializers.SerializerMethodField()
    is_currently_visible = serializers.SerializerMethodField()
    can_send_notification = serializers.SerializerMethodField()
    last_notification_sent_at = serializers.SerializerMethodField()
    notification_send_count = serializers.SerializerMethodField()
    is_multi_market = serializers.SerializerMethodField()
    market_count = serializers.SerializerMethodField()
    markets = serializers.SerializerMethodField()
    market_names_summary = serializers.SerializerMethodField()
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.all(),
        source="market",
        required=False,
    )
    market = AdminMarketSerializer(read_only=True)
    service_city_ids = PrimaryKeyListField(
        queryset=ServiceCity.objects.all(),
        source="service_cities",
        required=False,
    )
    service_cities = ServiceCitySummarySerializer(many=True, read_only=True)
    product_ids = PrimaryKeyListField(
        queryset=Product.objects.all(),
        source="products",
        required=False,
    )
    products = OfferProductSerializer(many=True, read_only=True)
    items = OfferItemSerializer(many=True, required=False)

    class Meta:
        model = Offer
        fields = (
            "id",
            "market",
            "market_id",
            "show_in_general",
            "service_cities",
            "service_city_ids",
            "products",
            "product_ids",
            "items",
            "is_multi_market",
            "market_count",
            "markets",
            "market_names_summary",
            "title",
            "description",
            "image",
            "type",
            "discount",
            "start_time",
            "end_time",
            "active_days",
            "use_limits",
            "user_limit",
            "announcement_url",
            "announcement_cta_label",
            "announcement_priority",
            "announcement_display_seconds",
            "status",
            "effective_status",
            "is_currently_visible",
            "can_send_notification",
            "send_push_notification",
            "push_sent_at",
            "last_notification_sent_at",
            "notification_send_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "push_sent_at", "created_at", "updated_at")

    def to_internal_value(self, data):
        raw_items = data.get("items") if hasattr(data, "get") else None
        if isinstance(raw_items, str):
            try:
                parsed_items = json.loads(raw_items)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError(
                    {"items": "Expected a list of offer items."}
                ) from exc
            if hasattr(data, "dict"):
                data = data.dict()
            else:
                data = dict(data)
            data["items"] = parsed_items
        return super().to_internal_value(data)

    def get_effective_status(self, instance):
        return instance.get_effective_status()

    def get_is_currently_visible(self, instance):
        return instance.is_currently_visible()

    def get_can_send_notification(self, instance):
        return instance.can_send_notification()

    def _completed_dispatches(self, instance):
        return instance.notification_dispatches.filter(status="completed")

    def get_last_notification_sent_at(self, instance):
        dispatch = self._completed_dispatches(instance).order_by("-completed_at").first()
        return dispatch.completed_at if dispatch else None

    def get_notification_send_count(self, instance):
        return self._completed_dispatches(instance).count()

    def _product_markets(self, instance):
        cache_name = "_offer_serializer_markets"
        if not hasattr(instance, cache_name):
            markets = {product.market_id: product.market for product in instance.products.all() if product.market_id}
            setattr(instance, cache_name, [markets[key] for key in sorted(markets)])
        return getattr(instance, cache_name)

    def get_markets(self, instance):
        return [{"id": market.id, "name": market.name, "branch": market.branch} for market in self._product_markets(instance)]

    def get_market_count(self, instance):
        return len(self._product_markets(instance))

    def get_is_multi_market(self, instance):
        return self.get_market_count(instance) > 1

    def get_market_names_summary(self, instance):
        return "، ".join(market.name for market in self._product_markets(instance))

    def validate_title(self, value):
        return value.strip()

    def validate_description(self, value):
        return value.strip()

    def validate_discount(self, value):
        if value < 0:
            raise serializers.ValidationError("Discount cannot be negative.")
        return value

    def validate_active_days(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError(
                    "Active days must be a list."
                ) from exc
        if not isinstance(value, list):
            raise serializers.ValidationError("Active days must be a list.")
        return value

    def validate(self, attrs):
        offer_type = attrs.get("type") or getattr(
            self.instance,
            "type",
            None,
        )
        if offer_type == Offer.OfferType.ANNOUNCEMENT:
            announcement_url = attrs.get(
                "announcement_url",
                getattr(self.instance, "announcement_url", ""),
            ).strip()
            parsed_url = urlparse(announcement_url)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                raise serializers.ValidationError(
                    {"announcement_url": "A valid HTTPS URL is required."}
                )
            if attrs.get("products") or attrs.get("items"):
                raise serializers.ValidationError(
                    {"product_ids": "External announcements cannot include products."}
                )
            attrs["announcement_url"] = announcement_url
            attrs["discount"] = 0
            attrs["use_limits"] = None
            attrs["user_limit"] = None
            attrs["market"] = None
            return attrs

        market = attrs.get("market") or getattr(self.instance, "market", None)
        products = attrs.get("products")
        items = attrs.get("items")
        show_in_general = attrs.get(
            "show_in_general",
            getattr(self.instance, "show_in_general", False),
        )
        service_cities = attrs.get("service_cities")
        start_time = attrs.get("start_time") or getattr(
            self.instance,
            "start_time",
            None,
        )
        end_time = attrs.get("end_time") or getattr(
            self.instance,
            "end_time",
            None,
        )

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time."}
            )

        supplied_status = attrs.get("status")
        if (
            self.instance is not None
            and self.instance.status == Offer.Status.EXPIRED
            and end_time > timezone.now()
            and supplied_status != Offer.Status.INACTIVE
        ):
            attrs["status"] = Offer.Status.ACTIVE
        elif supplied_status == Offer.Status.EXPIRED and end_time > timezone.now():
            attrs["status"] = Offer.Status.ACTIVE

        if items is not None:
            variant_ids = [item["variant"].id for item in items]
            if len(variant_ids) != len(set(variant_ids)):
                raise serializers.ValidationError(
                    {"items": "لا يمكن تكرار نفس تركيبة المنتج داخل العرض."}
                )
            products_to_check = [item["variant"].product for item in items]
            item_product_ids = {product.id for product in products_to_check}
            if products is not None and item_product_ids != {product.id for product in products}:
                raise serializers.ValidationError(
                    {"product_ids": "المنتجات لا تطابق التركيبات المختارة داخل العرض."}
                )
        else:
            products_to_check = products
            if products_to_check is None and self.instance is not None:
                products_to_check = [item.variant.product for item in self.instance.items.select_related("variant__product")]
                if not products_to_check:
                    products_to_check = list(self.instance.products.all())

        if products_to_check is not None:
            if not products_to_check:
                raise serializers.ValidationError(
                    {
                        "items" if items is not None else "product_ids": (
                            "اختر تركيبة منتج واحدة على الأقل للعرض."
                        )
                    }
                )
            if any(not product.is_available for product in products_to_check):
                raise serializers.ValidationError(
                    {"items": "لا يمكن إضافة منتج غير متاح للبيع إلى العرض."}
                )
            if market is None:
                market = products_to_check[0].market
                attrs["market"] = market

        if market is None:
            raise serializers.ValidationError(
                {"market_id": "Offer market is required."}
            )

        if service_cities is None:
            service_cities_to_check = (
                list(self.instance.service_cities.all())
                if self.instance is not None
                else []
            )
        else:
            service_cities_to_check = list(service_cities)

        if not show_in_general and not service_cities_to_check:
            message = (
                "اختر الظهور في العام أو مدينة خدمة واحدة على الأقل."
            )
            raise serializers.ValidationError(
                {
                    "show_in_general": message,
                    "service_city_ids": message,
                }
            )

        if show_in_general and service_cities_to_check:
            message = "Choose general visibility or one service city, not both."
            raise serializers.ValidationError(
                {
                    "show_in_general": message,
                    "service_city_ids": message,
                }
            )

        if len(service_cities_to_check) > 1:
            raise serializers.ValidationError(
                {"service_city_ids": "Only one service city may be selected."}
            )

        if show_in_general:
            if market.scope != Market.Scope.GENERAL:
                raise serializers.ValidationError(
                    {
                        "market_id": (
                            "Offer market must support general visibility."
                        )
                    }
                )

        existing_city_ids = set()
        if self.instance is not None:
            existing_city_ids = set(
                self.instance.service_cities.values_list("id", flat=True)
            )

        inactive_new_city_ids = [
            service_city.id
            for service_city in service_cities_to_check
            if not service_city.is_active and service_city.id not in existing_city_ids
        ]
        if inactive_new_city_ids:
            raise serializers.ValidationError(
                {"service_city_ids": "Only active service cities may be selected."}
            )

        is_service_city_package = (
            offer_type == Offer.OfferType.PACKAGE and not show_in_general
        )
        product_markets = {
            product.market_id: product.market
            for product in (products_to_check or [])
            if product.market_id
        }
        if is_service_city_package and products_to_check:
            if any(product.market_id is None for product in products_to_check):
                raise serializers.ValidationError({"product_ids": "كل منتج في الباكج يجب أن يكون تابعًا لمحل."})
            if any(item.status != Market.Status.ACTIVE for item in product_markets.values()):
                raise serializers.ValidationError({"product_ids": "كل منتجات الباكج يجب أن تكون من محلات نشطة."})
            if any(item.scope != Market.Scope.SERVICE_CITY for item in product_markets.values()):
                raise serializers.ValidationError({"product_ids": "لا يمكن خلط منتجات السوق العام مع منتجات مدينة خدمة."})
            selected_city = service_cities_to_check[0] if len(service_cities_to_check) == 1 else None
            if selected_city and any(not self._market_serves_service_city(item, selected_city) for item in product_markets.values()):
                raise serializers.ValidationError({"product_ids": "هذا المنتج تابع لمحل لا يخدم مدينة العرض المحددة."})
            if market.id not in product_markets:
                if "market" in attrs:
                    raise serializers.ValidationError({"market_id": "المحل الأساسي يجب أن يكون أحد محلات منتجات الباكج."})
                attrs["market"] = products_to_check[0].market
                market = attrs["market"]

        unserved_city_ids = [] if is_service_city_package else [
            service_city.id for service_city in service_cities_to_check
            if not self._market_serves_service_city(market, service_city)
        ]
        if unserved_city_ids:
            raise serializers.ValidationError(
                {"service_city_ids": "Offer market does not serve every selected city."}
            )

        if products_to_check is not None and not is_service_city_package:
            invalid_product_ids = [
                product.id
                for product in products_to_check
                if product.market_id != market.id
            ]
            if invalid_product_ids:
                raise serializers.ValidationError(
                    {
                        "product_ids": (
                            "العروض غير الباكج يجب أن تكون منتجاتها من محل واحد."
                        )
                    }
                )

        return attrs

    @staticmethod
    def _market_serves_service_city(market, service_city):
        return (
            market.service_cities.filter(
                pk=service_city.pk,
                is_active=True,
            ).exists()
        )

    @staticmethod
    def _legacy_items(products):
        items = []
        for product in products:
            variant = product.variants.order_by("id").first()
            if variant is not None:
                items.append({"variant": variant, "quantity": 1})
        return items

    @staticmethod
    def _replace_items(offer, items):
        offer.items.all().delete()
        OfferItem.objects.bulk_create(
            [
                OfferItem(
                    offer=offer,
                    variant=item["variant"],
                    quantity=item.get("quantity", 1),
                    apply_product_discount=item.get("apply_product_discount", True),
                )
                for item in items
            ]
        )
        offer.products.set(
            {item["variant"].product_id for item in items}
        )

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items", None)
        products = validated_data.pop("products", [])
        service_cities = validated_data.pop("service_cities", [])
        if items is None:
            items = self._legacy_items(products)
        offer = Offer.objects.create(**validated_data)
        if products:
            offer.products.set(products)
            OfferItem.objects.bulk_create(
                [
                    OfferItem(
                        offer=offer,
                        variant=item["variant"],
                        quantity=item.get("quantity", 1),
                        apply_product_discount=item.get("apply_product_discount", True),
                    )
                    for item in items
                ]
            )
        else:
            self._replace_items(offer, items)
        offer.service_cities.set(service_cities)
        return offer

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        products = validated_data.pop("products", None)
        service_cities = validated_data.pop("service_cities", None)
        instance = super().update(instance, validated_data)
        if instance.type == Offer.OfferType.ANNOUNCEMENT:
            instance.items.all().delete()
            instance.products.clear()
        elif items is not None:
            self._replace_items(instance, items)
        elif products is not None:
            instance.products.set(products)
            instance.items.all().delete()
            OfferItem.objects.bulk_create(
                [
                    OfferItem(
                        offer=instance,
                        variant=item["variant"],
                        quantity=item.get("quantity", 1),
                        apply_product_discount=item.get("apply_product_discount", True),
                    )
                    for item in self._legacy_items(products)
                ]
            )
        if service_cities is not None:
            instance.service_cities.set(service_cities)
        return instance
