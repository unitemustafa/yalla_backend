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
from locations.models import Address, DeliveryArea
from markets.models import Market, MarketClassification
from offers.models import Offer
from orders.models import Order, OrderItem, OrderOffer

User = get_user_model()


class Command(BaseCommand):
    help = "Create idempotent fake data for all Yalla project tables."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        users = self._seed_users(now)
        self._seed_otps(users, now)
        areas = self._seed_locations(users)
        CourierProfile.objects.update_or_create(
            user=users["seed.courier@yalla.test"],
            defaults={
                "vehicle_type": "Motorcycle",
                "plate_number": "YH-1004",
                "delivery_area": next(iter(areas.values())),
                "max_active_orders": 3,
                "is_available": True,
            },
        )
        markets = self._seed_markets(areas)
        catalog = self._seed_catalog(markets)
        additions = self._seed_additions(catalog["products"])
        offers = self._seed_offers(markets, catalog["products"], now)
        self._seed_orders(users, markets, catalog["variants"], offers)

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
            f"{len(additions)} additions, {len(offers)} offers."
        )

    def _seed_users(self, now):
        definitions = [
            {
                "email": "seed.admin@yalla.test",
                "username": "seed_admin",
                "first_name": "يلا",
                "last_name": "مشرف",
                "phone": "+213555100001",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
            {
                "email": "seed.amina@yalla.test",
                "username": "seed_amina",
                "first_name": "أمينة",
                "last_name": "بن سالم",
                "phone": "+213555100002",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.karim@yalla.test",
                "username": "seed_karim",
                "first_name": "كريم",
                "last_name": "منصوري",
                "phone": "+213555100003",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
            {
                "email": "seed.courier@yalla.test",
                "username": "seed_courier",
                "first_name": "سفيان",
                "last_name": "مندوب",
                "phone": "+213555100004",
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
                "phone": "+213555100005",
                "role": User.Role.CLIENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": False,
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
        area_definitions = [
            ("وسط الجزائر", "250.00", "36.7538000", "3.0588000", "8.00"),
            ("باب الزوار", "300.00", "36.7167000", "3.1833000", "6.50"),
            ("وسط وهران", "280.00", "35.6969000", "-0.6331000", "7.00"),
        ]
        areas = {}
        for name, price, latitude, longitude, radius in area_definitions:
            area, _ = DeliveryArea.objects.update_or_create(
                name=name,
                defaults={
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
                "36.7525000",
                "3.0419000",
                True,
            ),
            (
                users["seed.amina@yalla.test"],
                "العمل",
                "36.7110000",
                "3.1810000",
                False,
            ),
            (
                users["seed.karim@yalla.test"],
                "المنزل",
                "35.7002000",
                "-0.6401000",
                True,
            ),
        ]
        for user, name, latitude, longitude, is_default in addresses:
            Address.objects.update_or_create(
                user=user,
                name=name,
                defaults={
                    "latitude": Decimal(latitude),
                    "longitude": Decimal(longitude),
                    "is_default": is_default,
                },
            )
        return areas

    def _seed_markets(self, areas):
        classifications = {}
        for name in ("سوبرماركت", "مطعم", "مخبزة"):
            obj, _ = MarketClassification.objects.get_or_create(name=name)
            classifications[name] = obj

        definitions = [
            (
                "سوق يلا الطازج",
                "وسط الجزائر",
                "سوبرماركت",
                ["وسط الجزائر", "باب الزوار"],
            ),
            (
                "مطبخ أطلس العائلي",
                "باب الزوار",
                "مطعم",
                ["وسط الجزائر", "باب الزوار"],
            ),
            (
                "مخبزة وهران الذهبية",
                "وسط وهران",
                "مخبزة",
                ["وسط وهران"],
            ),
        ]
        markets = {}
        for name, branch, classification, area_names in definitions:
            market, _ = Market.objects.update_or_create(
                name=name,
                branch=branch,
                defaults={
                    "classification": classifications[classification],
                    "status": Market.Status.ACTIVE,
                },
            )
            market.delivery_areas.set([areas[name] for name in area_names])
            markets[name] = market
        return markets

    def _seed_catalog(self, markets):
        grocery, _ = CategoryClassification.objects.get_or_create(name="بقالة")
        food, _ = CategoryClassification.objects.get_or_create(name="أكل جاهز")

        category_definitions = [
            ("خضر وفواكه", grocery, "produce", "فواكه وخضر طازجة"),
            ("مشروبات", grocery, "beverage", "مشروبات باردة ومعلبة"),
            ("مخبوزات", food, "bakery", "خبز ومخبوزات يومية"),
            ("وجبات", food, "meal", "وجبات جاهزة للأكل"),
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
            ("كسكس بالدجاج", "مطبخ أطلس العائلي", "وجبات", "850.00"),
            ("شوربة خضار", "مطبخ أطلس العائلي", "وجبات", "420.00"),
            ("دجاج مشوي", "مطبخ أطلس العائلي", "وجبات", "980.00"),
            ("خبز باغيت تقليدي", "مخبزة وهران الذهبية", "مخبوزات", "60.00"),
            ("كرواسون بالشوكولاتة", "مخبزة وهران الذهبية", "مخبوزات", "140.00"),
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
                ["كسكس بالدجاج", "شوربة خضار"],
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
                ["كسكس بالدجاج", "شوربة خضار"],
            ),
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
                Offer.OfferType.DISCOUNT,
                "10.00",
                ["تفاح أحمر", "موز"],
            ),
            (
                "عرض عشاء العائلة",
                "مطبخ أطلس العائلي",
                Offer.OfferType.PACKAGE,
                "15.00",
                ["كسكس بالدجاج", "شوربة خضار"],
            ),
            (
                "أساسيات الانتعاش",
                "سوق يلا الطازج",
                Offer.OfferType.DELIVERY,
                "8.00",
                ["مياه معدنية", "عصير برتقال"],
            ),
            (
                "غداء الجزائر السريع",
                "مطبخ أطلس العائلي",
                Offer.OfferType.FLASH,
                "12.00",
                ["دجاج مشوي", "شوربة خضار"],
            ),
            (
                "عرض المخبزة الصباحي",
                "مخبزة وهران الذهبية",
                Offer.OfferType.FLASH,
                "12.00",
                ["خبز باغيت تقليدي", "كرواسون بالشوكولاتة"],
            ),
        ]
        offers = {}
        for title, market_name, offer_type, discount, product_names in definitions:
            offer, _ = Offer.objects.update_or_create(
                market=markets[market_name],
                title=title,
                defaults={
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
            offers[title] = offer
        return offers

    def _seed_orders(self, users, markets, variants, offers):
        definitions = [
            {
                "marker": "SEED-ORDER-001",
                "user": users["seed.amina@yalla.test"],
                "market": markets["سوق يلا الطازج"],
                "status": Order.Status.DELIVERED,
                "payment_method": "cash",
                "delivery_price": Decimal("250.00"),
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
                "market": markets["مطبخ أطلس العائلي"],
                "status": Order.Status.UNDER_PREPARATION,
                "payment_method": "card",
                "delivery_price": Decimal("300.00"),
                "items": [
                    (variants["كسكس بالدجاج"][0], 1),
                    (variants["شوربة خضار"][0], 2),
                ],
                "offer": offers["عرض عشاء العائلة"],
                "offer_discount": Decimal("180.00"),
            },
            {
                "marker": "SEED-ORDER-003",
                "user": users["seed.amina@yalla.test"],
                "market": markets["مخبزة وهران الذهبية"],
                "status": Order.Status.PENDING,
                "payment_method": "cash",
                "delivery_price": Decimal("280.00"),
                "items": [
                    (variants["خبز باغيت تقليدي"][1], 1),
                    (variants["كرواسون بالشوكولاتة"][0], 4),
                ],
                "offer": offers["عرض المخبزة الصباحي"],
                "offer_discount": Decimal("75.00"),
            },
        ]

        for definition in definitions:
            subtotal = sum(
                variant.price * quantity
                for variant, quantity in definition["items"]
            )
            discount = definition["offer_discount"]
            total = subtotal + definition["delivery_price"] - discount
            order, _ = Order.objects.update_or_create(
                description=definition["marker"],
                defaults={
                    "user": definition["user"],
                    "market": definition["market"],
                    "payment_method": definition["payment_method"],
                    "discount": discount,
                    "status": definition["status"],
                    "delivery_price": definition["delivery_price"],
                    "subtotal_price": subtotal,
                    "total_price": total,
                    "delivery_address": definition["user"].addresses.filter(
                        is_default=True
                    ).first()
                    or definition["user"].addresses.order_by("-created_at").first(),
                },
            )
            order.items.all().delete()
            for variant, quantity in definition["items"]:
                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    quantity=quantity,
                    unit_price=variant.price,
                )
            OrderOffer.objects.update_or_create(
                order=order,
                offer=definition["offer"],
                defaults={"discount_amount": discount},
            )
