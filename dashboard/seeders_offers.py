from datetime import timedelta
from decimal import Decimal

from markets.models import Market
from offers.models import Offer

from .seed_constants import ACTIVE_DAYS


class DemoOfferSeederMixin:
    def _seed_offers(self, context, now):
        def offer(
            title,
            market_name,
            product_names,
            offer_type,
            discount,
            status=Offer.Status.ACTIVE,
            scope=None,
            city_name=None,
            starts=-1,
            ends=14,
            use_limits=None,
            user_limit=None,
            with_image=False,
        ):
            market = context["markets"][market_name]
            scope = scope or market.scope
            service_city = context["cities"].get(city_name) if city_name else None
            created = Offer.objects.create(
                market=market,
                show_in_general=scope == Market.Scope.GENERAL,
                title=title,
                description=f"{title} متاح ضمن بيانات العرض التجريبية.",
                type=offer_type,
                discount=self._money(discount),
                start_time=now + timedelta(days=starts),
                end_time=now + timedelta(days=ends),
                active_days=ACTIVE_DAYS,
                use_limits=use_limits,
                user_limit=user_limit,
                status=status,
            )
            created.products.set(
                [context["products"][(market_name, name)] for name in product_names]
            )
            created.service_cities.set([service_city] if service_city is not None else [])
            if with_image:
                self._attach_image(created, "image", f"seed_offer_{created.id}.png")
            context["offers"][title] = created
            return created

        offer(
            "عرض الجمعة العام",
            "سوق يلا العام",
            ["مياه معدنية", "تمر مصري فاخر", "زيت زيتون"],
            Offer.OfferType.FLASH,
            "15.00",
            scope=Market.Scope.GENERAL,
            use_limits=100,
            user_limit=1,
            with_image=True,
        )
        offer(
            "باقة البيت العامة",
            "متجر العروض العامة",
            ["كرتونة رمضان", "باقة عناية"],
            Offer.OfferType.PACKAGE,
            "12.00",
            scope=Market.Scope.GENERAL,
        )
        offer(
            "توصيل عام مخفض",
            "سوق يلا العام",
            ["قفة رمضان"],
            Offer.OfferType.DELIVERY,
            "5.00",
            scope=Market.Scope.GENERAL,
        )
        offer(
            "باقة العائلة",
            "مطبخ النيل العائلي",
            ["دجاج مشوي", "شوربة خضار", "بيتزا عائلية"],
            Offer.OfferType.PACKAGE,
            "18.00",
            city_name="القاهرة",
            use_limits=50,
            user_limit=2,
            with_image=True,
        )
        offer(
            "عرض الشاورما السريع",
            "مطبخ النيل العائلي",
            ["شاورما دجاج", "برغر لحم"],
            Offer.OfferType.FLASH,
            "10.00",
            city_name="القاهرة",
        )
        offer(
            "خصم البيتزا",
            "مطبخ النيل العائلي",
            ["بيتزا عائلية"],
            Offer.OfferType.DISCOUNT,
            "15.00",
            city_name="القاهرة",
        )
        offer(
            "خصم الخضار",
            "سوق يلا الطازج",
            ["تفاح أحمر", "طماطم", "بطاطس"],
            Offer.OfferType.DISCOUNT,
            "8.00",
            city_name="القاهرة",
        )
        offer(
            "عصير اليوم",
            "سوق يلا الطازج",
            ["عصير برتقال", "حليب طازج"],
            Offer.OfferType.FLASH,
            "7.00",
            city_name="الجيزة",
        )
        offer(
            "مخبوزات الصباح",
            "مخبز إسكندرية الذهبي",
            ["عيش بلدي", "فينو", "بريوش"],
            Offer.OfferType.PACKAGE,
            "9.00",
            city_name="الإسكندرية",
            with_image=True,
        )
        offer(
            "إعلان افتتاح فرع سموحة",
            "مخبز إسكندرية الذهبي",
            ["كعك إسكندراني"],
            Offer.OfferType.ANNOUNCEMENT,
            "0.00",
            city_name="الإسكندرية",
        )
        offer(
            "حلويات الجمعة",
            "حلويات الدلتا",
            ["بقلاوة", "بسبوسة"],
            Offer.OfferType.FLASH,
            "11.00",
            city_name="المنصورة",
        )
        offer(
            "باقة الضيافة",
            "حلويات الدلتا",
            ["كنافة", "غريبة", "قطايف"],
            Offer.OfferType.PACKAGE,
            "13.00",
            city_name="طنطا",
        )
        offer(
            "توصيل صيدلية مخفض",
            "صيدلية الحياة",
            ["معقم يدين", "فيتامين C"],
            Offer.OfferType.DELIVERY,
            "6.00",
            city_name="الجيزة",
        )
        offer(
            "عرض عام غير نشط",
            "متجر العروض العامة",
            ["شاي أسوان"],
            Offer.OfferType.DISCOUNT,
            "10.00",
            status=Offer.Status.INACTIVE,
            scope=Market.Scope.GENERAL,
        )
        offer(
            "عرض مطبخ غير نشط",
            "مطبخ النيل العائلي",
            ["كشري مخصوص"],
            Offer.OfferType.FLASH,
            "10.00",
            status=Offer.Status.INACTIVE,
            city_name="القاهرة",
        )
        offer(
            "عرض صيدلية غير نشط",
            "صيدلية الحياة",
            ["كمامات"],
            Offer.OfferType.DISCOUNT,
            "10.00",
            status=Offer.Status.INACTIVE,
            city_name="الجيزة",
        )
        offer(
            "عرض رمضان المنتهي",
            "سوق يلا العام",
            ["أرز مصري"],
            Offer.OfferType.PACKAGE,
            "20.00",
            status=Offer.Status.EXPIRED,
            scope=Market.Scope.GENERAL,
            starts=-30,
            ends=-2,
        )
        offer(
            "عرض مخبز منتهي",
            "مخبز إسكندرية الذهبي",
            ["باغيت"],
            Offer.OfferType.DISCOUNT,
            "15.00",
            status=Offer.Status.EXPIRED,
            city_name="الإسكندرية",
            starts=-20,
            ends=-1,
        )
