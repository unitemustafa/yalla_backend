from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from markets.models import Market
from orders.models import Order, OrderItem

MONEY_ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)
SUCCESSFUL_STATUSES = (Order.Status.DELIVERED,)
ACTIVE_STATUSES = (
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.UNDER_PREPARATION,
    Order.Status.READY,
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


def build_dashboard_overview(from_date, to_date):
    start, end = date_bounds(from_date, to_date)
    orders = Order.objects.filter(created_at__gte=start, created_at__lt=end)
    successful_orders = orders.filter(status__in=SUCCESSFUL_STATUSES)

    order_totals = orders.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status__in=SUCCESSFUL_STATUSES)),
        all_value=Coalesce(Sum("total_price"), MONEY_ZERO, output_field=MONEY_FIELD),
        revenue=Coalesce(
            Sum("total_price", filter=Q(status__in=SUCCESSFUL_STATUSES)),
            MONEY_ZERO,
            output_field=MONEY_FIELD,
        ),
    )
    total_orders = order_totals["total"]
    completed_orders = order_totals["completed"]
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

    active_orders = [
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
        }
        for order in orders.filter(status__in=ACTIVE_STATUSES)
        .select_related("user")
        .order_by("-created_at", "-id")[:5]
    ]

    top_shop_rows = list(
        successful_orders.values(
            "market_id",
            market_name=F("market__name"),
            market_branch=F("market__branch"),
        )
        .annotate(
            orders_count=Count("id"),
            revenue=Sum("total_price"),
        )
        .order_by("-revenue", "market_id")[:5]
    )
    market_ids = [row["market_id"] for row in top_shop_rows]
    markets = {
        market.id: market
        for market in Market.objects.filter(id__in=market_ids).prefetch_related(
            "delivery_areas__service_city"
        )
    }
    units_by_market = {
        row["order__market_id"]: row["units"]
        for row in OrderItem.objects.filter(
            order__created_at__gte=start,
            order__created_at__lt=end,
            order__status__in=SUCCESSFUL_STATUSES,
            order__market_id__in=market_ids,
        )
        .values("order__market_id")
        .annotate(units=Sum("quantity"))
    }
    top_shops = []
    for row in top_shop_rows:
        market = markets[row["market_id"]]
        first_area = next(iter(market.delivery_areas.all()), None)
        zone = first_area.service_city.name if first_area else ""
        display_name = row["market_name"]
        if row["market_branch"]:
            display_name = f"{display_name} - {row['market_branch']}"
        top_shops.append(
            {
                "market_id": row["market_id"],
                "name": display_name,
                "zone": zone,
                "orders_count": row["orders_count"],
                "average_items_per_order": round(
                    units_by_market.get(row["market_id"], 0)
                    / row["orders_count"],
                    2,
                ),
                "revenue": money(row["revenue"]),
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
        "top_shops": top_shops,
    }
