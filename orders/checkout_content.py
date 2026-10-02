"""Shared checkout validation and immutable selected-addition pricing."""

from decimal import Decimal

from rest_framework import serializers

from catalog.models import ProductAddition
from markets.models import Market
from markets.region import visible_offer_queryset
from offers.models import Offer


def selected_additions(item):
    ids = item.get("addition_ids", [])
    if len(ids) != len(set(ids)):
        raise serializers.ValidationError(
            {"addition_ids": "Duplicate additions are not allowed."}
        )
    additions = list(
        ProductAddition.objects.filter(
            id__in=ids,
            products=item["variant"].product,
            is_active=True,
        ).order_by("id")
    )
    if len(additions) != len(ids):
        raise serializers.ValidationError(
            {"addition_ids": "An addition is unavailable for this product."}
        )
    return [
        {
            "id": addition.id,
            "name": addition.name_ar or addition.name_en,
            "price": f"{addition.price:.2f}",
        }
        for addition in additions
    ]


def additions_price(additions):
    return sum((Decimal(row["price"]) for row in additions), Decimal("0.00"))


def offer_variant_rows(offer):
    offer_items = list(offer.items.all())
    if offer_items:
        return [
            (item.variant, item.quantity, item.apply_product_discount)
            for item in offer_items
        ]
    rows = []
    for product in offer.products.all():
        variant = product.variants.order_by("id").first()
        if variant is not None:
            rows.append((variant, 1, True))
    return rows


def validate_checkout_content(
    items, offers, *, user, lock_offers=False, apply_region=True
):
    offer_ids = [row["offer"].id for row in offers]
    if len(offer_ids) != len(set(offer_ids)):
        raise serializers.ValidationError(
            {"offers": "Duplicate offers are not allowed."}
        )
    if lock_offers and offer_ids:
        # Every checkout locks offers in the same order before counting uses.
        list(Offer.objects.select_for_update().filter(id__in=offer_ids).order_by("id"))
    variants = [row["variant"] for row in items]
    for row in offers:
        variants.extend(variant for variant, _, _ in offer_variant_rows(row["offer"]))
        market = row["offer"].market
        if market and (market.status != Market.Status.ACTIVE or market.archived_at):
            raise serializers.ValidationError(
                {"offers": "The offer market is unavailable."}
            )
    if any(
        not variant.product.is_available
        or variant.product.archived_at
        or variant.product.market.status != Market.Status.ACTIVE
        or variant.product.market.archived_at
        for variant in variants
    ):
        raise serializers.ValidationError(
            {"items": "A product or market is no longer available."}
        )
    if offers:
        eligible = set(
            visible_offer_queryset(user, apply_region=apply_region)
            .filter(id__in=offer_ids)
            .values_list("id", flat=True)
        )
        if any(offer_id not in eligible for offer_id in offer_ids):
            raise serializers.ValidationError(
                {"offers": "One or more offers are no longer available."}
            )
