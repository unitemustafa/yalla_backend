from datetime import timedelta
from decimal import Decimal

from markets.models import Market
from offers.models import Offer, OfferItem
from orders.models import (
    Order,
    OrderEvent,
    OrderItem,
    OrderMarketSection,
    OrderOffer,
)
from orders.services import record_order_event


class OrderSeederMixin:
    def _seed_offers(self, markets, products, now):
        definitions = [
            (
                "عرض الفواكه الطازجة",
                "سوق يلا الطازج",
                "general",
                Offer.OfferType.DISCOUNT,
                "10.00",
                ["تفاح أحمر", "موز"],
            ),
            (
                "عرض عشاء العائلة",
                "مطبخ النيل العائلي",
                "service_city",
                Offer.OfferType.PACKAGE,
                "15.00",
                ["كشري بالدجاج", "شوربة خضار"],
            ),
            (
                "أساسيات الانتعاش",
                "سوق يلا الطازج",
                "general",
                Offer.OfferType.DELIVERY,
                "8.00",
                ["مياه معدنية", "عصير برتقال"],
            ),
            (
                "غداء القاهرة السريع",
                "مطبخ النيل العائلي",
                "service_city",
                Offer.OfferType.FLASH,
                "12.00",
                ["دجاج مشوي", "شوربة خضار"],
            ),
            (
                "عرض المخبزة الصباحي",
                "مخبزة الجيزة الذهبية",
                "service_city",
                Offer.OfferType.FLASH,
                "12.00",
                ["عيش بلدي", "كرواسون بالشوكولاتة"],
            ),
            ("أطباق إسكندرية", "نكهة إسكندرية", "service_city", Offer.OfferType.PACKAGE, "18.00", ["مكرونة إسكندراني", "طاجن خضار"]),
            ("حلويات البحر", "حلويات البحر", "service_city", Offer.OfferType.DISCOUNT, "10.00", ["بقلاوة", "بسبوسة بالعسل"]),
            ("أسبوع المنتجات العضوية", "خيرات المنصورة", "service_city", Offer.OfferType.ANNOUNCEMENT, "5.00", ["عسل مصري", "زيت زيتون"]),
            ("توصيل مخبزة الدلتا", "مخبزة الدلتا", "service_city", Offer.OfferType.DELIVERY, "7.00", ["خبز كامل", "بريوش"]),
        ]
        offers = {}
        for title, market_name, scope, offer_type, discount, product_names in definitions:
            market = markets[market_name]
            service_city = None
            if scope == "service_city":
                service_city = market.service_cities.filter(
                    is_active=True,
                ).order_by("id").first()
            offer, _ = Offer.objects.update_or_create(
                market=market,
                title=title,
                defaults={
                    "show_in_general": scope == "general",
                    "description": f"عرض تجريبي: {title}.",
                    "type": offer_type,
                    "discount": Decimal(discount),
                    "start_time": now - timedelta(days=1),
                    "end_time": now + timedelta(days=30),
                    "active_days": [0, 1, 2, 3, 4, 5, 6],
                    "use_limits": 500,
                    "user_limit": 3,
                    "status": Offer.Status.ACTIVE,
                },
            )
            offer.products.set([products[name] for name in product_names])
            selected_variants = [
                products[name].variants.order_by("id").first()
                for name in product_names
            ]
            selected_variants = [
                variant for variant in selected_variants if variant is not None
            ]
            offer.items.exclude(
                variant_id__in=[variant.id for variant in selected_variants]
            ).delete()
            for variant in selected_variants:
                OfferItem.objects.update_or_create(
                    offer=offer,
                    variant=variant,
                    defaults={
                        "quantity": 1,
                        "apply_product_discount": True,
                    },
                )
            offer.service_cities.set([service_city] if service_city is not None else [])
            offers[title] = offer
        return offers

    def _seed_orders(self, users, markets, variants, offers, now):
        definitions = [
            {
                "marker": "SEED-ORDER-001",
                "user": users["seed.amina@yalla.test"],
                "market": markets["سوق يلا الطازج"],
                "status": Order.Status.DELIVERED,
                "payment_method": "cash",
                "items": [
                    (variants["تفاح أحمر"][1], 2),
                    (variants["عصير برتقال"][0], 3),
                ],
                "offer": offers["عرض الفواكه الطازجة"],
                "offer_discount": Decimal("120.00"),
            },
            {
                "marker": "SEED-ORDER-002",
                "user": users["seed.karim@yalla.test"],
                "market": markets["مطبخ النيل العائلي"],
                "status": Order.Status.CONFIRMED,
                "payment_method": "card",
                "items": [
                    (variants["كشري بالدجاج"][0], 1),
                    (variants["شوربة خضار"][0], 2),
                ],
                "offer": offers["عرض عشاء العائلة"],
                "offer_discount": Decimal("180.00"),
            },
            {
                "marker": "SEED-ORDER-003",
                "user": users["seed.amina@yalla.test"],
                "market": markets["مخبزة الجيزة الذهبية"],
                "status": Order.Status.PENDING,
                "payment_method": "cash",
                "items": [
                    (variants["عيش بلدي"][1], 1),
                    (variants["كرواسون بالشوكولاتة"][0], 4),
                ],
                "offer": offers["عرض المخبزة الصباحي"],
                "offer_discount": Decimal("75.00"),
            },
            {
                "marker": "SEED-ORDER-004",
                "user": users["seed.sara@yalla.test"],
                "market": markets["نكهة إسكندرية"],
                "status": Order.Status.CONFIRMED,
                "payment_method": "cash",
                "items": [(variants["مكرونة إسكندراني"][0], 1)],
                "offer": offers["أطباق إسكندرية"],
                "offer_discount": Decimal("100.00"),
            },
            {
                "marker": "SEED-ORDER-005",
                "user": users["seed.sara@yalla.test"],
                "market": markets["حلويات البحر"],
                "status": Order.Status.ASSIGNED,
                "payment_method": "card",
                "items": [(variants["بقلاوة"][1], 2), (variants["بسبوسة بالعسل"][0], 1)],
                "offer": offers["حلويات البحر"],
                "offer_discount": Decimal("150.00"),
            },
            {
                "marker": "SEED-ORDER-006",
                "user": users["seed.nadir@yalla.test"],
                "market": markets["خيرات المنصورة"],
                "status": Order.Status.CANCELLED,
                "payment_method": "cash",
                "items": [(variants["عسل مصري"][0], 1)],
                "offer": offers["أسبوع المنتجات العضوية"],
                "offer_discount": Decimal("60.00"),
            },
            {
                "marker": "SEED-ORDER-007",
                "user": users["seed.nadir@yalla.test"],
                "market": markets["مخبزة الدلتا"],
                "status": Order.Status.DELIVERED,
                "payment_method": "card",
                "items": [(variants["خبز كامل"][1], 2), (variants["بريوش"][0], 3)],
                "offer": offers["توصيل مخبزة الدلتا"],
                "offer_discount": Decimal("80.00"),
            },
        ]

        for definition in definitions:
            subtotal = sum(
                variant.price * quantity
                for variant, quantity in definition["items"]
            )
            discount = definition["offer_discount"]
            order_scope = (
                Order.Scope.GENERAL
                if definition["market"].scope == Market.Scope.GENERAL
                else Order.Scope.SERVICE_CITY
            )
            if order_scope == Order.Scope.GENERAL:
                delivery_address = (
                    definition["user"]
                    .addresses.filter(
                        service_city__isnull=True,
                        delivery_area__isnull=True,
                        manual_city__isnull=False,
                        manual_area__isnull=False,
                    )
                    .first()
                    or definition["user"].addresses.order_by("-created_at").first()
                )
            else:
                delivery_address = (
                    definition["user"].addresses.filter(is_default=True).first()
                    or definition["user"].addresses.order_by("-created_at").first()
                )
            service_city = (
                definition["market"]
                .service_cities.filter(
                    pk=getattr(delivery_address, "service_city_id", None)
                )
                .first()
                or definition["market"].service_cities.order_by("id").first()
            )
            if order_scope == Order.Scope.GENERAL:
                service_city = None
            delivery_area = None
            delivery_type = Order.DeliveryType.DELIVERY
            delivery_price = None
            if (
                order_scope == Order.Scope.SERVICE_CITY
                and delivery_address
                and delivery_address.delivery_area_id
            ):
                address_area = delivery_address.delivery_area
                if (
                    address_area.is_active
                    and service_city is not None
                    and address_area.service_city_id == service_city.id
                ):
                    delivery_area = address_area
                    delivery_type = Order.DeliveryType.FIXED_AREA
                    delivery_price = delivery_area.delivery_price
            total = subtotal + (delivery_price or Decimal("0.00")) - discount
            order, _ = Order.objects.update_or_create(
                description=definition["marker"],
                defaults={
                    "user": definition["user"],
                    "market": definition["market"],
                    "order_scope": order_scope,
                    "service_city": service_city,
                    "delivery_area": delivery_area,
                    "delivery_type": delivery_type,
                    "payment_method": definition["payment_method"],
                    "discount": discount,
                    "status": definition["status"],
                    "review_status": Order.ReviewStatus.APPROVED,
                    "delivery_price": delivery_price,
                    "subtotal_price": subtotal,
                    "total_price": total,
                    "delivery_address": delivery_address,
                    "assigned_representative": self._representative_for_order(
                        users, definition["status"]
                    ),
                    "assigned_at": (
                        now - timedelta(hours=2)
                        if definition["status"]
                        in (
                            Order.Status.ASSIGNED,
                            Order.Status.PICKED_UP,
                            Order.Status.DELIVERED,
                            Order.Status.FAILED_DELIVERY,
                        )
                        else None
                    ),
                    "delivered_at": (
                        now - timedelta(minutes=30)
                        if definition["status"] == Order.Status.DELIVERED
                        else None
                    ),
                    "delivery_note": "بيانات تجريبية للتوصيل.",
                },
            )
            order.market_sections.all().delete()
            order.items.all().delete()
            order.order_offers.all().delete()
            section = OrderMarketSection.objects.create(
                order=order,
                market=definition["market"],
                subtotal_price=subtotal,
                discount=discount,
                pickup_status=(
                    OrderMarketSection.PickupStatus.PICKED_UP
                    if definition["status"]
                    in (
                        Order.Status.PICKED_UP,
                        Order.Status.DELIVERED,
                        Order.Status.FAILED_DELIVERY,
                    )
                    else OrderMarketSection.PickupStatus.PENDING
                ),
                picked_up_at=(
                    now - timedelta(hours=1)
                    if definition["status"]
                    in (
                        Order.Status.PICKED_UP,
                        Order.Status.DELIVERED,
                        Order.Status.FAILED_DELIVERY,
                    )
                    else None
                ),
            )
            for variant, quantity in definition["items"]:
                OrderItem.objects.create(
                    order=order,
                    section=section,
                    variant=variant,
                    quantity=quantity,
                    unit_price=variant.price,
                )
            OrderOffer.objects.create(
                order=order,
                section=section,
                offer=definition["offer"],
                discount_amount=discount,
            )
            self._sync_order_history(order, users)

    def _sync_order_history(self, order, users):
        order.history_events.all().delete()

        admin = users["seed.admin@yalla.test"]
        representative = order.assigned_representative

        record_order_event(
            order,
            OrderEvent.EventType.ORDER_CREATED,
            actor=order.user,
            to_status=Order.Status.PENDING,
            metadata={"seed": True},
        )

        if order.status == Order.Status.PENDING:
            return

        record_order_event(
            order,
            OrderEvent.EventType.REVIEW_APPROVED,
            actor=admin,
            from_status=Order.Status.PENDING,
            to_status=Order.Status.CONFIRMED,
            metadata={
                "seed": True,
                "review_status": Order.ReviewStatus.APPROVED,
            },
        )

        if order.status == Order.Status.CONFIRMED:
            return

        if order.status == Order.Status.CANCELLED:
            record_order_event(
                order,
                OrderEvent.EventType.CANCELLED,
                actor=admin,
                from_status=Order.Status.CONFIRMED,
                to_status=Order.Status.CANCELLED,
                metadata={"seed": True},
            )
            return

        if representative is None:
            return

        record_order_event(
            order,
            OrderEvent.EventType.ASSIGNED,
            actor=admin,
            from_status=Order.Status.CONFIRMED,
            to_status=Order.Status.ASSIGNED,
            metadata={
                "seed": True,
                "representative_id": representative.id,
            },
        )

        if order.status == Order.Status.ASSIGNED:
            return

        if order.status in (
            Order.Status.PICKED_UP,
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
        ):
            record_order_event(
                order,
                OrderEvent.EventType.STATUS_CHANGED,
                actor=representative,
                from_status=Order.Status.ASSIGNED,
                to_status=Order.Status.PICKED_UP,
                metadata={"seed": True},
            )

        if order.status == Order.Status.PICKED_UP:
            return

        if order.status in (
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
        ):
            record_order_event(
                order,
                OrderEvent.EventType.STATUS_CHANGED,
                actor=representative,
                from_status=Order.Status.PICKED_UP,
                to_status=order.status,
                metadata={"seed": True},
            )

    def _representative_for_order(self, users, status):
        if status in (
            Order.Status.PENDING,
            Order.Status.CONFIRMED,
            Order.Status.CANCELLED,
        ):
            return None
        email = (
            "seed.courier2@yalla.test"
            if status in (Order.Status.ASSIGNED, Order.Status.DELIVERED)
            else "seed.courier@yalla.test"
        )
        return users[email]

