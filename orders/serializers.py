from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from catalog.models import ProductVariant
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market
from markets.region import (
    address_matches_market_region,
    current_market_region_selection,
    order_region_validation_error,
)
from offers.models import Offer

from .models import Order, OrderItem, OrderOffer

User = get_user_model()


class ServiceCitySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCity
        fields = ("id", "name", "delivery_price", "is_active")


class DeliveryAreaSummarySerializer(serializers.ModelSerializer):
    service_city_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = DeliveryArea
        fields = ("id", "service_city_id", "name", "delivery_price", "is_active")


class MarketSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Market
        fields = ("id", "name", "branch", "status")


class OrderPreviewItemSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related(
            "product",
            "product__market",
        ),
        source="variant",
    )
    quantity = serializers.IntegerField(min_value=1)


class OrderPreviewOfferSerializer(serializers.Serializer):
    offer_id = serializers.PrimaryKeyRelatedField(
        queryset=Offer.objects.select_related(
            "market",
            "service_city",
        ).prefetch_related(
            "products__variants",
            "products__market__service_cities",
        ),
        source="offer",
    )


class OrderPreviewAddressSerializer(serializers.ModelSerializer):
    service_city = ServiceCitySummarySerializer(read_only=True)
    service_city_id = serializers.IntegerField(read_only=True)
    delivery_area = DeliveryAreaSummarySerializer(read_only=True)
    delivery_area_id = serializers.IntegerField(read_only=True)
    delivery_price_preview = serializers.SerializerMethodField()

    class Meta:
        model = Address
        fields = (
            "id",
            "name",
            "latitude",
            "longitude",
            "manual_city",
            "manual_area",
            "service_city",
            "service_city_id",
            "delivery_area",
            "delivery_area_id",
            "delivery_type",
            "delivery_price_preview",
            "is_default",
            "created_at",
        )

    def get_delivery_price_preview(self, instance):
        if (
            instance.delivery_type == Address.DeliveryType.FIXED_AREA
            and instance.delivery_area_id
        ):
            return f"{instance.delivery_area.delivery_price:.2f}"
        return None


class OrderPreviewSerializer(serializers.Serializer):
    DELIVERY_MESSAGE = (
        "Delivery price will be determined later."
    )
    ADDRESS_REGION_MISMATCH_MESSAGE = (
        "This address does not belong to the currently selected market region."
    )
    ADDRESS_REGION_MISMATCH_CODE = "address_region_mismatch"

    address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.select_related(
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
        ).all(),
        source="delivery_address",
        required=False,
        write_only=True,
    )
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        source="service_city",
        required=False,
        write_only=True,
    )
    items = OrderPreviewItemSerializer(many=True, required=False)
    offers = OrderPreviewOfferSerializer(many=True, required=False)

    def validate(self, attrs):
        user = self.context["request"].user
        has_explicit_address = "delivery_address" in attrs
        items = attrs.get("items", [])
        offers = attrs.get("offers", [])

        if not items and not offers:
            raise serializers.ValidationError(
                {"items": "Choose at least one product variant or offer."}
            )

        region_error = order_region_validation_error(
            user,
            [item["variant"] for item in items],
            [item["offer"] for item in offers],
        )
        if region_error:
            raise serializers.ValidationError(region_error)

        current_selection = current_market_region_selection(user)
        address = attrs.get("delivery_address")
        if address is not None and address.user_id != user.id:
            raise serializers.ValidationError(
                {"address_id": "Address does not belong to the authenticated user."}
            )
        if address is not None and not address_matches_market_region(
            address,
            current_selection,
        ):
            raise serializers.ValidationError(self._address_region_mismatch_error())
        if address is None and not has_explicit_address:
            address = self._default_address(user, current_selection)
        if address is None:
            raise serializers.ValidationError(
                {
                    "requires_address_selection": True,
                    "address_id": (
                        "Choose an address for the currently selected market region."
                    ),
                }
            )

        service_city = self._service_city_for_order(
            address,
            attrs.get("service_city"),
        )
        is_general_manual = self._is_general_manual_address(user, address)
        if is_general_manual and attrs.get("service_city") is not None:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be empty for General manual delivery."}
            )
        if service_city is None and not is_general_manual:
            raise serializers.ValidationError(
                {"service_city_id": "Service city is required."}
            )
        if service_city is not None and not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        delivery_context = self._delivery_context(address)

        attrs["user"] = user
        attrs["delivery_address"] = address
        attrs["service_city"] = service_city
        attrs["current_selection"] = current_selection
        attrs.update(delivery_context)
        return attrs

    def preview_data(self):
        user = self.validated_data["user"]
        current_selection = self.validated_data["current_selection"]
        address = self.validated_data.get("delivery_address")
        service_city = self.validated_data["service_city"]
        delivery_area = self.validated_data["delivery_area"]
        delivery_type = self.validated_data["delivery_type"]
        fixed_delivery_price = self.validated_data["delivery_price"]
        delivery_message = self.validated_data["delivery_message"]
        items = self.validated_data.get("items", [])
        offers = self.validated_data.get("offers", [])
        market_groups = {}
        selected_lines_by_product = {}

        for item in items:
            variant = item["variant"]
            product = variant.product
            quantity = item["quantity"]
            subtotal = variant.price * quantity
            group = self._market_group(market_groups, product.market)
            line = {
                "variant_id": variant.id,
                "product_id": product.id,
                "product_name": product.name,
                "image": self._image_url(product.image),
                "quantity": quantity,
                "unit_price": self._money(variant.price),
                "subtotal": self._money(subtotal),
            }
            group["selected_products"].append(line)
            group["products_subtotal"] += subtotal
            selected_lines_by_product.setdefault(product.id, []).append(
                {
                    "line": line,
                    "subtotal": subtotal,
                }
            )

        for item in offers:
            offer = item["offer"]
            for offer_group in self._offer_product_rows_by_market(
                offer,
                selected_lines_by_product,
            ).values():
                group = self._market_group(market_groups, offer_group["market"])
                group["products_subtotal"] += offer_group[
                    "added_products_subtotal"
                ]
                discount_amount = self._percentage_amount(
                    offer_group["offer_products_subtotal"],
                    offer.discount,
                )
                group["total_offer_discounts"] += discount_amount
                group["selected_offers"].append(
                    {
                        "id": offer.id,
                        "title": offer.title,
                        "description": offer.description,
                        "image": self._image_url(offer.image),
                        "type": offer.type,
                        "discount_percentage": self._money(offer.discount),
                        "offer_products_subtotal": self._money(
                            offer_group["offer_products_subtotal"]
                        ),
                        "discount_amount": self._money(discount_amount),
                        "products": offer_group["products"],
                    }
                )

        market_groups_data = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        delivery_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for market_id in sorted(market_groups):
            group = market_groups[market_id]
            delivery_available = self._market_serves_city(
                group["market"],
                service_city,
            )
            delivery_price = (
                fixed_delivery_price
                if delivery_available
                and delivery_type == Order.DeliveryType.FIXED_AREA
                else None
            )
            delivery_price_total = delivery_price or Decimal("0.00")
            market_total = (
                group["products_subtotal"]
                - group["total_offer_discounts"]
                + delivery_price_total
            )
            subtotal += group["products_subtotal"]
            discount_total += group["total_offer_discounts"]
            delivery_total += delivery_price_total
            grand_total += market_total
            market_groups_data.append(
                {
                    "market": {
                        "id": group["market"].id,
                        "name": group["market"].name,
                        "branch": group["market"].branch,
                    },
                    "service_city": self._service_city_data(service_city),
                    "delivery_area": (
                        DeliveryAreaSummarySerializer(delivery_area).data
                        if delivery_area is not None
                        else None
                    ),
                    "delivery_type": delivery_type,
                    "delivery_price": self._money_nullable(delivery_price),
                    "delivery_message": delivery_message,
                    "delivery_available": delivery_available,
                    "selected_products": group["selected_products"],
                    "selected_offers": group["selected_offers"],
                    "pricing": {
                        "products_subtotal": self._money(
                            group["products_subtotal"]
                        ),
                        "total_offer_discounts": self._money(
                            group["total_offer_discounts"]
                        ),
                        "delivery_price": self._money_nullable(delivery_price),
                        "market_total": self._money(market_total),
                    },
                }
            )

        addresses = user.addresses.select_related(
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
        ).filter(is_active=True).order_by("-is_default", "-created_at")
        addresses = [
            item
            for item in addresses
            if address_matches_market_region(
                item,
                current_selection,
            )
        ]
        return {
            "addresses": OrderPreviewAddressSerializer(
                addresses,
                many=True,
                context=self.context,
            ).data,
            "selected_address": (
                OrderPreviewAddressSerializer(address, context=self.context).data
                if address is not None
                else None
            ),
            "service_city": self._service_city_data(service_city),
            "market_groups": market_groups_data,
            "summary": {
                "subtotal": self._money(subtotal),
                "discount_total": self._money(discount_total),
                "delivery_total": self._money(delivery_total),
                "grand_total": self._money(grand_total),
            },
        }

    @staticmethod
    def _default_address(user, current_selection):
        address = (
            user.addresses.select_related(
                "service_city",
                "delivery_area",
                "delivery_area__service_city",
            )
            .filter(is_default=True, is_active=True)
            .order_by("-created_at")
            .first()
        )
        if address_matches_market_region(address, current_selection):
            return address
        return None

    @classmethod
    def _address_region_mismatch_error(cls):
        return {
            "address_id": cls.ADDRESS_REGION_MISMATCH_MESSAGE,
            "code": cls.ADDRESS_REGION_MISMATCH_CODE,
        }

    @staticmethod
    def _service_city_for_order(address, request_service_city):
        if address is not None and address.service_city_id:
            return address.service_city
        return request_service_city

    @staticmethod
    def _is_general_manual_address(user, address):
        return (
            getattr(user, "market_region_mode", None) == User.MarketRegionMode.GENERAL
            and address is not None
            and address.service_city_id is None
            and address.delivery_area_id is None
            and bool(address.manual_city)
            and bool(address.manual_area)
        )

    @staticmethod
    def _service_city_data(service_city):
        if service_city is None:
            return None
        return ServiceCitySummarySerializer(service_city).data

    def _delivery_context(self, address):
        if (
            address is not None
            and address.delivery_type == Address.DeliveryType.FIXED_AREA
            and address.delivery_area_id
        ):
            delivery_area = address.delivery_area
            if not delivery_area.is_active:
                raise serializers.ValidationError(
                    {"delivery_area": "Delivery area must be active."}
                )
            if delivery_area.service_city_id != address.service_city_id:
                raise serializers.ValidationError(
                    {
                        "delivery_area": (
                            "Delivery area must belong to the address service city."
                        )
                    }
                )
            return {
                "delivery_area": delivery_area,
                "delivery_type": Order.DeliveryType.FIXED_AREA,
                "delivery_price": delivery_area.delivery_price,
                "delivery_message": "",
            }

        return {
            "delivery_area": None,
            "delivery_type": Order.DeliveryType.DELIVERY,
            "delivery_price": None,
            "delivery_message": self.DELIVERY_MESSAGE,
        }

    @staticmethod
    def _market_group(groups, market):
        if market.id not in groups:
            groups[market.id] = {
                "market": market,
                "selected_products": [],
                "selected_offers": [],
                "products_subtotal": Decimal("0.00"),
                "total_offer_discounts": Decimal("0.00"),
            }
        return groups[market.id]

    @staticmethod
    def _percentage_amount(amount, percentage):
        return (amount * percentage / Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def _image_url(self, image):
        if not image:
            return None
        request = self.context.get("request")
        url = image.url
        return request.build_absolute_uri(url) if request is not None else url

    def _offer_product_rows_by_market(self, offer, selected_lines_by_product):
        groups = {}

        for product in offer.products.all():
            group = groups.setdefault(
                product.market_id,
                {
                    "market": product.market,
                    "products": [],
                    "offer_products_subtotal": Decimal("0.00"),
                    "added_products_subtotal": Decimal("0.00"),
                },
            )
            selected_lines = selected_lines_by_product.get(product.id, [])
            if selected_lines:
                for selected_line in selected_lines:
                    line = selected_line["line"]
                    subtotal = selected_line["subtotal"]
                    group["offer_products_subtotal"] += subtotal
                    group["products"].append(
                        {
                            "product_id": product.id,
                            "product_name": product.name,
                            "image": self._image_url(product.image),
                            "variant_id": line["variant_id"],
                            "quantity": line["quantity"],
                            "unit_price": line["unit_price"],
                            "subtotal": line["subtotal"],
                            "is_selected": True,
                        }
                    )
                continue

            variant = product.variants.order_by("id").first()
            if variant is None:
                group["products"].append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "image": self._image_url(product.image),
                        "variant_id": None,
                        "quantity": 0,
                        "unit_price": self._money(Decimal("0.00")),
                        "subtotal": self._money(Decimal("0.00")),
                        "is_selected": False,
                    }
                )
                continue

            subtotal = variant.price
            group["offer_products_subtotal"] += subtotal
            group["added_products_subtotal"] += subtotal
            group["products"].append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "image": self._image_url(product.image),
                    "variant_id": variant.id,
                    "quantity": 1,
                    "unit_price": self._money(variant.price),
                    "subtotal": self._money(subtotal),
                    "is_selected": False,
                }
            )

        return groups

    @staticmethod
    def _money(value):
        return f"{value:.2f}"

    @classmethod
    def _money_nullable(cls, value):
        if value is None:
            return None
        return cls._money(value)

    @staticmethod
    def _market_serves_city(market, service_city):
        if service_city is None:
            return market.scope == Market.Scope.GENERAL
        return market.service_cities.filter(
            pk=service_city.pk,
            is_active=True,
        ).exists()


class ClientOrderCreateSerializer(OrderPreviewSerializer):
    payment_method = serializers.CharField(max_length=50)
    description = serializers.CharField(required=False, allow_blank=True)
    delivery_note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["delivery_address"] is None:
            raise serializers.ValidationError(
                {"address": "Add an address before creating an order."}
            )

        order_groups = self._order_groups(
            attrs.get("items", []),
            attrs.get("offers", []),
            attrs["service_city"],
            attrs["delivery_type"],
            attrs["delivery_price"],
        )
        unavailable_market_ids = [
            group["market"].id
            for group in order_groups.values()
            if not group["delivery_available"]
        ]
        if unavailable_market_ids:
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "Selected service city is not served by markets: "
                        f"{unavailable_market_ids}."
                    )
                }
            )
        attrs["order_groups"] = order_groups
        return attrs

    def create_orders(self):
        user = self.validated_data["user"]
        address = self.validated_data["delivery_address"]
        service_city = self.validated_data["service_city"]
        delivery_area = self.validated_data["delivery_area"]
        delivery_type = self.validated_data["delivery_type"]
        payment_method = self.validated_data["payment_method"].strip()
        description = self.validated_data.get("description", "").strip()
        delivery_note = self.validated_data.get("delivery_note", "").strip()
        orders = []

        for market_id in sorted(self.validated_data["order_groups"]):
            group = self.validated_data["order_groups"][market_id]
            order = Order.objects.create(
                user=user,
                delivery_address=address,
                service_city=service_city,
                delivery_area=delivery_area,
                delivery_type=delivery_type,
                market=group["market"],
                payment_method=payment_method,
                status=Order.Status.PENDING,
                review_status=Order.ReviewStatus.PENDING_REVIEW,
                discount=group["total_offer_discounts"],
                description=description,
                delivery_price=group["delivery_price"],
                subtotal_price=group["products_subtotal"],
                total_price=(
                    group["products_subtotal"]
                    - group["total_offer_discounts"]
                    + (group["delivery_price"] or Decimal("0.00"))
                ),
                delivery_note=delivery_note,
            )
            OrderItem.objects.bulk_create(
                OrderItem(order=order, **item)
                for item in group["items"]
            )
            OrderOffer.objects.bulk_create(
                OrderOffer(order=order, **item)
                for item in group["offers"]
            )
            from notifications.services import create_new_order_review_notification

            create_new_order_review_notification(order)
            orders.append(order)
        return orders

    def _order_groups(self, items, offers, service_city, delivery_type, delivery_price):
        groups = {}
        selected_lines_by_product = {}

        for item in items:
            variant = item["variant"]
            product = variant.product
            quantity = item["quantity"]
            subtotal = variant.price * quantity
            group = self._create_group(
                groups,
                product.market,
                service_city,
                delivery_type,
                delivery_price,
            )
            group["items"].append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "unit_price": variant.price,
                }
            )
            group["products_subtotal"] += subtotal
            selected_lines_by_product.setdefault(product.id, []).append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "subtotal": subtotal,
                }
            )

        for item in offers:
            offer = item["offer"]
            offer_groups = {}
            for product in offer.products.all():
                group = self._create_group(
                    groups,
                    product.market,
                    service_city,
                    delivery_type,
                    delivery_price,
                )
                offer_group = offer_groups.setdefault(
                    product.market_id,
                    {
                        "group": group,
                        "offer_products_subtotal": Decimal("0.00"),
                    },
                )
                selected_lines = selected_lines_by_product.get(product.id, [])
                if selected_lines:
                    offer_group["offer_products_subtotal"] += sum(
                        line["subtotal"] for line in selected_lines
                    )
                    continue

                variant = product.variants.order_by("id").first()
                if variant is None:
                    continue
                offer_group["offer_products_subtotal"] += variant.price
                group["products_subtotal"] += variant.price
                group["items"].append(
                    {
                        "variant": variant,
                        "quantity": 1,
                        "unit_price": variant.price,
                    }
                )

            for offer_group in offer_groups.values():
                discount_amount = self._percentage_amount(
                    offer_group["offer_products_subtotal"],
                    offer.discount,
                )
                group = offer_group["group"]
                group["total_offer_discounts"] += discount_amount
                group["offers"].append(
                    {
                        "offer": offer,
                        "discount_amount": discount_amount,
                    }
                )

        return groups

    def _create_group(
        self,
        groups,
        market,
        service_city,
        delivery_type,
        delivery_price,
    ):
        if market.id not in groups:
            delivery_available = self._market_serves_city(market, service_city)
            groups[market.id] = {
                "market": market,
                "delivery_available": delivery_available,
                "delivery_price": (
                    delivery_price
                    if delivery_available
                    and delivery_type == Order.DeliveryType.FIXED_AREA
                    else None
                ),
                "items": [],
                "offers": [],
                "products_subtotal": Decimal("0.00"),
                "total_offer_discounts": Decimal("0.00"),
            }
        return groups[market.id]


class OrderItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product"),
        source="variant",
    )

    class Meta:
        model = OrderItem
        fields = ("id", "variant_id", "quantity", "unit_price")
        read_only_fields = ("id",)


class OrderOfferSerializer(serializers.ModelSerializer):
    offer_id = serializers.PrimaryKeyRelatedField(
        queryset=Offer.objects.all(),
        source="offer",
    )

    class Meta:
        model = OrderOffer
        fields = ("id", "offer_id", "discount_amount", "created_at")
        read_only_fields = ("id", "created_at")


class AdminOrderItemCreateSerializer(serializers.ModelSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product"),
        source="variant",
    )
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )

    class Meta:
        model = OrderItem
        fields = ("id", "variant_id", "quantity", "unit_price")
        read_only_fields = ("id",)


class AdminOrderOfferCreateSerializer(serializers.ModelSerializer):
    offer_id = serializers.PrimaryKeyRelatedField(
        queryset=Offer.objects.all(),
        source="offer",
    )
    discount_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )

    class Meta:
        model = OrderOffer
        fields = ("id", "offer_id", "discount_amount", "created_at")
        read_only_fields = ("id", "created_at")


def user_summary(user):
    full_name = user.get_full_name().strip()
    return {
        "id": user.id,
        "name": full_name or user.username,
        "phone": user.phone,
    }


class OrderSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.CLIENT),
        source="user",
    )
    delivery_address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.select_related(
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
        ).all(),
        source="delivery_address",
        required=False,
        allow_null=True,
    )
    assigned_representative_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            role=User.Role.REPRESENTATIVE,
            is_active=True,
            deleted_at__isnull=True,
        ),
        source="assigned_representative",
        required=False,
        allow_null=True,
    )
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.prefetch_related("service_cities").all(),
        source="market",
    )
    service_city_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        source="service_city",
        required=False,
        allow_null=True,
    )
    delivery_area_id = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryArea.objects.select_related("service_city").all(),
        source="delivery_area",
        required=False,
        allow_null=True,
    )
    customer = serializers.SerializerMethodField()
    market = MarketSummarySerializer(read_only=True)
    service_city = ServiceCitySummarySerializer(read_only=True)
    delivery_area = DeliveryAreaSummarySerializer(read_only=True)
    delivery_address = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, required=False)
    offers = OrderOfferSerializer(
        source="order_offers",
        many=True,
        required=False,
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "user_id",
            "customer",
            "delivery_address_id",
            "delivery_address",
            "assigned_representative_id",
            "market_id",
            "market",
            "service_city_id",
            "service_city",
            "delivery_area_id",
            "delivery_area",
            "delivery_type",
            "payment_method",
            "discount",
            "description",
            "status",
            "review_status",
            "delivery_price",
            "subtotal_price",
            "total_price",
            "image",
            "assigned_at",
            "delivered_at",
            "delivery_note",
            "delivery_proof",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "items",
            "offers",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "review_status",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        )

    def get_customer(self, instance):
        return user_summary(instance.user)

    def get_delivery_address(self, instance):
        address = instance.delivery_address
        if address is None:
            return None
        return {
            "id": address.id,
            "name": address.name,
            "details": address.details,
            "latitude": address.latitude,
            "longitude": address.longitude,
            "manual_city": address.manual_city,
            "manual_area": address.manual_area,
            "service_city": (
                ServiceCitySummarySerializer(address.service_city).data
                if address.service_city_id
                else None
            ),
            "delivery_area": (
                DeliveryAreaSummarySerializer(address.delivery_area).data
                if address.delivery_area_id
                else None
            ),
            "delivery_type": address.delivery_type,
            "delivery_price_preview": (
                f"{address.delivery_area.delivery_price:.2f}"
                if address.delivery_type == Address.DeliveryType.FIXED_AREA
                and address.delivery_area_id
                else None
            ),
        }

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        address = attrs.get(
            "delivery_address",
            getattr(self.instance, "delivery_address", None),
        )
        market = attrs.get("market", getattr(self.instance, "market", None))
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        representative = attrs.get(
            "assigned_representative",
            getattr(self.instance, "assigned_representative", None),
        )
        items = attrs.get("items")
        offers = attrs.get("order_offers")

        if address and user and address.user_id != user.id:
            raise serializers.ValidationError(
                {"delivery_address_id": "Address does not belong to the order user."}
            )
        if service_city is None and address is not None and address.service_city_id:
            service_city = address.service_city
            attrs["service_city"] = service_city
        if (
            service_city is None
            and market is not None
            and not (
                address is not None
                and address.service_city_id is None
                and address.manual_city
                and address.manual_area
            )
        ):
            service_city = market.service_cities.filter(is_active=True).first()
            if service_city is not None:
                attrs["service_city"] = service_city
        if service_city is None and (
            market is None or market.scope != Market.Scope.GENERAL
        ):
            raise serializers.ValidationError(
                {"service_city_id": "Service city is required."}
            )
        if service_city is not None and not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        if (
            address is not None
            and address.service_city_id
            and address.service_city_id != service_city.id
        ):
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "Service city must match the delivery address service city."
                    )
                }
            )
        if self.instance is None or any(
            field in attrs
            for field in (
                "delivery_address",
                "service_city",
                "delivery_area",
                "delivery_type",
                "delivery_price",
            )
        ):
            self._normalize_delivery_fields(attrs, address, service_city)
        if (
            market
            and service_city is not None
            and not market.service_cities.filter(pk=service_city.pk).exists()
        ):
            raise serializers.ValidationError(
                {"service_city_id": "Market does not serve this service city."}
            )
        if market and service_city is None and market.scope != Market.Scope.GENERAL:
            raise serializers.ValidationError(
                {"service_city_id": "Market does not support General manual delivery."}
            )
        if items is not None and market:
            if any(item["variant"].product.market_id != market.id for item in items):
                raise serializers.ValidationError(
                    {"items": "All item variants must belong to the order market."}
                )
        if offers is not None and market:
            if any(item["offer"].market_id != market.id for item in offers):
                raise serializers.ValidationError(
                    {"offers": "All offers must belong to the order market."}
                )
        if "assigned_representative" in attrs:
            if representative:
                review_status = attrs.get(
                    "review_status",
                    getattr(
                        self.instance,
                        "review_status",
                        Order.ReviewStatus.PENDING_REVIEW,
                    ),
                )
                if review_status != Order.ReviewStatus.APPROVED:
                    raise serializers.ValidationError(
                        {"assigned_representative_id": "Order must be approved before assignment."}
                    )
                profile = getattr(representative, "courier_profile", None)
                if profile is None:
                    raise serializers.ValidationError(
                        {"assigned_representative_id": "Representative must have a courier profile."}
                    )
                if service_city is None:
                    raise serializers.ValidationError(
                        {"assigned_representative_id": "General manual orders cannot be assigned by service city."}
                    )
                if profile.service_city_id != service_city.id:
                    raise serializers.ValidationError(
                        {
                            "assigned_representative_id": (
                                "هذا المندوب لا يعمل في نفس مدينة الطلب."
                            )
                        }
                    )
                attrs["status"] = Order.Status.READY
                if not attrs.get("assigned_at"):
                    attrs["assigned_at"] = timezone.now()
            else:
                attrs["assigned_at"] = None
                if self.instance and self.instance.assigned_representative_id:
                    attrs["status"] = Order.Status.PENDING
        return attrs

    def _normalize_delivery_fields(self, attrs, address, service_city):
        if address is not None:
            if (
                address.delivery_type == Address.DeliveryType.FIXED_AREA
                and address.delivery_area_id
            ):
                delivery_area = address.delivery_area
                if not delivery_area.is_active:
                    raise serializers.ValidationError(
                        {"delivery_area_id": "Delivery area must be active."}
                    )
                if delivery_area.service_city_id != service_city.id:
                    raise serializers.ValidationError(
                        {
                            "delivery_area_id": (
                                "Delivery area must belong to the service city."
                            )
                        }
                    )
                attrs["delivery_area"] = delivery_area
                attrs["delivery_type"] = Order.DeliveryType.FIXED_AREA
                attrs["delivery_price"] = delivery_area.delivery_price
                return

            attrs["delivery_area"] = None
            attrs["delivery_type"] = Order.DeliveryType.DELIVERY
            attrs["delivery_price"] = None
            return

        delivery_area = attrs.get(
            "delivery_area",
            getattr(self.instance, "delivery_area", None),
        )
        delivery_type = attrs.get(
            "delivery_type",
            getattr(self.instance, "delivery_type", Order.DeliveryType.DELIVERY),
        )
        if delivery_area is not None:
            if service_city is None:
                raise serializers.ValidationError(
                    {"service_city_id": "Service city is required for fixed-area delivery."}
                )
            if not delivery_area.is_active:
                raise serializers.ValidationError(
                    {"delivery_area_id": "Delivery area must be active."}
                )
            if delivery_area.service_city_id != service_city.id:
                raise serializers.ValidationError(
                    {
                        "delivery_area_id": (
                            "Delivery area must belong to the service city."
                        )
                    }
                )
            attrs["delivery_area"] = delivery_area
            attrs["delivery_type"] = Order.DeliveryType.FIXED_AREA
            attrs["delivery_price"] = delivery_area.delivery_price
            return

        if delivery_type == Order.DeliveryType.FIXED_AREA:
            raise serializers.ValidationError(
                {"delivery_area_id": "Delivery area is required for fixed-area delivery."}
            )
        attrs["delivery_area"] = None
        attrs["delivery_type"] = Order.DeliveryType.DELIVERY
        attrs["delivery_price"] = None

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        offers = validated_data.pop("order_offers", [])
        order = Order.objects.create(**validated_data)
        self._replace_items(order, items)
        self._replace_offers(order, offers)
        return order

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        offers = validated_data.pop("order_offers", None)
        instance = super().update(instance, validated_data)
        if items is not None:
            instance.items.all().delete()
            self._replace_items(instance, items)
        if offers is not None:
            instance.order_offers.all().delete()
            self._replace_offers(instance, offers)
        return instance

    @staticmethod
    def _replace_items(order, items):
        OrderItem.objects.bulk_create(
            OrderItem(order=order, **item) for item in items
        )

    @staticmethod
    def _replace_offers(order, offers):
        OrderOffer.objects.bulk_create(
            OrderOffer(order=order, **item) for item in offers
        )


class AdminOrderCreateSerializer(OrderSerializer):
    SYSTEM_CONTROLLED_CREATE_FIELDS = {
        "assigned_representative_id",
        "assigned_at",
        "delivered_at",
        "delivery_area_id",
        "delivery_type",
        "delivery_price",
        "discount",
        "subtotal_price",
        "total_price",
        "image",
        "delivery_proof",
        "status",
        "review_status",
        "approved_by",
        "approved_at",
        "rejected_by",
        "rejected_at",
        "rejection_reason",
    }

    items = AdminOrderItemCreateSerializer(many=True, required=True)
    offers = AdminOrderOfferCreateSerializer(
        source="order_offers",
        many=True,
        required=False,
    )

    def get_fields(self):
        fields = super().get_fields()
        for field_name in self.SYSTEM_CONTROLLED_CREATE_FIELDS:
            if field_name in fields:
                fields[field_name].read_only = True
                fields[field_name].required = False
        return fields

    def validate_payment_method(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Payment method is required.")
        return value

    def validate(self, attrs):
        errors = {
            field: "This field is controlled by the system on create."
            for field in sorted(self.SYSTEM_CONTROLLED_CREATE_FIELDS)
            if field in self.initial_data
        }
        if "delivery_address" not in attrs or attrs["delivery_address"] is None:
            errors["delivery_address_id"] = "Delivery address is required."
        if errors:
            raise serializers.ValidationError(errors)

        attrs = super().validate(attrs)
        if not attrs.get("items"):
            raise serializers.ValidationError(
                {"items": "Choose at least one product variant."}
            )
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        offers = validated_data.pop("order_offers", [])
        subtotal = sum(
            item["unit_price"] * item["quantity"]
            for item in items
        )
        discount = sum(
            item.get("discount_amount", Decimal("0.00"))
            for item in offers
        )
        delivery_price = validated_data.get("delivery_price")
        delivery_total = delivery_price or Decimal("0.00")
        total = subtotal + delivery_total - discount

        validated_data.update(
            {
                "assigned_representative": None,
                "assigned_at": None,
                "delivered_at": None,
                "status": Order.Status.PENDING,
                "review_status": Order.ReviewStatus.PENDING_REVIEW,
                "discount": discount,
                "subtotal_price": subtotal,
                "total_price": max(total, Decimal("0.00")),
            }
        )

        order = Order.objects.create(**validated_data)
        self._replace_items(order, items)
        self._replace_offers(order, offers)
        return order


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class OrderAssignmentSerializer(serializers.Serializer):
    representative_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            role=User.Role.REPRESENTATIVE,
            is_active=True,
            deleted_at__isnull=True,
        ),
        source="representative",
    )


class RepresentativeSummarySerializer(serializers.ModelSerializer):
    representative_id = serializers.IntegerField(source="id", read_only=True)
    user_id = serializers.IntegerField(source="id", read_only=True)
    name = serializers.SerializerMethodField()
    service_city_id = serializers.IntegerField(
        source="courier_profile.service_city_id",
        read_only=True,
    )
    service_city = serializers.CharField(
        source="courier_profile.service_city.name",
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            "representative_id",
            "user_id",
            "name",
            "phone",
            "service_city_id",
            "service_city",
        )

    def get_name(self, instance):
        return user_summary(instance)["name"]


class OrderReviewActionSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


class CourierOrderItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    variant = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ("id", "quantity", "unit_price", "product", "variant")

    def get_product(self, instance):
        product = instance.variant.product
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "image": self._image_url(product.image),
        }

    def get_variant(self, instance):
        variant = instance.variant
        return {
            "id": variant.id,
            "sku": variant.sku,
            "price": variant.price,
        }

    def _image_url(self, image):
        if not image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(image.url) if request else image.url


class CourierOrderOfferSerializer(serializers.ModelSerializer):
    offer = serializers.SerializerMethodField()

    class Meta:
        model = OrderOffer
        fields = ("id", "offer", "discount_amount", "created_at")

    def get_offer(self, instance):
        offer = instance.offer
        return {
            "id": offer.id,
            "title": offer.title,
            "description": offer.description,
            "type": offer.type,
            "discount": offer.discount,
        }


class CourierOrderListSerializer(serializers.ModelSerializer):
    service_city = ServiceCitySummarySerializer(read_only=True)
    delivery_area = DeliveryAreaSummarySerializer(read_only=True)
    market = MarketSummarySerializer(read_only=True)
    customer = serializers.SerializerMethodField()
    delivery_address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "service_city",
            "delivery_area",
            "delivery_type",
            "market",
            "customer",
            "delivery_address",
            "total_price",
            "delivery_price",
            "created_at",
            "assigned_at",
        )

    def get_customer(self, instance):
        return user_summary(instance.user)

    def get_delivery_address(self, instance):
        if instance.delivery_address is None:
            return None
        return {
            "id": instance.delivery_address.id,
            "name": instance.delivery_address.name,
            "details": instance.delivery_address.details,
            "delivery_area": (
                DeliveryAreaSummarySerializer(
                    instance.delivery_address.delivery_area
                ).data
                if instance.delivery_address.delivery_area_id
                else None
            ),
            "delivery_type": instance.delivery_address.delivery_type,
        }


class CourierOrderDetailSerializer(CourierOrderListSerializer):
    items = CourierOrderItemSerializer(many=True, read_only=True)
    offers = CourierOrderOfferSerializer(
        source="order_offers",
        many=True,
        read_only=True,
    )

    class Meta(CourierOrderListSerializer.Meta):
        fields = CourierOrderListSerializer.Meta.fields + (
            "items",
            "offers",
            "subtotal_price",
            "discount",
            "delivery_note",
            "delivery_proof",
            "delivered_at",
        )


class CourierOrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            (Order.Status.PICKED_UP, Order.Status.PICKED_UP.label),
            (Order.Status.ON_THE_WAY, Order.Status.ON_THE_WAY.label),
            (Order.Status.DELIVERED, Order.Status.DELIVERED.label),
            (Order.Status.FAILED_DELIVERY, Order.Status.FAILED_DELIVERY.label),
        )
    )
