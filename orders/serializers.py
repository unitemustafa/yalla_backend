from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from catalog.models import ProductVariant
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market
from markets.region import (
    GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE,
    MIXED_MARKET_SCOPE_MESSAGE,
    MIXED_SERVICE_CITY_MARKETS_MESSAGE,
    SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE,
    address_matches_market_region,
    current_market_region_selection,
    order_region_validation_error,
    visible_offer_queryset,
)
from offers.models import Offer

from .models import Order, OrderEvent, OrderItem, OrderMarketSection, OrderOffer
from .services import allowed_statuses_for_order

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
        ).prefetch_related(
            "service_cities",
            "products__variants",
            "products__market__service_cities",
            "items__variant__product__market__service_cities",
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
    DELIVERY_AREA_UNAVAILABLE_MESSAGE = (
        "Delivery is no longer available for this address. Choose another address."
    )

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
        user = self.context.get("preview_user") or self.context["request"].user
        has_explicit_address = "delivery_address" in attrs
        items = attrs.get("items", [])
        offers = attrs.get("offers", [])

        if not items and not offers:
            raise serializers.ValidationError(
                {"items": "Choose at least one product variant or offer."}
            )

        if any(item["offer"].type == Offer.OfferType.ANNOUNCEMENT for item in offers):
            raise serializers.ValidationError(
                {"offers": "Announcements are external links and cannot be added to an order."}
            )

        region_error = order_region_validation_error(
            user,
            [item["variant"] for item in items],
            [item["offer"] for item in offers],
        )
        if region_error:
            raise serializers.ValidationError(region_error)

        available_offer_ids = set(
            visible_offer_queryset(user).filter(
                id__in=[item["offer"].id for item in offers]
            ).values_list("id", flat=True)
        )
        unavailable_offer_ids = [
            item["offer"].id
            for item in offers
            if item["offer"].id not in available_offer_ids
        ]
        if unavailable_offer_ids:
            raise serializers.ValidationError(
                {"offers": "One or more offers are no longer available."}
            )

        current_selection = current_market_region_selection(user)
        address = attrs.get("delivery_address")
        if address is not None and address.user_id != user.id:
            raise serializers.ValidationError(
                {"address_id": "Address does not belong to the authenticated user."}
            )
        if address is not None and not self._address_is_allowed_for_scope(
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

        order_scope = current_selection["mode"]
        request_service_city = attrs.get("service_city")
        service_city = self._service_city_for_order(
            user,
            current_selection,
            attrs.get("service_city"),
        )
        if order_scope == Order.Scope.GENERAL and request_service_city is not None:
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "يجب ترك مدينة الخدمة فارغة لطلبات السوق العام."
                    )
                }
            )
        if order_scope == Order.Scope.SERVICE_CITY and service_city is None:
            raise serializers.ValidationError(
                {"service_city_id": "Service city is required."}
            )
        if service_city is not None and not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        delivery_context = self._delivery_context(
            address,
            order_scope,
            service_city,
        )

        attrs["user"] = user
        attrs["delivery_address"] = address
        attrs["order_scope"] = order_scope
        attrs["service_city"] = service_city
        attrs["current_selection"] = current_selection
        attrs.update(delivery_context)
        return attrs

    def preview_data(self):
        user = self.validated_data["user"]
        current_selection = self.validated_data["current_selection"]
        address = self.validated_data.get("delivery_address")
        order_scope = self.validated_data["order_scope"]
        service_city = self.validated_data["service_city"]
        delivery_area = self.validated_data["delivery_area"]
        delivery_type = self.validated_data["delivery_type"]
        fixed_delivery_price = self.validated_data["delivery_price"]
        delivery_message = self.validated_data["delivery_message"]
        items = self.validated_data.get("items", [])
        offers = self.validated_data.get("offers", [])
        has_free_delivery = self._has_free_delivery_offer(offers)
        market_groups = {}
        selected_lines_by_variant = {}

        for item in items:
            variant = item["variant"]
            product = variant.product
            quantity = item["quantity"]
            unit_price = self._product_unit_price(variant)
            subtotal = unit_price * quantity
            group = self._market_group(market_groups, product.market)
            line = {
                "variant_id": variant.id,
                "product_id": product.id,
                "product_name": product.name,
                "image": self._image_url(product.image),
                "quantity": quantity,
                "unit_price": self._money(unit_price),
                "subtotal": self._money(subtotal),
            }
            group["selected_products"].append(line)
            group["products_subtotal"] += subtotal
            selected_lines_by_variant.setdefault(variant.id, []).append(
                {
                    "line": line,
                    "subtotal": subtotal,
                }
            )

        for item in offers:
            offer = item["offer"]
            for offer_group in self._offer_product_rows_by_market(
                offer,
                selected_lines_by_variant,
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

        fixed_delivery_applied = False
        for market_id in sorted(market_groups):
            group = market_groups[market_id]
            delivery_available = self._market_serves_city(
                group["market"],
                service_city,
                order_scope,
            )
            if delivery_available and has_free_delivery and not fixed_delivery_applied:
                delivery_price = Decimal("0.00")
            else:
                delivery_price = (
                    fixed_delivery_price
                    if delivery_available
                    and delivery_type == Order.DeliveryType.FIXED_AREA
                    and not fixed_delivery_applied
                    else None
                )
            if delivery_price is not None:
                fixed_delivery_applied = True
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
            if self._address_is_allowed_for_scope(
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
            "order_scope": order_scope,
            "is_multi_market": len(market_groups_data) > 1,
            "market_count": len(market_groups_data),
            "market_names_summary": ", ".join(
                group["market"]["name"] for group in market_groups_data
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
    def _default_address(user, current_selection):
        addresses = (
            user.addresses.select_related(
                "service_city",
                "delivery_area",
                "delivery_area__service_city",
            )
            .filter(is_active=True)
            .order_by("-is_default", "-created_at")
        )
        for address in addresses:
            if OrderPreviewSerializer._address_is_allowed_for_scope(
                address,
                current_selection,
            ):
                return address
        return None

    @classmethod
    def _address_region_mismatch_error(cls):
        return {
            "address_id": cls.ADDRESS_REGION_MISMATCH_MESSAGE,
            "code": cls.ADDRESS_REGION_MISMATCH_CODE,
        }

    @staticmethod
    def _service_city_for_order(user, current_selection, request_service_city):
        if current_selection["mode"] == User.MarketRegionMode.GENERAL:
            return None

        selected_city = getattr(user, "market_region_service_city", None)
        if request_service_city is None:
            return selected_city
        if selected_city is None or request_service_city.id != selected_city.id:
            raise serializers.ValidationError(
                {
                    "service_city_id": (
                        "يجب أن تطابق مدينة الخدمة نطاق السوق المختار."
                    )
                }
            )
        return request_service_city

    @staticmethod
    def _address_is_allowed_for_scope(address, current_selection):
        return address_matches_market_region(address, current_selection)

    @staticmethod
    def _service_city_data(service_city):
        if service_city is None:
            return None
        return ServiceCitySummarySerializer(service_city).data

    def _delivery_context(self, address, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            return {
                "delivery_area": None,
                "delivery_type": Order.DeliveryType.DELIVERY,
                "delivery_price": None,
                "delivery_message": self.DELIVERY_MESSAGE,
            }

        if (
            order_scope == Order.Scope.SERVICE_CITY
            and address is not None
            and address.delivery_type == Address.DeliveryType.FIXED_AREA
            and address.delivery_area_id
        ):
            delivery_area = address.delivery_area
            if not delivery_area.is_active:
                raise serializers.ValidationError(
                    {"address_id": self.DELIVERY_AREA_UNAVAILABLE_MESSAGE}
                )
            if (
                service_city is not None
                and delivery_area.service_city_id == service_city.id
            ):
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

    @staticmethod
    def _has_free_delivery_offer(offers):
        return any(
            item["offer"].type == Offer.OfferType.DELIVERY
            for item in offers
        )

    @classmethod
    def _product_unit_price(cls, variant, *, apply_product_discount=True):
        if not apply_product_discount:
            return variant.price
        discount = variant.product.discount or Decimal("0.00")
        discount_amount = cls._percentage_amount(variant.price, discount)
        return max(variant.price - discount_amount, Decimal("0.00"))

    @staticmethod
    def _offer_variant_rows(offer):
        offer_items = list(offer.items.all())
        if offer_items:
            return [
                (
                    item.variant,
                    item.quantity,
                    item.apply_product_discount,
                )
                for item in offer_items
            ]

        rows = []
        for product in offer.products.all():
            variant = product.variants.order_by("id").first()
            if variant is not None:
                rows.append((variant, 1, True))
        return rows

    def _image_url(self, image):
        if not image:
            return None
        request = self.context.get("request")
        url = image.url
        return request.build_absolute_uri(url) if request is not None else url

    def _offer_product_rows_by_market(self, offer, selected_lines_by_variant):
        groups = {}

        for (
            variant,
            offer_quantity,
            apply_product_discount,
        ) in self._offer_variant_rows(offer):
            product = variant.product
            group = groups.setdefault(
                product.market_id,
                {
                    "market": product.market,
                    "products": [],
                    "offer_products_subtotal": Decimal("0.00"),
                    "added_products_subtotal": Decimal("0.00"),
                },
            )
            selected_lines = selected_lines_by_variant.get(variant.id, [])
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
                            "apply_product_discount": apply_product_discount,
                            "product_discount_percentage": self._money(
                                product.discount or Decimal("0.00")
                            ),
                        }
                    )
                continue

            unit_price = self._product_unit_price(
                variant,
                apply_product_discount=apply_product_discount,
            )
            subtotal = unit_price * offer_quantity
            group["offer_products_subtotal"] += subtotal
            group["added_products_subtotal"] += subtotal
            group["products"].append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "image": self._image_url(product.image),
                    "variant_id": variant.id,
                    "quantity": offer_quantity,
                    "unit_price": self._money(unit_price),
                    "subtotal": self._money(subtotal),
                    "is_selected": False,
                    "apply_product_discount": apply_product_discount,
                    "product_discount_percentage": self._money(
                        product.discount or Decimal("0.00")
                    ),
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
    def _market_serves_city(market, service_city, order_scope=None):
        if order_scope == Order.Scope.GENERAL or service_city is None:
            return market.scope == Market.Scope.GENERAL
        return (
            market.scope == Market.Scope.SERVICE_CITY
            and market.service_cities.filter(
                pk=service_city.pk,
                is_active=True,
            ).exists()
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
            attrs["order_scope"],
            attrs["service_city"],
            attrs["delivery_type"],
            attrs["delivery_price"],
        )
        if not order_groups:
            raise serializers.ValidationError(
                {"items": "Choose at least one product variant or valid offer."}
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
        order_scope = self.validated_data["order_scope"]
        service_city = self.validated_data["service_city"]
        delivery_area = self.validated_data["delivery_area"]
        delivery_type = self.validated_data["delivery_type"]
        delivery_price = self.validated_data["delivery_price"]
        has_free_delivery = self._has_free_delivery_offer(
            self.validated_data.get("offers", [])
        )
        payment_method = self.validated_data["payment_method"].strip()
        description = self.validated_data.get("description", "").strip()
        delivery_note = self.validated_data.get("delivery_note", "").strip()
        order_groups = self.validated_data["order_groups"]
        sorted_market_ids = sorted(order_groups)
        subtotal = sum(
            (order_groups[market_id]["products_subtotal"] for market_id in sorted_market_ids),
            Decimal("0.00"),
        )
        discount = sum(
            (
                order_groups[market_id]["total_offer_discounts"]
                for market_id in sorted_market_ids
            ),
            Decimal("0.00"),
        )
        parent_delivery_price = (
            Decimal("0.00")
            if has_free_delivery
            else delivery_price
            if delivery_type == Order.DeliveryType.FIXED_AREA
            else None
        )
        total = subtotal - discount + (parent_delivery_price or Decimal("0.00"))
        first_group = order_groups[sorted_market_ids[0]]

        order = Order.objects.create(
            user=user,
            delivery_address=address,
            order_scope=order_scope,
            service_city=service_city,
            delivery_area=delivery_area,
            delivery_type=delivery_type,
            market=first_group["market"],
            payment_method=payment_method,
            status=Order.Status.PENDING,
            review_status=Order.ReviewStatus.PENDING_REVIEW,
            discount=discount,
            description=description,
            delivery_price=parent_delivery_price,
            subtotal_price=subtotal,
            total_price=max(total, Decimal("0.00")),
            delivery_note=delivery_note,
        )
        for sort_order, market_id in enumerate(sorted_market_ids):
            group = order_groups[market_id]
            section = OrderMarketSection.objects.create(
                order=order,
                market=group["market"],
                subtotal_price=group["products_subtotal"],
                discount=group["total_offer_discounts"],
                sort_order=sort_order,
            )
            OrderItem.objects.bulk_create(
                OrderItem(order=order, section=section, **item)
                for item in group["items"]
            )
            OrderOffer.objects.bulk_create(
                OrderOffer(order=order, section=section, **item)
                for item in group["offers"]
            )
        from notifications.services import create_new_order_review_notification

        create_new_order_review_notification(order)
        return [order]

    def _order_groups(
        self,
        items,
        offers,
        order_scope,
        service_city,
        delivery_type,
        delivery_price,
    ):
        groups = {}
        selected_lines_by_variant = {}

        for item in items:
            variant = item["variant"]
            product = variant.product
            quantity = item["quantity"]
            unit_price = self._product_unit_price(variant)
            subtotal = unit_price * quantity
            group = self._create_group(
                groups,
                product.market,
                order_scope,
                service_city,
                delivery_type,
                delivery_price,
            )
            group["items"].append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            )
            group["products_subtotal"] += subtotal
            selected_lines_by_variant.setdefault(variant.id, []).append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "subtotal": subtotal,
                }
            )

        for item in offers:
            offer = item["offer"]
            offer_groups = {}
            for (
                variant,
                offer_quantity,
                apply_product_discount,
            ) in self._offer_variant_rows(offer):
                product = variant.product
                group = self._create_group(
                    groups,
                    product.market,
                    order_scope,
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
                selected_lines = selected_lines_by_variant.get(variant.id, [])
                if selected_lines:
                    offer_group["offer_products_subtotal"] += sum(
                        line["subtotal"] for line in selected_lines
                    )
                    continue

                unit_price = self._product_unit_price(
                    variant,
                    apply_product_discount=apply_product_discount,
                )
                subtotal = unit_price * offer_quantity
                offer_group["offer_products_subtotal"] += subtotal
                group["products_subtotal"] += subtotal
                group["items"].append(
                    {
                        "variant": variant,
                        "quantity": offer_quantity,
                        "unit_price": unit_price,
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
        order_scope,
        service_city,
        delivery_type,
        delivery_price,
    ):
        if market.id not in groups:
            delivery_available = self._market_serves_city(
                market,
                service_city,
                order_scope,
            )
            groups[market.id] = {
                "market": market,
                "delivery_available": delivery_available,
                "delivery_price": None,
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
    section_id = serializers.IntegerField(read_only=True)
    product_name = serializers.SerializerMethodField()
    variant_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "section_id",
            "variant_id",
            "product_name",
            "variant_name",
            "quantity",
            "unit_price",
        )
        read_only_fields = ("id", "product_name", "variant_name")

    def get_product_name(self, instance):
        return instance.variant.product.name

    def get_variant_name(self, instance):
        values = []
        for value in instance.variant.attribute_values.all():
            attribute = (
                value.product_attribute
                if value.product_attribute_id
                else value.attribute
            )
            option = (
                value.product_attribute_option
                if value.product_attribute_option_id
                else value.option
            )
            attribute_name = getattr(attribute, "name", "")
            option_value = getattr(option, "value", "")
            if attribute_name and option_value:
                values.append(f"{attribute_name}: {option_value}")
            elif option_value:
                values.append(option_value)
        return " - ".join(values)


class OrderOfferSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ("id", "title", "type", "discount")
        read_only_fields = fields


class OrderOfferSerializer(serializers.ModelSerializer):
    offer_id = serializers.PrimaryKeyRelatedField(
        queryset=Offer.objects.all(),
        source="offer",
    )
    section_id = serializers.IntegerField(read_only=True)
    offer = OrderOfferSummarySerializer(read_only=True)

    class Meta:
        model = OrderOffer
        fields = ("id", "section_id", "offer_id", "offer", "discount_amount", "created_at")
        read_only_fields = ("id", "offer", "created_at")


class OrderMarketSectionSerializer(serializers.ModelSerializer):
    market = MarketSummarySerializer(read_only=True)
    market_id = serializers.IntegerField(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    offers = OrderOfferSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = OrderMarketSection
        fields = (
            "id",
            "market_id",
            "market",
            "subtotal_price",
            "discount",
            "total_price",
            "pickup_status",
            "picked_up_at",
            "sort_order",
            "items",
            "offers",
        )

    def get_total_price(self, instance):
        total = max(
            instance.subtotal_price - instance.discount,
            Decimal("0.00"),
        )
        return f"{total:.2f}"


class AdminOrderItemCreateSerializer(serializers.ModelSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product"),
        source="variant",
    )
    quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = OrderItem
        fields = ("id", "variant_id", "quantity")
        read_only_fields = ("id",)


class AdminOrderOfferCreateSerializer(serializers.ModelSerializer):
    offer_id = serializers.PrimaryKeyRelatedField(
        queryset=Offer.objects.all(),
        source="offer",
    )

    class Meta:
        model = OrderOffer
        fields = ("id", "offer_id", "created_at")
        read_only_fields = ("id", "created_at")


def user_summary(user):
    full_name = user.get_full_name().strip()
    return {
        "id": user.id,
        "name": full_name or user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
    }


class AssignedRepresentativeSummarySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    service_city = serializers.SerializerMethodField()
    service_city_id = serializers.IntegerField(
        source="courier_profile.service_city_id",
        read_only=True,
    )
    is_available = serializers.BooleanField(
        source="courier_profile.is_available",
        read_only=True,
    )
    vehicle_type = serializers.CharField(
        source="courier_profile.vehicle_type",
        read_only=True,
    )
    plate_number = serializers.CharField(
        source="courier_profile.plate_number",
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "name",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "avatar_url",
            "service_city_id",
            "service_city",
            "is_available",
            "vehicle_type",
            "plate_number",
        )

    def get_name(self, instance):
        return user_summary(instance)["name"]

    def get_avatar(self, instance):
        return self.get_avatar_url(instance)

    def get_avatar_url(self, instance):
        if instance.avatar_image:
            request = self.context.get("request")
            url = instance.avatar_image.url
            return request.build_absolute_uri(url) if request is not None else url
        return instance.avatar_url

    def get_service_city(self, instance):
        profile = getattr(instance, "courier_profile", None)
        service_city = getattr(profile, "service_city", None)
        if service_city is None:
            return None
        return ServiceCitySummarySerializer(service_city).data


class OrderEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = OrderEvent
        fields = (
            "id",
            "event_type",
            "from_status",
            "to_status",
            "actor",
            "note",
            "metadata",
            "created_at",
        )

    def get_actor(self, instance):
        return user_summary(instance.actor) if instance.actor_id else None


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
        source="assigned_representative",
        read_only=True,
    )
    market_id = serializers.PrimaryKeyRelatedField(
        queryset=Market.objects.prefetch_related("service_cities").all(),
        source="market",
        required=False,
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
    assigned_representative = AssignedRepresentativeSummarySerializer(read_only=True)
    market = MarketSummarySerializer(read_only=True)
    service_city = ServiceCitySummarySerializer(read_only=True)
    delivery_area = DeliveryAreaSummarySerializer(read_only=True)
    delivery_address = serializers.SerializerMethodField()
    is_multi_market = serializers.SerializerMethodField()
    market_count = serializers.SerializerMethodField()
    market_names_summary = serializers.SerializerMethodField()
    market_sections = serializers.SerializerMethodField()
    grouped_items = serializers.SerializerMethodField()
    grouped_offers = serializers.SerializerMethodField()
    pickup_stops = serializers.SerializerMethodField()
    history = OrderEventSerializer(
        source="history_events",
        many=True,
        read_only=True,
    )
    allowed_statuses = serializers.SerializerMethodField()
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
            "assigned_representative",
            "market_id",
            "market",
            "order_scope",
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
            "is_multi_market",
            "market_count",
            "market_names_summary",
            "market_sections",
            "grouped_items",
            "grouped_offers",
            "pickup_stops",
            "history",
            "allowed_statuses",
            "items",
            "offers",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "review_status",
            "assigned_representative_id",
            "assigned_at",
            "delivered_at",
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        aggregated = {}
        for row in data.get("offers", []):
            offer_id = row.get("offer_id")
            if offer_id is None:
                continue
            current = aggregated.setdefault(
                str(offer_id),
                {
                    "id": row.get("id"),
                    "offer_id": offer_id,
                    "offer": row.get("offer"),
                    "discount_amount": Decimal("0.00"),
                    "section_ids": [],
                },
            )
            current["discount_amount"] += Decimal(str(row.get("discount_amount") or "0"))
            section_id = row.get("section_id")
            if section_id is not None and section_id not in current["section_ids"]:
                current["section_ids"].append(section_id)
        for current in aggregated.values():
            current["discount_amount"] = f'{current["discount_amount"]:.2f}'
            current["market_count"] = len(current["section_ids"])
        data["offers"] = list(aggregated.values())
        return data

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

    def get_is_multi_market(self, instance):
        return self.get_market_count(instance) > 1

    def get_market_count(self, instance):
        return len(self._market_sections(instance))

    def get_market_names_summary(self, instance):
        return ", ".join(
            section.market.name for section in self._market_sections(instance)
        )

    def get_market_sections(self, instance):
        return OrderMarketSectionSerializer(
            self._market_sections(instance),
            many=True,
            context=self.context,
        ).data

    def get_grouped_items(self, instance):
        return [
            {
                "market": MarketSummarySerializer(section.market).data,
                "items": OrderItemSerializer(
                    list(section.items.all()),
                    many=True,
                    context=self.context,
                ).data,
            }
            for section in self._market_sections(instance)
        ]

    def get_grouped_offers(self, instance):
        return [
            {
                "market": MarketSummarySerializer(section.market).data,
                "offers": OrderOfferSerializer(
                    list(section.offers.all()),
                    many=True,
                    context=self.context,
                ).data,
            }
            for section in self._market_sections(instance)
        ]

    def get_pickup_stops(self, instance):
        return [
            {
                "market_id": section.market_id,
                "market": MarketSummarySerializer(section.market).data,
                "pickup_status": section.pickup_status,
                "picked_up_at": section.picked_up_at,
                "sort_order": section.sort_order,
            }
            for section in self._market_sections(instance)
        ]

    def get_allowed_statuses(self, instance):
        return allowed_statuses_for_order(instance)

    def _market_sections(self, instance):
        cache_name = "_order_serializer_market_sections"
        if hasattr(instance, cache_name):
            return getattr(instance, cache_name)
        prefetched = getattr(instance, "_prefetched_objects_cache", {})
        if "market_sections" in prefetched:
            sections = list(prefetched["market_sections"])
        else:
            sections = list(
                instance.market_sections.select_related("market")
                .prefetch_related(
                    "items__variant__product",
                    "offers__offer",
                )
                .order_by("sort_order", "id")
            )
        sections.sort(key=lambda section: (section.sort_order, section.id))
        setattr(instance, cache_name, sections)
        return sections

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
        order_scope = attrs.get(
            "order_scope",
            getattr(self.instance, "order_scope", None),
        )

        if address and user and address.user_id != user.id:
            raise serializers.ValidationError(
                {"delivery_address_id": "Address does not belong to the order user."}
            )
        if market is None:
            market = self._first_market_from_lines(items, offers)
            if market is not None:
                attrs["market"] = market
        if order_scope is None and market is not None:
            order_scope = (
                Order.Scope.GENERAL
                if market.scope == Market.Scope.GENERAL
                else Order.Scope.SERVICE_CITY
            )
            attrs["order_scope"] = order_scope
        if (
            service_city is None
            and order_scope == Order.Scope.SERVICE_CITY
            and address is not None
            and address.service_city_id
        ):
            service_city = address.service_city
            attrs["service_city"] = service_city
        if (
            service_city is None
            and order_scope == Order.Scope.SERVICE_CITY
            and market is not None
        ):
            service_city = market.service_cities.filter(is_active=True).first()
            if service_city is not None:
                attrs["service_city"] = service_city
        if order_scope == Order.Scope.GENERAL:
            service_city = None
            attrs["service_city"] = None
        if order_scope == Order.Scope.SERVICE_CITY and service_city is None:
            raise serializers.ValidationError(
                {"service_city_id": "Service city is required."}
            )
        if address is not None:
            if order_scope == Order.Scope.GENERAL and not (
                address.service_city_id is None
                and address.delivery_area_id is None
                and bool((address.manual_city or "").strip())
                and bool((address.manual_area or "").strip())
            ):
                raise serializers.ValidationError(
                    {
                        "delivery_address_id": (
                            "General orders require a manual general address."
                        )
                    }
                )
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and address.service_city_id is None
            ):
                raise serializers.ValidationError(
                    {
                        "delivery_address_id": (
                            "Delivery address must belong to the service city."
                        )
                    }
                )
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and address.service_city_id != service_city.id
            ):
                raise serializers.ValidationError(
                    {
                        "service_city_id": (
                            "Service city must match the delivery address service city."
                        )
                    }
                )
        if service_city is not None and not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city_id": "Service city must be active."}
            )
        if (
            order_scope == Order.Scope.SERVICE_CITY
            and
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
            self._normalize_delivery_fields(attrs, address, service_city, order_scope)
        if market and not self._market_matches_order_scope(
            market,
            order_scope,
            service_city,
        ):
            raise serializers.ValidationError(
                {
                    "market_id": self._market_scope_error_message(
                        market,
                        order_scope,
                        service_city,
                    )
                }
            )
        if items is not None:
            invalid_market = next(
                (
                    item["variant"].product.market
                    for item in items
                    if not self._market_matches_order_scope(
                        item["variant"].product.market,
                        order_scope,
                        service_city,
                    )
                ),
                None,
            )
            if invalid_market is not None:
                raise serializers.ValidationError(
                    {
                        "items": self._market_scope_error_message(
                            invalid_market,
                            order_scope,
                            service_city,
                        )
                    }
                )
        if offers is not None:
            invalid_offer = next(
                (
                    item["offer"]
                    for item in offers
                    if not self._offer_matches_order_scope(
                        item["offer"],
                        order_scope,
                        service_city,
                    )
                ),
                None,
            )
            if invalid_offer is not None:
                raise serializers.ValidationError(
                    {
                        "offers": self._offer_scope_error_message(
                            invalid_offer,
                            order_scope,
                            service_city,
                        )
                    }
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
                courier_service_city = self._courier_service_city_for_order(
                    order_scope,
                    service_city,
                    attrs.get(
                        "delivery_area",
                        getattr(self.instance, "delivery_area", None),
                    ),
                )
                if (
                    courier_service_city is not None
                    and profile.service_city_id != courier_service_city.id
                ):
                    raise serializers.ValidationError(
                        {
                            "assigned_representative_id": (
                                "هذا المندوب لا يعمل في نفس مدينة الطلب."
                            )
                        }
                    )
                attrs["status"] = Order.Status.ASSIGNED
                if not attrs.get("assigned_at"):
                    attrs["assigned_at"] = timezone.now()
            else:
                attrs["assigned_at"] = None
                if self.instance and self.instance.assigned_representative_id:
                    attrs["status"] = Order.Status.CONFIRMED
        return attrs

    def _normalize_delivery_fields(self, attrs, address, service_city, order_scope):
        if order_scope == Order.Scope.GENERAL:
            attrs["service_city"] = None
            attrs["delivery_area"] = None
            attrs["delivery_type"] = Order.DeliveryType.DELIVERY
            attrs["delivery_price"] = None
            return

        if address is not None:
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and address.delivery_type == Address.DeliveryType.FIXED_AREA
                and address.delivery_area_id
            ):
                delivery_area = address.delivery_area
                if (
                    delivery_area.is_active
                    and service_city is not None
                    and delivery_area.service_city_id == service_city.id
                ):
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
            if order_scope == Order.Scope.SERVICE_CITY and service_city is None:
                raise serializers.ValidationError(
                    {"service_city_id": "Service city is required for fixed-area delivery."}
                )
            if not delivery_area.is_active:
                raise serializers.ValidationError(
                    {"delivery_area_id": "Delivery area must be active."}
                )
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and delivery_area.service_city_id != service_city.id
            ):
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

    def _market_matches_order_scope(self, market, order_scope, service_city):
        if market is None or order_scope is None:
            return False
        if order_scope == Order.Scope.GENERAL:
            return market.scope == Market.Scope.GENERAL
        return (
            market.scope in [Market.Scope.GENERAL, Market.Scope.SERVICE_CITY]
            and service_city is not None
            and market.service_cities.filter(
                pk=service_city.pk,
                is_active=True,
            ).exists()
        )

    def _offer_matches_order_scope(self, offer, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            if not offer.show_in_general:
                return False
        elif order_scope == Order.Scope.SERVICE_CITY:
            if (
                service_city is None
                or not offer.service_cities.filter(
                    pk=service_city.id,
                    is_active=True,
                ).exists()
            ):
                return False
        else:
            return False

        if not self._market_matches_order_scope(
            offer.market,
            order_scope,
            service_city,
        ):
            return False
        return all(
            self._market_matches_order_scope(
                product.market,
                order_scope,
                service_city,
            )
            for product in offer.products.select_related("market").all()
        )

    def _market_scope_error_message(self, market, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            return MIXED_MARKET_SCOPE_MESSAGE
        if market.scope == Market.Scope.GENERAL:
            return MIXED_MARKET_SCOPE_MESSAGE
        return MIXED_SERVICE_CITY_MARKETS_MESSAGE

    def _offer_scope_error_message(self, offer, order_scope, service_city):
        if order_scope == Order.Scope.GENERAL:
            if not offer.show_in_general:
                return SERVICE_CITY_OFFER_IN_GENERAL_MESSAGE
            return MIXED_MARKET_SCOPE_MESSAGE
        if (
            service_city is None
            or not offer.service_cities.filter(
                pk=service_city.id,
                is_active=True,
            ).exists()
        ):
            return GENERAL_OFFER_IN_SERVICE_CITY_MESSAGE
        return MIXED_SERVICE_CITY_MARKETS_MESSAGE

    @staticmethod
    def _courier_service_city_for_order(order_scope, service_city, delivery_area):
        if order_scope == Order.Scope.SERVICE_CITY:
            return service_city
        return None

    @staticmethod
    def _first_market_from_lines(items, offers):
        if items:
            return items[0]["variant"].product.market
        if offers:
            return offers[0]["offer"].market
        return None

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        offers = validated_data.pop("order_offers", [])
        order = Order.objects.create(**validated_data)
        self._replace_sections(order, items, offers)
        return order

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        offers = validated_data.pop("order_offers", None)
        instance = super().update(instance, validated_data)
        if items is not None or offers is not None:
            current_items = list(instance.items.all()) if items is None else items
            current_offers = (
                list(instance.order_offers.all()) if offers is None else offers
            )
            instance.market_sections.all().delete()
            instance.items.all().delete()
            instance.order_offers.all().delete()
            self._replace_sections(instance, current_items, current_offers)
        return instance

    @staticmethod
    def _replace_sections(order, items, offers):
        groups = {}

        def group_for_market(market):
            return groups.setdefault(
                market.id,
                {
                    "market": market,
                    "items": [],
                    "offers": [],
                    "subtotal": Decimal("0.00"),
                    "discount": Decimal("0.00"),
                },
            )

        for item in items:
            if isinstance(item, OrderItem):
                item_data = {
                    "variant": item.variant,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                }
            else:
                item_data = item
            group = group_for_market(item_data["variant"].product.market)
            group["items"].append(item_data)
            group["subtotal"] += item_data["unit_price"] * item_data["quantity"]

        for offer_item in offers:
            if isinstance(offer_item, OrderOffer):
                offer_data = {
                    "offer": offer_item.offer,
                    "discount_amount": offer_item.discount_amount,
                }
            else:
                offer_data = offer_item
            group = group_for_market(offer_data["offer"].market)
            group["offers"].append(offer_data)
            group["discount"] += offer_data.get("discount_amount", Decimal("0.00"))

        for sort_order, market_id in enumerate(sorted(groups)):
            group = groups[market_id]
            section = OrderMarketSection.objects.create(
                order=order,
                market=group["market"],
                subtotal_price=group["subtotal"],
                discount=group["discount"],
                sort_order=sort_order,
            )
            OrderItem.objects.bulk_create(
                OrderItem(order=order, section=section, **item)
                for item in group["items"]
            )
            OrderOffer.objects.bulk_create(
                OrderOffer(order=order, section=section, **offer)
                for offer in group["offers"]
            )


class OrderListSerializer(serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()
    market = MarketSummarySerializer(read_only=True)
    assigned_representative = AssignedRepresentativeSummarySerializer(read_only=True)
    delivery_address = serializers.SerializerMethodField()
    market_count = serializers.SerializerMethodField()
    market_names_summary = serializers.SerializerMethodField()
    has_offer = serializers.SerializerMethodField()
    offer_titles = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "customer",
            "status",
            "review_status",
            "order_scope",
            "market",
            "market_count",
            "market_names_summary",
            "has_offer",
            "offer_titles",
            "delivery_address",
            "delivery_type",
            "delivery_price",
            "subtotal_price",
            "discount",
            "total_price",
            "assigned_representative_id",
            "assigned_representative",
            "created_at",
            "updated_at",
        )

    def get_customer(self, instance):
        return user_summary(instance.user)

    def get_delivery_address(self, instance):
        return OrderSerializer(context=self.context).get_delivery_address(instance)

    def get_market_count(self, instance):
        return instance.market_sections.count()

    def get_market_names_summary(self, instance):
        sections = list(instance.market_sections.all())
        if sections:
            return ", ".join(section.market.name for section in sections)
        return instance.market.name if instance.market_id else ""

    def _order_offers(self, instance):
        return list(instance.order_offers.all())

    def get_has_offer(self, instance):
        return bool(self._order_offers(instance))

    def get_offer_titles(self, instance):
        titles = {}
        for order_offer in self._order_offers(instance):
            if order_offer.offer_id and order_offer.offer.title:
                titles.setdefault(order_offer.offer_id, order_offer.offer.title)
        return list(titles.values())


class AdminOrderCreateSerializer(OrderSerializer):
    SYSTEM_CONTROLLED_CREATE_FIELDS = {
        "assigned_representative_id",
        "assigned_at",
        "delivered_at",
        "delivery_area_id",
        "delivery_type",
        "delivery_price",
        "order_scope",
        "discount",
        "subtotal_price",
        "total_price",
        "image",
        "delivery_proof",
        "market_sections",
        "status",
        "review_status",
        "approved_by",
        "approved_at",
        "rejected_by",
        "rejected_at",
        "rejection_reason",
    }

    items = AdminOrderItemCreateSerializer(many=True, required=False)
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

        items = attrs.get("items", [])
        offers = attrs.get("order_offers", [])
        first_market = self._first_market_from_lines(items, offers)
        if first_market is not None:
            attrs["market"] = first_market

        attrs = super().validate(attrs)
        if not attrs.get("items") and not attrs.get("order_offers"):
            raise serializers.ValidationError(
                {"items": "Choose at least one product variant or offer."}
            )
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        offers = validated_data.pop("order_offers", [])
        has_free_delivery = OrderPreviewSerializer._has_free_delivery_offer(offers)
        items, offers = self._server_priced_lines(items, offers)
        if items:
            validated_data["market"] = items[0]["variant"].product.market
        elif offers:
            validated_data["market"] = offers[0]["offer"].market
        subtotal = sum(
            item["unit_price"] * item["quantity"]
            for item in items
        )
        discount = sum(
            item.get("discount_amount", Decimal("0.00"))
            for item in offers
        )
        delivery_price = (
            Decimal("0.00")
            if has_free_delivery
            else validated_data.get("delivery_price")
        )
        validated_data["delivery_price"] = delivery_price
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
        self._replace_sections(order, items, offers)
        return order

    def _server_priced_lines(self, items, offers):
        priced_items = []
        selected_lines_by_variant = {}

        for item in items:
            variant = item["variant"]
            quantity = item["quantity"]
            unit_price = OrderPreviewSerializer._product_unit_price(variant)
            priced_item = {
                "variant": variant,
                "quantity": quantity,
                "unit_price": unit_price,
            }
            priced_items.append(priced_item)
            selected_lines_by_variant.setdefault(variant.id, []).append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "subtotal": unit_price * quantity,
                }
            )

        priced_offers = []
        for offer_item in offers:
            offer = offer_item["offer"]
            offer_products_subtotal = Decimal("0.00")
            for (
                variant,
                offer_quantity,
                apply_product_discount,
            ) in OrderPreviewSerializer._offer_variant_rows(offer):
                product = variant.product
                selected_lines = selected_lines_by_variant.get(variant.id, [])
                if selected_lines:
                    offer_products_subtotal += sum(
                        line["subtotal"] for line in selected_lines
                    )
                    continue

                unit_price = OrderPreviewSerializer._product_unit_price(
                    variant,
                    apply_product_discount=apply_product_discount,
                )
                subtotal = unit_price * offer_quantity
                priced_item = {
                    "variant": variant,
                    "quantity": offer_quantity,
                    "unit_price": unit_price,
                }
                priced_items.append(priced_item)
                selected_lines_by_variant.setdefault(variant.id, []).append(
                    {
                        "variant": variant,
                        "quantity": offer_quantity,
                        "subtotal": subtotal,
                    }
                )
                offer_products_subtotal += subtotal

            priced_offers.append(
                {
                    "offer": offer,
                    "discount_amount": OrderPreviewSerializer._percentage_amount(
                        offer_products_subtotal,
                        offer.discount,
                    ),
                }
            )

        return priced_items, priced_offers


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class OrderDeliveryPriceSerializer(serializers.Serializer):
    delivery_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )


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
    display_name = serializers.SerializerMethodField()
    item_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "display_name",
            "quantity",
            "unit_price",
            "item_subtotal",
            "product",
            "variant",
        )

    def get_display_name(self, instance):
        product_name = instance.variant.product.name
        variant_name = OrderItemSerializer(context=self.context).get_variant_name(
            instance
        )
        return f"{product_name} - {variant_name}" if variant_name else product_name

    def get_item_subtotal(self, instance):
        return f"{instance.unit_price * instance.quantity:.2f}"

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
    market_count = serializers.SerializerMethodField()
    market_names_summary = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "order_scope",
            "service_city",
            "delivery_area",
            "delivery_type",
            "market",
            "market_count",
            "market_names_summary",
            "items_count",
            "customer",
            "delivery_address",
            "total_price",
            "delivery_price",
            "created_at",
            "assigned_at",
        )

    def get_customer(self, instance):
        return user_summary(instance.user)

    def get_market_count(self, instance):
        annotated_count = getattr(instance, "sections_count", None)
        if annotated_count is not None:
            return annotated_count
        return instance.market_sections.count()

    def get_market_names_summary(self, instance):
        prefetched = getattr(instance, "_prefetched_objects_cache", {})
        sections = prefetched.get("market_sections")
        if sections is not None:
            return ", ".join(section.market.name for section in sections)
        annotated_count = getattr(instance, "sections_count", None)
        if annotated_count is not None and annotated_count > 1:
            return ""
        if instance.market_id:
            return instance.market.name
        return ""

    def get_items_count(self, instance):
        annotated_count = getattr(instance, "items_count", None)
        if annotated_count is not None:
            return annotated_count
        return sum(item.quantity for item in instance.items.all())

    def get_delivery_address(self, instance):
        if instance.delivery_address is None:
            return None
        return {
            "id": instance.delivery_address.id,
            "name": instance.delivery_address.name,
            "details": instance.delivery_address.details,
            "latitude": instance.delivery_address.latitude,
            "longitude": instance.delivery_address.longitude,
            "manual_city": instance.delivery_address.manual_city,
            "manual_area": instance.delivery_address.manual_area,
            "service_city": (
                ServiceCitySummarySerializer(
                    instance.delivery_address.service_city
                ).data
                if instance.delivery_address.service_city_id
                else None
            ),
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
    market_sections = OrderMarketSectionSerializer(many=True, read_only=True)

    class Meta(CourierOrderListSerializer.Meta):
        fields = CourierOrderListSerializer.Meta.fields + (
            "market_sections",
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
            (Order.Status.DELIVERED, Order.Status.DELIVERED.label),
            (Order.Status.FAILED_DELIVERY, Order.Status.FAILED_DELIVERY.label),
        )
    )
    delivery_note = serializers.CharField(required=False, allow_blank=True)
    delivery_proof = serializers.ImageField(required=False, allow_null=True)
