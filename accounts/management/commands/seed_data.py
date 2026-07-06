from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CourierProfile, OneTimePassword
from catalog.models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductAttributeValue,
    ProductCategory,
    ProductVariant,
    VariantAttributeValue,
)
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from offers.models import Offer
from orders.models import Order, OrderItem, OrderMarketSection, OrderOffer

User = get_user_model()


class Command(BaseCommand):
    help = "Create idempotent fake data for all Yalla project tables."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        users = self._seed_users(now)
        self._seed_otps(users, now)
        areas = self._seed_locations(users)
        self._seed_courier_profiles(users, areas)
        markets = self._seed_markets(areas)
        catalog = self._seed_catalog(markets)
        additions = self._seed_additions(catalog["products"])
        offers = self._seed_offers(markets, catalog["products"], now)
        self._seed_orders(users, markets, catalog["variants"], offers, now)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed data ready. Test password: SeedPass1! "
                "| pending OTP: 123456"
            )
        )
        self.stdout.write(
            "Created/updated: "
            f"{len(users)} users, {len(areas)} delivery areas, "
            f"{len(markets)} markets, {len(catalog['products'])} products, "
            f"{sum(len(value) for value in catalog['variants'].values())} variants, "
            f"{len(additions)} additions, {len(offers)} offers, "
            f"{Order.objects.filter(description__startswith='SEED-ORDER-').count()} orders."
        )

    def _seed_users(self, now):
        definitions = [
            {
                "email": "seed.admin@yalla.test",
                "username": "seed_admin",
                "first_name": "يلا",
                "last_name": "مشرف",
                "phone": "+201001000001",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
            {
                "email": "seed.amina@yalla.test",
                "username": "seed_amina",
                "first_name": "أمينة",
                "last_name": "حسن",
                "phone": "+201001000002",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.karim@yalla.test",
                "username": "seed_karim",
                "first_name": "كريم",
                "last_name": "محمود",
                "phone": "+201001000003",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.courier@yalla.test",
                "username": "seed_courier",
                "first_name": "أحمد",
                "last_name": "مندوب",
                "phone": "+201001000004",
                "role": User.Role.REPRESENTATIVE,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.pending@yalla.test",
                "username": "seed_pending",
                "first_name": "زبون",
                "last_name": "قيد التفعيل",
                "phone": "+201001000005",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": False,
            },
            {
                "email": "seed.sara@yalla.test",
                "username": "seed_sara",
                "first_name": "سارة",
                "last_name": "عادل",
                "phone": "+201001000006",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.nadir@yalla.test",
                "username": "seed_nadir",
                "first_name": "نذير",
                "last_name": "إبراهيم",
                "phone": "+201001000007",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.courier2@yalla.test",
                "username": "seed_courier2",
                "first_name": "محمود",
                "last_name": "سائق",
                "phone": "+201001000008",
                "role": User.Role.REPRESENTATIVE,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.courier3@yalla.test",
                "username": "seed_courier3",
                "first_name": "ليلى",
                "last_name": "سائقة",
                "phone": "+201001000009",
                "role": User.Role.REPRESENTATIVE,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        ]
        users = {}
        for definition in definitions:
            email = definition["email"]
            defaults = {
                **definition,
                "terms_accepted": True,
                "terms_accepted_at": now,
                "privacy_policy_version": "seed-v1",
            }
            defaults.pop("email")
            user, _ = User.objects.update_or_create(
                email=email,
                defaults=defaults,
            )
            user.set_password("SeedPass1!")
            user.save(update_fields=["password"])
            users[email] = user
        return users

    def _seed_otps(self, users, now):
        pending = users["seed.pending@yalla.test"]
        OneTimePassword.objects.update_or_create(
            user=pending,
            purpose=OneTimePassword.Purpose.REGISTRATION,
            used_at__isnull=True,
            defaults={
                "code_hash": make_password("123456"),
                "expires_at": now + timedelta(hours=1),
                "attempts": 0,
            },
        )

        client = users["seed.amina@yalla.test"]
        otp, _ = OneTimePassword.objects.get_or_create(
            user=client,
            purpose=OneTimePassword.Purpose.PASSWORD_RESET,
            used_at__isnull=False,
            defaults={
                "code_hash": make_password("654321"),
                "expires_at": now - timedelta(hours=1),
                "attempts": 0,
                "used_at": now - timedelta(hours=2),
            },
        )
        if otp.used_at is None:
            otp.used_at = now - timedelta(hours=2)
            otp.save(update_fields=["used_at"])

    def _seed_locations(self, users):
        city_definitions = [
            ("القاهرة", "30.0444000", "31.2357000", "28.00", "45.00"),
            ("الجيزة", "30.0131000", "31.2089000", "22.00", "50.00"),
            ("الإسكندرية", "31.2001000", "29.9187000", "24.00", "55.00"),
            ("المنصورة", "31.0409000", "31.3785000", "18.00", "40.00"),
        ]
        cities = {}
        for name, latitude, longitude, radius, delivery_price in city_definitions:
            city, _ = ServiceCity.objects.update_or_create(
                name=name,
                defaults={
                    "center_latitude": Decimal(latitude),
                    "center_longitude": Decimal(longitude),
                    "radius_km": Decimal(radius),
                    "delivery_price": Decimal(delivery_price),
                    "is_active": True,
                },
            )
            cities[name] = city

        area_definitions = [
            (
                "وسط القاهرة",
                "القاهرة",
                "45.00",
                "30.0444000",
                "31.2357000",
                "8.00",
            ),
            (
                "مدينة نصر",
                "القاهرة",
                "45.00",
                "30.0561000",
                "31.3300000",
                "6.50",
            ),
            (
                "الدقي",
                "الجيزة",
                "50.00",
                "30.0384000",
                "31.2123000",
                "7.00",
            ),
            ("الهرم", "الجيزة", "55.00", "29.9888000", "31.1477000", "6.00"),
            ("سموحة", "الإسكندرية", "55.00", "31.2140000", "29.9540000", "7.00"),
            ("سيدي جابر", "الإسكندرية", "58.00", "31.2188000", "29.9423000", "6.00"),
            ("حي الجامعة", "المنصورة", "40.00", "31.0379000", "31.3576000", "7.00"),
            ("توريل", "المنصورة", "42.00", "31.0483000", "31.3939000", "6.00"),
        ]
        areas = {}
        for name, city_name, price, latitude, longitude, radius in area_definitions:
            area, _ = DeliveryArea.objects.update_or_create(
                name=name,
                defaults={
                    "service_city": cities[city_name],
                    "delivery_price": Decimal(price),
                    "center_latitude": Decimal(latitude),
                    "center_longitude": Decimal(longitude),
                    "radius_km": Decimal(radius),
                    "is_active": True,
                },
            )
            areas[name] = area

        addresses = [
            (
                users["seed.amina@yalla.test"],
                "المنزل",
                "30.0444000",
                "31.2357000",
                "القاهرة",
                "وسط القاهرة",
                True,
            ),
            (
                users["seed.amina@yalla.test"],
                "العمل",
                "30.0561000",
                "31.3300000",
                "القاهرة",
                "مدينة نصر",
                False,
            ),
            (
                users["seed.karim@yalla.test"],
                "المنزل",
                "30.0384000",
                "31.2123000",
                "الجيزة",
                "الدقي",
                True,
            ),
            (
                users["seed.courier@yalla.test"],
                "منطقة المندوب",
                "30.0444000",
                "31.2357000",
                "القاهرة",
                "وسط القاهرة",
                True,
            ),
            (users["seed.sara@yalla.test"], "المنزل", "31.2140000", "29.9540000", "الإسكندرية", "سموحة", True),
            (users["seed.sara@yalla.test"], "الجامعة", "31.2188000", "29.9423000", "الإسكندرية", "سيدي جابر", False),
            (users["seed.nadir@yalla.test"], "المنزل", "31.0379000", "31.3576000", "المنصورة", "حي الجامعة", True),
            (users["seed.courier2@yalla.test"], "منطقة المندوب", "29.9888000", "31.1477000", "الجيزة", "الهرم", True),
            (users["seed.courier3@yalla.test"], "منطقة المندوب", "31.2140000", "29.9540000", "الإسكندرية", "سموحة", True),
        ]
        for user, name, latitude, longitude, city_name, area_name, is_default in addresses:
            delivery_area = areas[area_name]
            Address.objects.update_or_create(
                user=user,
                name=name,
                defaults={
                    "latitude": Decimal(latitude),
                    "longitude": Decimal(longitude),
                    "service_city": cities[city_name],
                    "delivery_area": delivery_area,
                    "delivery_type": Address.DeliveryType.FIXED_AREA,
                    "is_default": is_default,
                },
            )
        Address.objects.update_or_create(
            user=users["seed.amina@yalla.test"],
            name="عنوان عام",
            defaults={
                "details": "شارع الثورة بجوار بنزينة التعاون",
                "manual_city": "القاهرة",
                "manual_area": "مصر الجديدة",
                "latitude": Decimal("30.0860000"),
                "longitude": Decimal("31.3300000"),
                "service_city": None,
                "delivery_area": None,
                "delivery_type": Address.DeliveryType.DELIVERY,
                "is_default": False,
            },
        )
        return areas

    def _seed_courier_profiles(self, users, areas):
        definitions = [
            ("seed.courier@yalla.test", "Motorcycle", "YH-1004", "وسط القاهرة", 3, True),
            ("seed.courier2@yalla.test", "Scooter", "YH-1008", "الهرم", 4, True),
            ("seed.courier3@yalla.test", "Car", "YH-1009", "سموحة", 5, False),
        ]
        for email, vehicle, plate, area, maximum, available in definitions:
            CourierProfile.objects.update_or_create(
                user=users[email],
                defaults={
                    "vehicle_type": vehicle,
                    "plate_number": plate,
                    "delivery_area": areas[area],
                    "service_city": areas[area].service_city,
                    "max_active_orders": maximum,
                    "is_available": available,
                },
            )

    def _seed_markets(self, areas):
        classifications = {}
        classification_types = {
            "سوبرماركت": MarketClassification.ClassificationType.POPULAR,
            "مطعم": MarketClassification.ClassificationType.FEATURED,
            "مخبزة": MarketClassification.ClassificationType.NORMAL,
            "حلويات": MarketClassification.ClassificationType.NORMAL,
            "منتجات عضوية": MarketClassification.ClassificationType.NORMAL,
        }
        for name, classification_type in classification_types.items():
            obj, _ = MarketClassification.objects.update_or_create(
                name=name,
                defaults={"classification_type": classification_type},
            )
            classifications[name] = obj

        definitions = [
            (
                "سوق يلا الطازج",
                "وسط القاهرة",
                "سوبرماركت",
                ["وسط القاهرة", "مدينة نصر"],
                Market.Scope.GENERAL,
            ),
            (
                "مطبخ النيل العائلي",
                "مدينة نصر",
                "مطعم",
                ["وسط القاهرة", "مدينة نصر"],
                Market.Scope.SERVICE_CITY,
            ),
            (
                "مخبزة الجيزة الذهبية",
                "الدقي",
                "مخبزة",
                ["الدقي"],
                Market.Scope.SERVICE_CITY,
            ),
            ("متجر الأهرام", "الهرم", "سوبرماركت", ["الدقي", "الهرم"], Market.Scope.SERVICE_CITY),
            ("نكهة إسكندرية", "سموحة", "مطعم", ["سموحة", "سيدي جابر"], Market.Scope.SERVICE_CITY),
            ("حلويات البحر", "سيدي جابر", "حلويات", ["سموحة", "سيدي جابر"], Market.Scope.SERVICE_CITY),
            ("خيرات المنصورة", "حي الجامعة", "منتجات عضوية", ["حي الجامعة", "توريل"], Market.Scope.SERVICE_CITY),
            ("مخبزة الدلتا", "توريل", "مخبزة", ["حي الجامعة", "توريل"], Market.Scope.SERVICE_CITY),
        ]
        markets = {}
        for name, branch, classification, area_names, scope in definitions:
            market, _ = Market.objects.update_or_create(
                name=name,
                branch=branch,
                defaults={
                    "classification": classifications[classification],
                    "scope": scope,
                    "status": Market.Status.ACTIVE,
                },
            )
            if scope == Market.Scope.GENERAL:
                market.delivery_areas.clear()
                market.service_cities.clear()
            else:
                market.delivery_areas.set([areas[name] for name in area_names])
                market.service_cities.set(
                    {areas[name].service_city_id for name in area_names}
                )
            markets[name] = market
        return markets

    def _seed_catalog(self, markets):
        grocery, _ = CategoryClassification.objects.get_or_create(name="بقالة")
        food, _ = CategoryClassification.objects.get_or_create(name="أكل جاهز")
        sweets, _ = CategoryClassification.objects.get_or_create(name="حلويات")

        category_definitions = [
            ("خضر وفواكه", grocery, "produce", "فواكه وخضر طازجة"),
            ("مشروبات", grocery, "beverage", "مشروبات باردة ومعلبة"),
            ("مخبوزات", food, "bakery", "خبز ومخبوزات يومية"),
            ("وجبات", food, "meal", "وجبات جاهزة للأكل"),
            ("حلويات", sweets, "dessert", "حلويات تقليدية وعصرية"),
            ("منتجات عضوية", grocery, "organic", "منتجات طبيعية وعضوية"),
        ]
        categories = {}
        for name, classification, category_type, description in category_definitions:
            category, _ = ProductCategory.objects.update_or_create(
                name=name,
                classification=classification,
                defaults={"type": category_type, "description": description},
            )
            categories[name] = category

        attribute_definitions = {
            "خضر وفواكه": ("الوحدة", ["500 غ", "1 كغ"]),
            "مشروبات": ("الحجم", ["330 مل", "1 لتر"]),
            "مخبوزات": ("العبوة", ["قطعة واحدة", "عبوة 4 قطع"]),
            "وجبات": ("الحصة", ["عادية", "عائلية"]),
            "حلويات": ("العبوة", ["قطعتان", "علبة 6 قطع"]),
            "منتجات عضوية": ("الوزن", ["250 غ", "500 غ"]),
        }
        attributes = {}
        options = {}
        for category_name, (attribute_name, values) in attribute_definitions.items():
            attribute, _ = CategoryAttribute.objects.update_or_create(
                category=categories[category_name],
                name=attribute_name,
            )
            attributes[category_name] = attribute
            options[category_name] = []
            for value in values:
                option, _ = CategoryOption.objects.get_or_create(
                    attribute=attribute,
                    value=value,
                )
                options[category_name].append(option)

        product_definitions = [
            ("تفاح أحمر", "سوق يلا الطازج", "خضر وفواكه", "320.00"),
            ("موز", "سوق يلا الطازج", "خضر وفواكه", "240.00"),
            ("عصير برتقال", "سوق يلا الطازج", "مشروبات", "180.00"),
            ("حليب طازج", "سوق يلا الطازج", "مشروبات", "160.00"),
            ("مياه معدنية", "سوق يلا الطازج", "مشروبات", "70.00"),
            ("كشري بالدجاج", "مطبخ النيل العائلي", "وجبات", "850.00"),
            ("شوربة خضار", "مطبخ النيل العائلي", "وجبات", "420.00"),
            ("دجاج مشوي", "مطبخ النيل العائلي", "وجبات", "980.00"),
            ("عيش بلدي", "مخبزة الجيزة الذهبية", "مخبوزات", "60.00"),
            ("كرواسون بالشوكولاتة", "مخبزة الجيزة الذهبية", "مخبوزات", "140.00"),
            ("قهوة مطحونة", "متجر الأهرام", "مشروبات", "450.00"),
            ("تمر مصري", "متجر الأهرام", "خضر وفواكه", "600.00"),
            ("مكرونة إسكندراني", "نكهة إسكندرية", "وجبات", "900.00"),
            ("طاجن خضار", "نكهة إسكندرية", "وجبات", "780.00"),
            ("بقلاوة", "حلويات البحر", "حلويات", "500.00"),
            ("بسبوسة بالعسل", "حلويات البحر", "حلويات", "420.00"),
            ("عسل مصري", "خيرات المنصورة", "منتجات عضوية", "1200.00"),
            ("زيت زيتون", "خيرات المنصورة", "منتجات عضوية", "950.00"),
            ("خبز كامل", "مخبزة الدلتا", "مخبوزات", "90.00"),
            ("بريوش", "مخبزة الدلتا", "مخبوزات", "160.00"),
        ]
        products = {}
        variants = {}
        for index, (name, market_name, category_name, base_price) in enumerate(
            product_definitions,
            start=1,
        ):
            product, _ = Product.objects.update_or_create(
                market=markets[market_name],
                name=name,
                defaults={
                    "category": categories[category_name],
                    "description": f"منتج تجريبي: {name}.",
                    "discount": Decimal("0.00"),
                },
            )
            products[name] = product
            attribute = attributes[category_name]
            first_option, second_option = options[category_name]
            ProductAttributeValue.objects.update_or_create(
                product=product,
                attribute=attribute,
                defaults={"option": first_option},
            )

            product_variants = []
            for variant_index, option in enumerate(
                (first_option, second_option),
                start=1,
            ):
                variant, _ = ProductVariant.objects.update_or_create(
                    product=product,
                    sku=f"SEED-{index:02d}-{variant_index}",
                    defaults={
                        "price": Decimal(base_price)
                        * (Decimal("1.00") if variant_index == 1 else Decimal("1.75"))
                    },
                )
                VariantAttributeValue.objects.update_or_create(
                    variant=variant,
                    attribute=attribute,
                    defaults={"option": option},
                )
                product_variants.append(variant)
            variants[name] = product_variants

        return {"products": products, "variants": variants}

    def _seed_additions(self, products):
        classifications = {}
        for name in ("صلصات", "تغليف", "إضافات"):
            obj, _ = AdditionClassification.objects.get_or_create(name=name)
            classifications[name] = obj

        definitions = [
            (
                "صلصة الثوم",
                "صلصة الثوم",
                "صلصات",
                "80.00",
                ["كشري بالدجاج", "شوربة خضار"],
            ),
            (
                "كيس هدية",
                "كيس هدية",
                "تغليف",
                "50.00",
                ["تفاح أحمر", "عصير برتقال", "كرواسون بالشوكولاتة"],
            ),
            (
                "خبز إضافي",
                "خبز إضافي",
                "إضافات",
                "40.00",
                ["كشري بالدجاج", "شوربة خضار"],
            ),
            ("مكسرات", "مكسرات", "إضافات", "120.00", ["بقلاوة", "بسبوسة بالعسل"]),
            ("علبة فاخرة", "علبة فاخرة", "تغليف", "150.00", ["بقلاوة", "عسل مصري"]),
            ("عسل إضافي", "عسل إضافي", "صلصات", "90.00", ["بريوش", "بسبوسة بالعسل"]),
        ]
        additions = {}
        for english, arabic, classification, price, product_names in definitions:
            addition, _ = ProductAddition.objects.update_or_create(
                name_en=english,
                defaults={
                    "name_ar": arabic,
                    "classification": classifications[classification],
                    "price": Decimal(price),
                    "is_active": True,
                },
            )
            addition.products.set([products[name] for name in product_names])
            additions[english] = addition
        return additions

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
                "status": Order.Status.UNDER_PREPARATION,
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
                "status": Order.Status.READY,
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
                        if definition["status"] not in (Order.Status.PENDING, Order.Status.CANCELLED)
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
                        Order.Status.ON_THE_WAY,
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
                        Order.Status.ON_THE_WAY,
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

    def _representative_for_order(self, users, status):
        if status in (Order.Status.PENDING, Order.Status.CANCELLED):
            return None
        email = (
            "seed.courier2@yalla.test"
            if status in (Order.Status.READY, Order.Status.DELIVERED)
            else "seed.courier@yalla.test"
        )
        return users[email]
