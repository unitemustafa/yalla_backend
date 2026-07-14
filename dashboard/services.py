from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from markets.models import Market
from orders.models import Order, OrderItem, OrderMarketSection

MONEY_ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)
SUCCESSFUL_STATUSES = (Order.Status.DELIVERED,)
ACTIVE_STATUSES = (
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.ASSIGNED,
    Order.Status.PICKED_UP,
)


def money(value):
    return (value or MONEY_ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percentage(numerator, denominator):
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 1)


def date_bounds(from_date, to_date):
    current_timezone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(from_date, time.min), current_timezone)
    end = timezone.make_aware(
        datetime.combine(to_date + timedelta(days=1), time.min),
        current_timezone,
    )
    return start, end


def order_number(order):
    return f"YM-{order.created_at:%Y%m%d}-{order.id:06d}"


def customer_name(user):
    full_name = user.get_full_name().strip()
    return full_name or user.username


def market_display_name(market):
    if not market:
        return ""
    if market.branch:
        return f"{market.name} - {market.branch}"
    return market.name


def summarize_names(names):
    cleaned_names = [name for name in names if name]
    if len(cleaned_names) <= 2:
        return ", ".join(cleaned_names)
    return f"{cleaned_names[0]}, {cleaned_names[1]} + {len(cleaned_names) - 2} more"


def market_zone(market):
    cities = sorted(
        market.service_cities.all(),
        key=lambda city: (city.name.casefold(), city.id),
    )
    if not cities:
        return "General market" if market.scope == Market.Scope.GENERAL else ""
    return summarize_names([city.name for city in cities])


def active_order_market_summary(order):
    sections = list(order.market_sections.all())
    if sections:
        names = [market_display_name(section.market) for section in sections]
    else:
        names = [market_display_name(order.market)]

    market_count = len(names)
    return {
        "market_count": market_count,
        "market_names_summary": summarize_names(names),
        "is_multi_market": market_count > 1,
    }


def section_revenue(section):
    return max(section.subtotal_price - section.discount, MONEY_ZERO)


def add_shop_row(rows, market, order_id, revenue, units):
    row = rows[market.id]
    row["market"] = market
    row["order_ids"].add(order_id)
    row["revenue"] += revenue
    row["units"] += units


def build_top_shops(start, end):
    rows = defaultdict(
        lambda: {
            "market": None,
            "order_ids": set(),
            "revenue": MONEY_ZERO,
            "units": 0,
        }
    )

    section_queryset = (
        OrderMarketSection.objects.filter(
            order__created_at__gte=start,
            order__created_at__lt=end,
            order__status__in=SUCCESSFUL_STATUSES,
        )
        .select_related("market")
        .prefetch_related(
            "market__service_cities",
            Prefetch("items", queryset=OrderItem.objects.only("id", "section_id", "quantity")),
        )
        .order_by("order_id", "sort_order", "id")
    )
    for section in section_queryset:
        units = sum(item.quantity for item in section.items.all())
        add_shop_row(
            rows,
            section.market,
            section.order_id,
            section_revenue(section),
            units,
        )

    legacy_orders = (
        Order.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            status__in=SUCCESSFUL_STATUSES,
        )
        .annotate(section_count=Count("market_sections"))
        .filter(section_count=0)
        .select_related("market")
        .prefetch_related(
            "market__service_cities",
            Prefetch("items", queryset=OrderItem.objects.only("id", "order_id", "quantity")),
        )
    )
    for order in legacy_orders:
        units = sum(item.quantity for item in order.items.all())
        revenue = max(order.subtotal_price - order.discount, MONEY_ZERO)
        add_shop_row(rows, order.market, order.id, revenue, units)

    sorted_rows = sorted(
        rows.values(),
        key=lambda row: (-row["revenue"], row["market"].id),
    )[:5]
    top_shops = []
    for row in sorted_rows:
        market = row["market"]
        orders_count = len(row["order_ids"])
        top_shops.append(
            {
                "market_id": market.id,
                "name": market_display_name(market),
                "zone": market_zone(market),
                "orders_count": orders_count,
                "average_items_per_order": round(
                    row["units"] / orders_count if orders_count else 0,
                    2,
                ),
                "revenue": money(row["revenue"]),
            }
        )
    return top_shops


def build_dashboard_overview(from_date, to_date):
    start, end = date_bounds(from_date, to_date)
    orders = Order.objects.filter(created_at__gte=start, created_at__lt=end)

    order_totals = orders.aggregate(
        all_value=Coalesce(Sum("total_price"), MONEY_ZERO, output_field=MONEY_FIELD),
        revenue=Coalesce(
            Sum("total_price", filter=Q(status__in=SUCCESSFUL_STATUSES)),
            MONEY_ZERO,
            output_field=MONEY_FIELD,
        ),
    )
    order_counts = orders.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status__in=SUCCESSFUL_STATUSES)),
    )
    total_orders = order_counts["total"]
    completed_orders = order_counts["completed"]
    revenue = money(order_totals["revenue"])

    customer_ids = orders.values_list("user_id", flat=True).distinct()
    returning_customers = (
        Order.objects.filter(user_id__in=customer_ids, created_at__lt=start)
        .values("user_id")
        .distinct()
        .count()
    )
    customers_in_range = customer_ids.count()
    new_customers = customers_in_range - returning_customers

    item_revenue = ExpressionWrapper(
        F("quantity") * F("unit_price"),
        output_field=MONEY_FIELD,
    )
    top_products = list(
        OrderItem.objects.filter(
            order__created_at__gte=start,
            order__created_at__lt=end,
            order__status__in=SUCCESSFUL_STATUSES,
        )
        .values(
            product_id=F("variant__product_id"),
            name=F("variant__product__name"),
        )
        .annotate(
            revenue=Sum(item_revenue),
            quantity_sold=Sum("quantity"),
            orders_count=Count("order_id", distinct=True),
        )
        .order_by("-revenue", "product_id")[:5]
    )
    for product in top_products:
        product["revenue"] = money(product["revenue"])

    active_order_queryset = (
        orders.filter(status__in=ACTIVE_STATUSES)
        .select_related("user", "market")
        .prefetch_related(
            Prefetch(
                "market_sections",
                queryset=OrderMarketSection.objects.select_related("market").order_by(
                    "sort_order",
                    "id",
                ),
            )
        )
        .order_by("-created_at", "-id")[:5]
    )
    active_orders = []
    for order in active_order_queryset:
        active_orders.append(
            {
                "id": order.id,
                "number": order_number(order),
                "customer": {
                    "id": order.user_id,
                    "name": customer_name(order.user),
                },
                "total": money(order.total_price),
                "status": order.status,
                "created_at": order.created_at,
                **active_order_market_summary(order),
            }
        )

    return {
        "range": {
            "from": from_date,
            "to": to_date,
            "timezone": timezone.get_current_timezone_name(),
        },
        "currency": "EGP",
        "revenue": {
            "total": revenue,
            "percentage": percentage(revenue, order_totals["all_value"]),
        },
        "orders": {
            "total": total_orders,
            "completed": completed_orders,
            "incomplete": total_orders - completed_orders,
            "completion_rate": percentage(completed_orders, total_orders),
        },
        "customers": {
            "new": new_customers,
            "returning": returning_customers,
            "return_rate": percentage(
                returning_customers,
                new_customers + returning_customers,
            ),
        },
        "top_products": top_products,
        "active_orders": active_orders,
        "top_shops": build_top_shops(start, end),
    }
