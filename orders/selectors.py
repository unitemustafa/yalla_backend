from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce

from accounts.models import User

from .models import Order, OrderEvent, OrderItem, OrderMarketSection


def order_queryset():
    return (
        Order.objects.select_related(
            "user",
            "delivery_address",
            "delivery_address__service_city",
            "delivery_address__delivery_area",
            "delivery_address__delivery_area__service_city",
            "assigned_representative",
            "assigned_representative__courier_profile",
            "assigned_representative__courier_profile__service_city",
            "market",
            "service_city",
            "delivery_area",
            "delivery_area__service_city",
            "approved_by",
            "rejected_by",
        )
        .prefetch_related(
            "items__variant__product",
            "items__variant__attribute_values__attribute",
            "items__variant__attribute_values__option",
            "items__variant__attribute_values__product_attribute",
            "items__variant__attribute_values__product_attribute_option",
            "items__section",
            "order_offers__offer",
            "order_offers__section",
            "market__service_cities",
            "market_sections__market",
            "market_sections__items__variant__product",
            "market_sections__items__variant__attribute_values__attribute",
            "market_sections__items__variant__attribute_values__option",
            "market_sections__items__variant__attribute_values__product_attribute",
            "market_sections__items__variant__attribute_values__product_attribute_option",
            "market_sections__offers__offer",
            Prefetch(
                "history_events",
                queryset=OrderEvent.objects.select_related("actor").order_by(
                    "created_at",
                    "id",
                ),
            ),
        )
        .order_by("-created_at", "-id")
    )


def active_available_representatives():
    return (
        User.objects.filter(
            role=User.Role.REPRESENTATIVE,
            is_active=True,
            deleted_at__isnull=True,
            courier_profile__is_available=True,
        )
        .select_related("courier_profile__service_city")
        .order_by("first_name", "last_name", "username", "id")
    )


def same_city_representatives(service_city):
    if service_city is None:
        return User.objects.none()
    return active_available_representatives().filter(
        courier_profile__service_city=service_city,
    )


def courier_service_city_for_order(order):
    if order.order_scope == Order.Scope.SERVICE_CITY:
        return order.service_city
    return None


def eligible_representatives_for_order(order):
    service_city = courier_service_city_for_order(order)
    if service_city is None:
        return active_available_representatives()
    return same_city_representatives(service_city)


def courier_orders_for_user(user):
    return order_queryset().filter(assigned_representative=user)


def courier_order_list_queryset(user):
    items_count = (
        OrderItem.objects.filter(order=OuterRef("pk"))
        .values("order")
        .annotate(total=Coalesce(Sum("quantity"), 0))
        .values("total")[:1]
    )
    sections_count = (
        OrderMarketSection.objects.filter(order=OuterRef("pk"))
        .values("order")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    return (
        Order.objects.filter(assigned_representative=user)
        .select_related(
            "user",
            "delivery_address",
            "delivery_address__service_city",
            "delivery_address__delivery_area",
            "market",
            "service_city",
            "delivery_area",
        )
        .annotate(
            items_count=Coalesce(
                Subquery(items_count, output_field=IntegerField()),
                0,
            ),
            sections_count=Coalesce(
                Subquery(sections_count, output_field=IntegerField()),
                0,
            ),
        )
        .order_by("-created_at", "-id")
    )
