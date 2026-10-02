"""Bounded admin order reads with counts computed independently of the page."""

from django.db.models import CharField, Count, F, Q, Sum, Value
from django.db.models.functions import Cast, Concat
from rest_framework import serializers
from rest_framework.response import Response

from .models import Order


def filtered_admin_orders(queryset, parameters):
    scope = parameters.get("scope")
    terminal = (
        Order.Status.DELIVERED,
        Order.Status.CANCELLED,
        Order.Status.FAILED_DELIVERY,
    )
    if scope == "active":
        queryset = queryset.exclude(status__in=terminal)
    elif scope == "history":
        queryset = queryset.filter(status__in=terminal)
    elif scope is not None:
        raise serializers.ValidationError({"scope": "Unsupported order scope."})
    representative = parameters.get("representative_id")
    if representative is not None:
        identifier = serializers.IntegerField(min_value=1).run_validation(
            representative
        )
        queryset = queryset.filter(assigned_representative_id=identifier)
    delivery = parameters.get("delivery_type")
    if delivery == "delivery":
        queryset = queryset.filter(delivery_type__in=("delivery", "manual_quote"))
    elif delivery == "fixed_area":
        queryset = queryset.filter(delivery_type=delivery)
    elif delivery not in (None, "all"):
        raise serializers.ValidationError(
            {"delivery_type": "Unsupported delivery type."}
        )
    query = parameters.get("search", "").strip()
    if len(query) > 200:
        raise serializers.ValidationError(
            {"search": "Search must not exceed 200 characters."}
        )
    if query:
        # JSON fields use the saved order destination, not today's address book.
        fields = (
            "user__first_name",
            "user__last_name",
            "user__username",
            "user__phone",
            "market__name",
            "market_sections__market__name",
            "service_city__name",
            "assigned_representative__first_name",
            "assigned_representative__last_name",
            "assigned_representative__username",
            "delivery_address_snapshot__details",
            "delivery_address_snapshot__street",
            "delivery_address_snapshot__recipient_name",
            "delivery_address_snapshot__formatted_address",
            "delivery_address_snapshot__manual_city",
            "delivery_address_snapshot__manual_area",
        )
        predicate = Q()
        for field in fields:
            predicate |= Q(**{f"{field}__icontains": query})
        identifier_query = (
            query.removeprefix("#").removeprefix("YM-").removeprefix("ORD-")
        )
        queryset = queryset.annotate(
            _search_id=Cast("id", CharField()),
            _customer_name=Concat("user__first_name", Value(" "), "user__last_name"),
            _representative_name=Concat(
                "assigned_representative__first_name",
                Value(" "),
                "assigned_representative__last_name",
            ),
        )
        if identifier_query:
            predicate |= Q(_search_id__icontains=identifier_query)
        predicate |= Q(_customer_name__icontains=query) | Q(
            _representative_name__icontains=query
        )
        queryset = queryset.filter(predicate).distinct()
    ordering = parameters.get("ordering")
    if ordering in ("-delivered_at", "-assigned_at", "-created_at"):
        queryset = queryset.order_by(F(ordering[1:]).desc(nulls_last=True), "-id")
    elif ordering is not None:
        raise serializers.ValidationError({"ordering": "Unsupported order sorting."})
    return queryset


def order_counts(queryset):
    return queryset.aggregate(
        total=Count("pk", distinct=True),
        assignmentReady=Count(
            "pk",
            filter=Q(status=Order.Status.CONFIRMED, assigned_representative=None),
            distinct=True,
        ),
        assigned=Count(
            "pk",
            filter=Q(
                status=Order.Status.ASSIGNED, assigned_representative__isnull=False
            ),
            distinct=True,
        ),
        delivered=Count("pk", filter=Q(status=Order.Status.DELIVERED), distinct=True),
    )


class AdminOrderListMixin:
    def list(self, request, *args, **kwargs):
        # Keep the unpaged v1 shape for existing consumers. New clients request
        # page/page_size explicitly and never need the full accumulated history.
        base = self.filter_queryset(self.get_queryset())
        queryset = filtered_admin_orders(base, request.query_params)
        page = self.paginate_queryset(queryset)
        if page is None:
            return Response(self.get_serializer(queryset, many=True).data)
        response = self.get_paginated_response(
            self.get_serializer(page, many=True).data
        )
        response.data["metrics"] = order_counts(base)
        totals = queryset.aggregate(
            count=Count("pk"),
            total_value=Sum("total_price"),
            total_delivery_fees=Sum("delivery_price"),
        )
        response.data["summary"] = {
            "count": totals["count"],
            "total_value": f"{totals['total_value'] or 0:.2f}",
            "total_delivery_fees": f"{totals['total_delivery_fees'] or 0:.2f}",
        }
        if request.query_params.get("include_courier_summary") == "1":
            courier_rows = list(
                Order.objects.filter(assigned_representative__isnull=False)
                .order_by()
                .values("assigned_representative_id")
                .annotate(
                    active=Count(
                        "pk",
                        filter=Q(
                            status__in=(Order.Status.ASSIGNED, Order.Status.PICKED_UP)
                        ),
                    ),
                    delivered=Count("pk", filter=Q(status=Order.Status.DELIVERED)),
                    total=Count("pk"),
                    delivered_total=Sum(
                        "total_price", filter=Q(status=Order.Status.DELIVERED)
                    ),
                )
            )
            response.data["courier_summary"] = [
                {**row, "delivered_total": f"{row['delivered_total'] or 0:.2f}"}
                for row in courier_rows
            ]
        return response
