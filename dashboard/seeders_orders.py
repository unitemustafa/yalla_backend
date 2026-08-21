from datetime import timedelta
from decimal import Decimal

from locations.models import Address
from markets.models import Market
from orders.models import Order, OrderItem, OrderMarketSection, OrderOffer


class DemoOrderSeederMixin:
    def _seed_orders(self, context, now):
        specs = [
            ("amina", "amina_salam", "مطبخ النيل العائلي", [("دجاج مشوي", 1), ("شوربة خضار", 2)], ["عرض الشاورما السريع"], Order.Status.PENDING, Order.ReviewStatus.PENDING_REVIEW, None, 0),
            ("amina", "amina_other", "سوق يلا الطازج", [("تفاح أحمر", 2), ("حليب طازج", 1)], [], Order.Status.PENDING, Order.ReviewStatus.PENDING_REVIEW, None, 0),
            ("sara", "sara_home", "مخبز إسكندرية الذهبي", [("فينو", 1), ("كرواسون بالشوكولاتة", 2)], ["مخبوزات الصباح"], Order.Status.PENDING, Order.ReviewStatus.PENDING_REVIEW, None, 1),
            ("karim", "karim_general", "سوق يلا العام", [("قفة رمضان", 1)], ["عرض الجمعة العام"], Order.Status.PENDING, Order.ReviewStatus.PENDING_REVIEW, None, 0),
            ("amina", "amina_home", "مطبخ النيل العائلي", [("كشري مخصوص", 3)], [], Order.Status.CONFIRMED, Order.ReviewStatus.APPROVED, None, 1),
            ("amina", "amina_home", "سوق يلا الطازج", [("طماطم", 2), ("بطاطس", 2)], ["خصم الخضار"], Order.Status.CONFIRMED, Order.ReviewStatus.APPROVED, None, 1),
            ("sara", "sara_home", "مخبز إسكندرية الذهبي", [("عيش بلدي", 5), ("بريوش", 1)], [], Order.Status.CONFIRMED, Order.ReviewStatus.APPROVED, None, 2),
            ("karim", "karim_general", "متجر العروض العامة", [("كرتونة رمضان", 1)], ["باقة البيت العامة"], Order.Status.CONFIRMED, Order.ReviewStatus.APPROVED, None, 3),
            ("sara", "sara_other", "مخبز إسكندرية الذهبي", [("كعك إسكندراني", 1)], ["إعلان افتتاح فرع سموحة"], Order.Status.CONFIRMED, Order.ReviewStatus.APPROVED, None, 5),
            ("amina", "amina_home", "مطبخ النيل العائلي", [("بيتزا عائلية", 1)], ["خصم البيتزا"], Order.Status.ASSIGNED, Order.ReviewStatus.APPROVED, "courier1", 0),
            ("amina", "amina_home", "سوق يلا الطازج", [("عصير برتقال", 3)], [], Order.Status.ASSIGNED, Order.ReviewStatus.APPROVED, "courier2", 0),
            ("amina", "amina_home", "مطبخ النيل العائلي", [("شاورما دجاج", 2)], [], Order.Status.PICKED_UP, Order.ReviewStatus.APPROVED, "courier2", 0),
            ("amina", "amina_home", "مطبخ النيل العائلي", [("برغر لحم", 2)], [], Order.Status.PICKED_UP, Order.ReviewStatus.APPROVED, "courier2", 0),
            ("amina", "amina_home", "سوق يلا الطازج", [("موز", 2), ("خيار", 1)], [], Order.Status.DELIVERED, Order.ReviewStatus.APPROVED, "courier1", 0),
            ("sara", "sara_home", "مخبز إسكندرية الذهبي", [("باغيت", 2)], ["عرض مخبز منتهي"], Order.Status.DELIVERED, Order.ReviewStatus.APPROVED, "courier3", 2),
            ("karim", "karim_general", "سوق يلا العام", [("مياه معدنية", 2), ("أرز مصري", 1)], [], Order.Status.DELIVERED, Order.ReviewStatus.APPROVED, None, 4),
            ("karim", "karim_home", "صيدلية الحياة", [("فيتامين C", 1), ("معقم يدين", 1)], ["توصيل صيدلية مخفض"], Order.Status.DELIVERED, Order.ReviewStatus.APPROVED, None, 10),
            ("amina", "amina_home", "مطبخ النيل العائلي", [("مكرونة بشاميل", 1)], [], Order.Status.FAILED_DELIVERY, Order.ReviewStatus.APPROVED, "courier1", 1),
            ("amina", "amina_home", "سوق يلا الطازج", [("تفاح أحمر", 1)], [], Order.Status.CANCELLED, Order.ReviewStatus.REJECTED, None, 6),
            ("sara", "sara_home", "مخبز إسكندرية الذهبي", [("كرواسون بالشوكولاتة", 1)], [], Order.Status.CANCELLED, Order.ReviewStatus.REJECTED, None, 8),
            ("karim", "karim_general", "متجر العروض العامة", [("عرض مدارس", 1), ("سكر أبيض", 2)], [], Order.Status.DELIVERED, Order.ReviewStatus.APPROVED, None, 20),
            ("amina", "amina_other", "مطبخ النيل العائلي", [("دجاج مشوي", 1)], ["باقة العائلة"], Order.Status.PENDING, Order.ReviewStatus.PENDING_REVIEW, None, 0),
        ]
        for spec in specs:
            order = self._create_order(context, now, *spec)
            context["orders"].append(order)

        multi_specs = [
            (
                "karim",
                "karim_general",
                [
                    ("سوق يلا العام", [("مياه معدنية", 2)], ["عرض الجمعة العام"]),
                    ("متجر العروض العامة", [("كرتونة رمضان", 1)], ["باقة البيت العامة"]),
                ],
                Order.Status.PENDING,
                Order.ReviewStatus.PENDING_REVIEW,
                None,
                0,
                "طلب عام متعدد الأسواق إلى مصر الجديدة",
            ),
            (
                "karim",
                "karim_general",
                [
                    ("سوق يلا العام", [("أرز مصري", 1)], []),
                    ("متجر العروض العامة", [("عرض مدارس", 1)], []),
                ],
                Order.Status.PENDING,
                Order.ReviewStatus.PENDING_REVIEW,
                None,
                0,
                "طلب عام متعدد الأسواق بعنوان يدوي",
            ),
            (
                "amina",
                "amina_home",
                [
                    ("مطبخ النيل العائلي", [("دجاج مشوي", 1)], ["باقة العائلة"]),
                    ("سوق يلا الطازج", [("تفاح أحمر", 2)], ["خصم الخضار"]),
                ],
                Order.Status.CONFIRMED,
                Order.ReviewStatus.APPROVED,
                None,
                1,
                "طلب مدينة خدمة متعدد الأسواق",
            ),
        ]
        for spec in multi_specs:
            order = self._create_multi_market_order(context, now, *spec)
            context["orders"].append(order)

    def _create_multi_market_order(
        self,
        context,
        now,
        user_key,
        address_key,
        section_specs,
        status,
        review_status,
        courier_key,
        days_ago,
        description,
    ):
        user = context["users"][user_key]
        address = context["addresses"][address_key]
        representative = context["users"].get(courier_key) if courier_key else None
        first_market = context["markets"][section_specs[0][0]]
        order_scope = (
            Order.Scope.GENERAL
            if first_market.scope == Market.Scope.GENERAL
            else Order.Scope.SERVICE_CITY
        )
        service_city = (
            None
            if order_scope == Order.Scope.GENERAL
            else address.service_city
        )
        delivery_area = None
        delivery_type = Order.DeliveryType.DELIVERY
        delivery_price = None
        if order_scope == Order.Scope.SERVICE_CITY and address.delivery_area_id:
            delivery_area = address.delivery_area
            if (
                address.delivery_type == Address.DeliveryType.FIXED_AREA
                and delivery_area.is_active
                and delivery_area.service_city_id == service_city.id
            ):
                delivery_type = Order.DeliveryType.FIXED_AREA
                delivery_price = delivery_area.delivery_price
            else:
                delivery_area = None
        created_at = now - timedelta(days=days_ago, hours=days_ago % 5)
        approved_at = None
        rejected_at = None
        delivered_at = None
        approved_by = None
        rejected_by = None
        rejection_reason = ""
        assigned_at = None

        if review_status == Order.ReviewStatus.APPROVED:
            approved_by = context["users"]["admin"]
            approved_at = created_at + timedelta(minutes=20)
        if review_status == Order.ReviewStatus.REJECTED:
            rejected_by = context["users"]["admin"]
            rejected_at = created_at + timedelta(minutes=25)
            rejection_reason = "بيانات العنوان غير مكتملة في الطلب التجريبي."
        if representative is not None:
            assigned_at = created_at + timedelta(minutes=35)
        if status == Order.Status.DELIVERED:
            delivered_at = created_at + timedelta(hours=2)

        sections = []
        subtotal = Decimal("0.00")
        discount = Decimal("0.00")
        for market_name, item_specs, offer_titles in section_specs:
            market = context["markets"][market_name]
            items = []
            section_subtotal = Decimal("0.00")
            selected_product_totals = {}
            for product_name, quantity in item_specs:
                product = context["products"][(market_name, product_name)]
                variant = product.variants.order_by("price", "id").first()
                line_total = variant.price * quantity
                section_subtotal += line_total
                selected_product_totals[product.id] = (
                    selected_product_totals.get(product.id, Decimal("0.00"))
                    + line_total
                )
                items.append(
                    {
                        "variant": variant,
                        "quantity": quantity,
                        "unit_price": variant.price,
                    }
                )

            offers = []
            section_discount = Decimal("0.00")
            for title in offer_titles:
                offer = context["offers"][title]
                offer_base = Decimal("0.00")
                for product in offer.products.filter(market=market):
                    selected_total = selected_product_totals.get(product.id)
                    if selected_total is not None:
                        offer_base += selected_total
                        continue
                    variant = product.variants.order_by("price", "id").first()
                    if variant is None:
                        continue
                    offer_base += variant.price
                    section_subtotal += variant.price
                    items.append(
                        {
                            "variant": variant,
                            "quantity": 1,
                            "unit_price": variant.price,
                        }
                    )
                discount_amount = self._percentage_amount(
                    offer_base,
                    offer.discount,
                )
                section_discount += discount_amount
                offers.append({"offer": offer, "discount_amount": discount_amount})

            sections.append(
                {
                    "market": market,
                    "items": items,
                    "offers": offers,
                    "subtotal": section_subtotal,
                    "discount": section_discount,
                }
            )
            subtotal += section_subtotal
            discount += section_discount

        total = subtotal + (delivery_price or Decimal("0.00")) - discount
        if total < Decimal("0.00"):
            total = Decimal("0.00")

        order = Order.objects.create(
            user=user,
            delivery_address=address,
            assigned_representative=representative,
            market=first_market,
            order_scope=order_scope,
            service_city=service_city,
            delivery_area=delivery_area,
            delivery_type=delivery_type,
            payment_method="cash",
            discount=discount,
            description=description,
            status=status,
            review_status=review_status,
            delivery_price=delivery_price,
            subtotal_price=subtotal,
            total_price=total,
            assigned_at=assigned_at,
            delivered_at=delivered_at,
            delivery_note="يرجى الاتصال قبل الوصول.",
            approved_by=approved_by,
            approved_at=approved_at,
            rejected_by=rejected_by,
            rejected_at=rejected_at,
            rejection_reason=rejection_reason,
        )
        section_picked_up = status in {
            Order.Status.PICKED_UP,
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
        }
        for sort_order, section_data in enumerate(sections):
            section = OrderMarketSection.objects.create(
                order=order,
                market=section_data["market"],
                subtotal_price=section_data["subtotal"],
                discount=section_data["discount"],
                pickup_status=(
                    OrderMarketSection.PickupStatus.PICKED_UP
                    if section_picked_up
                    else OrderMarketSection.PickupStatus.PENDING
                ),
                picked_up_at=(
                    assigned_at + timedelta(minutes=20)
                    if section_picked_up and assigned_at
                    else None
                ),
                sort_order=sort_order,
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(order=order, section=section, **item)
                    for item in section_data["items"]
                ]
            )
            OrderOffer.objects.bulk_create(
                [
                    OrderOffer(order=order, section=section, **offer)
                    for offer in section_data["offers"]
                ]
            )

        Order.objects.filter(pk=order.pk).update(
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=45),
        )
        order.created_at = created_at
        order.updated_at = created_at + timedelta(minutes=45)
        return order

    def _create_order(
        self,
        context,
        now,
        user_key,
        address_key,
        market_name,
        item_specs,
        offer_titles,
        status,
        review_status,
        courier_key,
        days_ago,
    ):
        user = context["users"][user_key]
        address = context["addresses"][address_key]
        market = context["markets"][market_name]
        order_scope = (
            Order.Scope.GENERAL
            if market.scope == Market.Scope.GENERAL
            else Order.Scope.SERVICE_CITY
        )
        service_city = (
            None
            if order_scope == Order.Scope.GENERAL
            else address.service_city
        )
        delivery_area = None
        delivery_type = Order.DeliveryType.DELIVERY
        delivery_price = None
        if order_scope == Order.Scope.SERVICE_CITY and address.delivery_area_id:
            delivery_area = address.delivery_area
            if (
                address.delivery_type == Address.DeliveryType.FIXED_AREA
                and delivery_area.is_active
                and delivery_area.service_city_id == service_city.id
            ):
                delivery_type = Order.DeliveryType.FIXED_AREA
                delivery_price = delivery_area.delivery_price
            else:
                delivery_area = None
        representative = context["users"].get(courier_key) if courier_key else None
        created_at = now - timedelta(days=days_ago, hours=days_ago % 5)
        approved_at = None
        rejected_at = None
        delivered_at = None
        approved_by = None
        rejected_by = None
        rejection_reason = ""
        assigned_at = None

        if review_status == Order.ReviewStatus.APPROVED:
            approved_by = context["users"]["admin"]
            approved_at = created_at + timedelta(minutes=20)
        if review_status == Order.ReviewStatus.REJECTED:
            rejected_by = context["users"]["admin"]
            rejected_at = created_at + timedelta(minutes=25)
            rejection_reason = "بيانات العنوان غير مكتملة في الطلب التجريبي."
        if representative is not None:
            assigned_at = created_at + timedelta(minutes=35)
        if status == Order.Status.DELIVERED:
            delivered_at = created_at + timedelta(hours=2)

        items = []
        subtotal = Decimal("0.00")
        for product_name, quantity in item_specs:
            product = context["products"][(market_name, product_name)]
            variant = product.variants.order_by("price", "id").first()
            line_total = variant.price * quantity
            subtotal += line_total
            items.append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "unit_price": variant.price,
                }
            )

        offers = []
        for title in offer_titles:
            offer = context["offers"][title]
            offer_products = list(offer.products.filter(market=market))
            offer_base = Decimal("0.00")
            for product in offer_products:
                variant = product.variants.order_by("price", "id").first()
                if variant:
                    offer_base += variant.price
            discount_amount = self._percentage_amount(
                min(offer_base or subtotal, subtotal),
                offer.discount,
            )
            offers.append({"offer": offer, "discount_amount": discount_amount})

        discount = sum((item["discount_amount"] for item in offers), Decimal("0.00"))
        total = subtotal + (delivery_price or Decimal("0.00")) - discount
        if total < Decimal("0.00"):
            total = Decimal("0.00")

        order = Order.objects.create(
            user=user,
            delivery_address=address,
            assigned_representative=representative,
            market=market,
            order_scope=order_scope,
            service_city=service_city,
            delivery_area=delivery_area,
            delivery_type=delivery_type,
            payment_method="cash",
            discount=discount,
            description=f"طلب تجريبي من {market.name}",
            status=status,
            review_status=review_status,
            delivery_price=delivery_price,
            subtotal_price=subtotal,
            total_price=total,
            assigned_at=assigned_at,
            delivered_at=delivered_at,
            delivery_note="يرجى الاتصال قبل الوصول.",
            approved_by=approved_by,
            approved_at=approved_at,
            rejected_by=rejected_by,
            rejected_at=rejected_at,
            rejection_reason=rejection_reason,
        )
        section_picked_up = status in {
            Order.Status.PICKED_UP,
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
        }
        section = OrderMarketSection.objects.create(
            order=order,
            market=market,
            subtotal_price=subtotal,
            discount=discount,
            pickup_status=(
                OrderMarketSection.PickupStatus.PICKED_UP
                if section_picked_up
                else OrderMarketSection.PickupStatus.PENDING
            ),
            picked_up_at=(
                assigned_at + timedelta(minutes=20)
                if section_picked_up and assigned_at
                else None
            ),
            sort_order=0,
        )
        OrderItem.objects.bulk_create(
            [OrderItem(order=order, section=section, **item) for item in items]
        )
        OrderOffer.objects.bulk_create(
            [OrderOffer(order=order, section=section, **item) for item in offers]
        )
        Order.objects.filter(pk=order.pk).update(
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=45),
        )
        order.created_at = created_at
        order.updated_at = created_at + timedelta(minutes=45)
        return order
