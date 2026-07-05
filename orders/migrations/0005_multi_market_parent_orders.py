import django.db.models.deletion
from django.db import migrations, models


def backfill_order_scope_and_sections(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    OrderOffer = apps.get_model("orders", "OrderOffer")
    OrderMarketSection = apps.get_model("orders", "OrderMarketSection")

    unresolved_scope_ids = []
    missing_market_ids = []

    orders = Order.objects.select_related("market", "service_city").order_by("id")
    for order in orders.iterator():
        scope = None
        service_city_id = order.service_city_id

        market = getattr(order, "market", None)
        if order.market_id and market is not None:
            if market.scope == "general":
                scope = "general"
                service_city_id = None
            elif market.scope == "service_city":
                if service_city_id is None:
                    service_city_id = (
                        market.service_cities.filter(is_active=True)
                        .order_by("id")
                        .values_list("id", flat=True)
                        .first()
                    )
                    if service_city_id is None:
                        service_city_id = (
                            market.service_cities.order_by("id")
                            .values_list("id", flat=True)
                            .first()
                        )
                scope = "service_city" if service_city_id is not None else None
        elif service_city_id is not None:
            scope = "service_city"

        if scope is None:
            unresolved_scope_ids.append(order.id)

        update_fields = []
        if order.order_scope != scope:
            order.order_scope = scope
            update_fields.append("order_scope")
        if order.service_city_id != service_city_id:
            order.service_city_id = service_city_id
            update_fields.append("service_city")
        if update_fields:
            order.save(update_fields=update_fields)

        if order.market_id:
            section, _ = OrderMarketSection.objects.get_or_create(
                order_id=order.id,
                market_id=order.market_id,
                defaults={
                    "subtotal_price": order.subtotal_price,
                    "discount": order.discount,
                    "sort_order": 0,
                },
            )
            OrderItem.objects.filter(
                order_id=order.id,
                section_id__isnull=True,
            ).update(section_id=section.id)
            OrderOffer.objects.filter(
                order_id=order.id,
                section_id__isnull=True,
            ).update(section_id=section.id)
        else:
            missing_market_ids.append(order.id)

    if unresolved_scope_ids:
        print(
            "orders.0005: preserved orders with unresolved order_scope: "
            f"{unresolved_scope_ids}"
        )
    if missing_market_ids:
        print(
            "orders.0005: preserved orders without market sections: "
            f"{missing_market_ids}"
        )


def reverse_order_scope_and_sections(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    OrderOffer = apps.get_model("orders", "OrderOffer")
    OrderMarketSection = apps.get_model("orders", "OrderMarketSection")

    OrderItem.objects.update(section_id=None)
    OrderOffer.objects.update(section_id=None)
    OrderMarketSection.objects.all().delete()
    Order.objects.update(order_scope=None)


class Migration(migrations.Migration):

    dependencies = [
        ("markets", "0004_marketclassification_classification_type"),
        ("orders", "0004_alter_order_service_city"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="order_scope",
            field=models.CharField(
                blank=True,
                choices=[
                    ("general", "General"),
                    ("service_city", "Service city"),
                ],
                db_index=True,
                max_length=20,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="OrderMarketSection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "subtotal_price",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                (
                    "discount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                (
                    "pickup_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("picked_up", "Picked up"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("picked_up_at", models.DateTimeField(blank=True, null=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "market",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="order_sections",
                        to="markets.market",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="market_sections",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.AddField(
            model_name="orderitem",
            name="section",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="items",
                to="orders.ordermarketsection",
            ),
        ),
        migrations.AddField(
            model_name="orderoffer",
            name="section",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="offers",
                to="orders.ordermarketsection",
            ),
        ),
        migrations.RunPython(
            backfill_order_scope_and_sections,
            reverse_order_scope_and_sections,
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("order_scope__isnull", True))
                    | (
                        models.Q(("order_scope", "general"))
                        & models.Q(("service_city__isnull", True))
                    )
                    | (
                        models.Q(("order_scope", "service_city"))
                        & models.Q(("service_city__isnull", False))
                    )
                ),
                name="orders_order_scope_service_city_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordermarketsection",
            constraint=models.UniqueConstraint(
                fields=("order", "market"),
                name="orders_market_section_order_market_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordermarketsection",
            constraint=models.CheckConstraint(
                condition=models.Q(("subtotal_price__gte", 0)),
                name="orders_market_section_subtotal_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordermarketsection",
            constraint=models.CheckConstraint(
                condition=models.Q(("discount__gte", 0)),
                name="orders_market_section_discount_non_negative",
            ),
        ),
    ]
