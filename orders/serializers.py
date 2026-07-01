from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from catalog.models import ProductVariant
from locations.models import Address
from markets.models import Market
from offers.models import Offer

from .models import Order, OrderItem, OrderOffer

User = get_user_model()


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
        queryset=Offer.objects.select_related("market").prefetch_related(
            "products__variants"
        ),
        source="offer",
    )


class OrderPreviewAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "name",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
        )


class OrderPreviewSerializer(serializers.Serializer):
    items = OrderPreviewItemSerializer(many=True, required=False)
    offers = OrderPreviewOfferSerializer(many=True, required=False)

    def validate(self, attrs):
        user = self.context["request"].user
        address = self._default_address(user)
        items = attrs.get("items", [])
        offers = attrs.get("offers", [])

        if not items and not offers:
            raise serializers.ValidationError(
                {"items": "Choose at least one product variant or offer."}
            )

        attrs["user"] = user
        attrs["delivery_address"] = address
        return attrs

    def preview_data(self):
        user = self.validated_data["user"]
        address = self.validated_data.get("delivery_address")
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
            group = self._market_group(market_groups, offer.market)
            offer_products, offer_products_subtotal, added_products_subtotal = (
                self._offer_product_rows(offer, selected_lines_by_product)
            )
            group["products_subtotal"] += added_products_subtotal
            discount_amount = self._percentage_amount(
                offer_products_subtotal,
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
                        offer_products_subtotal
                    ),
                    "discount_amount": self._money(discount_amount),
                    "products": offer_products,
                }
            )

        market_groups_data = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        delivery_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for market_id in sorted(market_groups):
            group = market_groups[market_id]
            delivery_area = (
                self._delivery_area_for_address(group["market"], address)
                if address is not None
                else None
            )
            delivery_price = (
                delivery_area.delivery_price
                if delivery_area is not None
                else Decimal("0.00")
            )
            market_total = (
                group["products_subtotal"]
                - group["total_offer_discounts"]
                + delivery_price
            )
            subtotal += group["products_subtotal"]
            discount_total += group["total_offer_discounts"]
            delivery_total += delivery_price
            grand_total += market_total
            market_groups_data.append(
                {
                    "market": {
                        "id": group["market"].id,
                        "name": group["market"].name,
                        "branch": group["market"].branch,
                    },
                    "delivery_area": (
                        {
                            "id": delivery_area.id,
                            "name": delivery_area.name,
                        }
                        if delivery_area is not None
                        else None
                    ),
                    "delivery_available": delivery_area is not None,
                    "selected_products": group["selected_products"],
                    "selected_offers": group["selected_offers"],
                    "pricing": {
                        "products_subtotal": self._money(
                            group["products_subtotal"]
                        ),
                        "total_offer_discounts": self._money(
                            group["total_offer_discounts"]
                        ),
                        "delivery_price": self._money(delivery_price),
                        "market_total": self._money(market_total),
                    },
                }
            )

        addresses = user.addresses.order_by("-is_default", "-created_at")
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
            "market_groups": market_groups_data,
            "summary": {
                "subtotal": self._money(subtotal),
                "discount_total": self._money(discount_total),
                "delivery_total": self._money(delivery_total),
                "grand_total": self._money(grand_total),
            },
        }

    @staticmethod
    def _default_address(user):
        return (
            user.addresses.filter(is_default=True).order_by("-created_at").first()
            or user.addresses.order_by("-created_at").first()
        )

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

    def _offer_product_rows(self, offer, selected_lines_by_product):
        rows = []
        offer_products_subtotal = Decimal("0.00")
        added_products_subtotal = Decimal("0.00")

        for product in offer.products.all():
            selected_lines = selected_lines_by_product.get(product.id, [])
            if selected_lines:
                for selected_line in selected_lines:
                    line = selected_line["line"]
                    subtotal = selected_line["subtotal"]
                    offer_products_subtotal += subtotal
                    rows.append(
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
                rows.append(
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
            offer_products_subtotal += subtotal
            added_products_subtotal += subtotal
            rows.append(
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

        return rows, offer_products_subtotal, added_products_subtotal

    @staticmethod
    def _money(value):
        return f"{value:.2f}"

    @staticmethod
    def _delivery_area_for_address(market, address):
        from markets.services import _distance_km

        latitude = float(address.latitude)
        longitude = float(address.longitude)
        matching_areas = [
            area
            for area in market.delivery_areas.filter(is_active=True).order_by("id")
            if _distance_km(
                latitude,
                longitude,
                float(area.center_latitude),
                float(area.center_longitude),
            )
            <= float(area.radius_km)
        ]
        if not matching_areas:
            return None
        return min(
            matching_areas,
            key=lambda area: _distance_km(
                latitude,
                longitude,
                float(area.center_latitude),
                float(area.center_longitude),
            ),
        )


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
            attrs["delivery_address"],
        )
        unavailable_market_ids = [
            group["market"].id
            for group in order_groups.values()
            if group["delivery_area"] is None
        ]
        if unavailable_market_ids:
            raise serializers.ValidationError(
                {
                    "address": (
                        "Selected address is outside the delivery area for "
                        f"markets: {unavailable_market_ids}."
                    )
                }
            )
        attrs["order_groups"] = order_groups
        return attrs

    def create_orders(self):
        user = self.validated_data["user"]
        address = self.validated_data["delivery_address"]
        payment_method = self.validated_data["payment_method"].strip()
        description = self.validated_data.get("description", "").strip()
        delivery_note = self.validated_data.get("delivery_note", "").strip()
        orders = []

        for market_id in sorted(self.validated_data["order_groups"]):
            group = self.validated_data["order_groups"][market_id]
            order = Order.objects.create(
                user=user,
                delivery_address=address,
                market=group["market"],
                payment_method=payment_method,
                discount=group["total_offer_discounts"],
                description=description,
                delivery_price=group["delivery_price"],
                subtotal_price=group["products_subtotal"],
                total_price=(
                    group["products_subtotal"]
                    - group["total_offer_discounts"]
                    + group["delivery_price"]
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
            orders.append(order)
        return orders

    def _order_groups(self, items, offers, address):
        groups = {}
        selected_lines_by_product = {}

        for item in items:
            variant = item["variant"]
            product = variant.product
            quantity = item["quantity"]
            subtotal = variant.price * quantity
            group = self._create_group(groups, product.market, address)
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
            group = self._create_group(groups, offer.market, address)
            offer_products_subtotal = Decimal("0.00")
            for product in offer.products.all():
                selected_lines = selected_lines_by_product.get(product.id, [])
                if selected_lines:
                    offer_products_subtotal += sum(
                        line["subtotal"] for line in selected_lines
                    )
                    continue

                variant = product.variants.order_by("id").first()
                if variant is None:
                    continue
                offer_products_subtotal += variant.price
                group["products_subtotal"] += variant.price
                group["items"].append(
                    {
                        "variant": variant,
                        "quantity": 1,
                        "unit_price": variant.price,
                    }
                )

            discount_amount = self._percentage_amount(
                offer_products_subtotal,
                offer.discount,
            )
            group["total_offer_discounts"] += discount_amount
            group["offers"].append(
                {
                    "offer": offer,
                    "discount_amount": discount_amount,
                }
            )

        return groups

    def _create_group(self, groups, market, address):
        if market.id not in groups:
            delivery_area = self._delivery_area_for_address(market, address)
            groups[market.id] = {
                "market": market,
                "delivery_area": delivery_area,
                "delivery_price": (
                    delivery_area.delivery_price
                    if delivery_area is not None
                    else Decimal("0.00")
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


class OrderSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.CLIENT),
        source="user",
    )
    delivery_address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
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
        queryset=Market.objects.all(),
        source="market",
    )
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
            "delivery_address_id",
            "assigned_representative_id",
            "market_id",
            "payment_method",
            "discount",
            "description",
            "status",
            "delivery_price",
            "subtotal_price",
            "total_price",
            "image",
            "assigned_at",
            "delivered_at",
            "delivery_note",
            "delivery_proof",
            "items",
            "offers",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        address = attrs.get(
            "delivery_address",
            getattr(self.instance, "delivery_address", None),
        )
        market = attrs.get("market", getattr(self.instance, "market", None))
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
                attrs["status"] = Order.Status.READY
                if not attrs.get("assigned_at"):
                    attrs["assigned_at"] = timezone.now()
            else:
                attrs["assigned_at"] = None
                if self.instance and self.instance.assigned_representative_id:
                    attrs["status"] = Order.Status.PENDING
        return attrs

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
        allow_null=True,
    )
