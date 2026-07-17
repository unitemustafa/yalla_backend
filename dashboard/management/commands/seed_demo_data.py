import base64
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from accounts.models import CourierProfile, OneTimePassword, User
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
from notifications.models import Notification
from offers.models import Offer
from orders.models import Order, OrderItem, OrderMarketSection, OrderOffer


PASSWORD = "SeedPass1!"
ACTIVE_DAYS = [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
]

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Destructively reset and seed a rich local Egyptian demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Required. Delete all project/domain data before seeding.",
        )
        parser.add_argument(
            "--yes-delete-all",
            action="store_true",
            help="Required with --reset. Confirms destructive local/demo reset.",
        )
        parser.add_argument(
            "--force-production-risk",
            action="store_true",
            help="Allow destructive reset when DEBUG is false.",
        )
        parser.add_argument(
            "--no-media",
            action="store_true",
            help="Skip local placeholder image creation.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Reduce progress output.",
        )

    def handle(self, *args, **options):
        self.quiet = options["quiet"]
        self.no_media = options["no_media"]
        self.skipped = []

        if not options["reset"] or not options["yes_delete_all"]:
            raise CommandError(
                "Refusing to run. Use --reset --yes-delete-all for the "
                "destructive local/demo seed reset."
            )
        if not settings.DEBUG and not options["force_production_risk"]:
            raise CommandError(
                "Refusing to run because DEBUG is false. Add "
                "--force-production-risk only if this is a safe demo database."
            )

        self.stdout.write(
            self.style.WARNING(
                "DESTRUCTIVE RESET: deleting all project/domain data before "
                "creating the Egyptian demo dataset."
            )
        )

        self._delete_seed_media_files()
        with transaction.atomic():
            deleted = self._delete_project_data()
            self._reset_sequences()
            context = self._create_seed_data()
            assertions = self._assert_seed_data(context)

        self._print_summary(context, deleted, assertions)

    def _delete_project_data(self):
        delete_plan = [
            Notification,
            OrderOffer,
            OrderItem,
            OrderMarketSection,
            Order,
            Offer,
            ProductAddition,
            ProductAttributeValue,
            VariantAttributeValue,
            ProductVariant,
            Product,
            CategoryOption,
            CategoryAttribute,
            ProductCategory,
            CategoryClassification,
            AdditionClassification,
            Market,
            MarketClassification,
            Address,
            CourierProfile,
            OneTimePassword,
            User,
            DeliveryArea,
            ServiceCity,
        ]
        deleted = {}
        for model in delete_plan:
            count, _ = model.objects.all().delete()
            deleted[model.__name__] = count
        self._write("Deleted existing project/domain data.")
        return deleted

    def _delete_seed_media_files(self):
        media_root = Path(settings.MEDIA_ROOT)
        for folder in ("additions", "categories", "offers", "products"):
            directory = media_root / folder
            if not directory.exists():
                continue
            for path in directory.glob("seed_*.png"):
                path.unlink()
        self._write("Deleted old seed placeholder media files.")

    def _reset_sequences(self):
        models = [
            ServiceCity,
            DeliveryArea,
            User,
            CourierProfile,
            OneTimePassword,
            MarketClassification,
            Market,
            CategoryClassification,
            ProductCategory,
            CategoryAttribute,
            CategoryOption,
            AdditionClassification,
            ProductAddition,
            Product,
            ProductAttributeValue,
            ProductVariant,
            VariantAttributeValue,
            Offer,
            Order,
            OrderItem,
            OrderOffer,
            Notification,
        ]
        statements = connection.ops.sequence_reset_sql(no_style(), models)
        if not statements:
            return
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    def _create_seed_data(self):
        now = timezone.now()
        context = {
            "cities": {},
            "areas": {},
            "users": {},
            "market_classifications": {},
            "markets": {},
            "category_classifications": {},
            "categories": {},
            "attributes": {},
            "options": {},
            "addition_classifications": {},
            "additions": {},
            "products": {},
            "offers": {},
            "orders": [],
            "notifications": [],
            "credentials": [],
        }

        self._seed_locations(context)
        self._seed_users(context, now)
        self._seed_addresses(context)
        self._seed_market_classifications(context)
        self._seed_markets(context)
        self._seed_catalog(context)
        self._seed_products(context)
        self._seed_likes(context)
        self._seed_offers(context, now)
        self._seed_orders(context, now)
        self._seed_notifications(context, now)
        self._write("Created Egyptian demo data.")
        return context

    def _seed_locations(self, context):
        city_rows = [
            ("القاهرة", "30.0444000", "31.2357000", "28.00", "45.00"),
            ("الجيزة", "30.0131000", "31.2089000", "22.00", "50.00"),
            ("الإسكندرية", "31.2001000", "29.9187000", "24.00", "55.00"),
            ("المنصورة", "31.0409000", "31.3785000", "18.00", "40.00"),
            ("طنطا", "30.7865000", "31.0004000", "18.00", "38.00"),
        ]
        for name, lat, lon, radius, price in city_rows:
            context["cities"][name] = ServiceCity.objects.create(
                name=name,
                center_latitude=self._decimal(lat),
                center_longitude=self._decimal(lon),
                radius_km=self._decimal(radius),
                delivery_price=self._money(price),
                is_active=True,
            )

        area_rows = [
            ("القاهرة", "مدينة نصر", "30.0561000", "31.3300000", "8.00", "45.00"),
            ("القاهرة", "المعادي", "29.9602000", "31.2569000", "7.50", "50.00"),
            ("القاهرة", "مصر الجديدة", "30.0860000", "31.3300000", "7.00", "48.00"),
            ("القاهرة", "السلام", "30.1680000", "31.4100000", "6.50", "46.00"),
            ("الجيزة", "الدقي", "30.0384000", "31.2123000", "6.50", "50.00"),
            ("الجيزة", "المهندسين", "30.0571000", "31.2008000", "6.50", "52.00"),
            ("الجيزة", "الهرم", "29.9888000", "31.1477000", "9.00", "55.00"),
            ("الإسكندرية", "سموحة", "31.2140000", "29.9540000", "6.00", "55.00"),
            ("الإسكندرية", "سيدي جابر", "31.2188000", "29.9423000", "6.00", "58.00"),
            ("المنصورة", "حي الجامعة", "31.0379000", "31.3576000", "5.00", "40.00"),
            ("المنصورة", "توريل", "31.0483000", "31.3939000", "5.00", "42.00"),
            ("طنطا", "شارع البحر", "30.7907000", "30.9999000", "5.00", "38.00"),
            ("طنطا", "سيجر", "30.7993000", "30.9907000", "5.00", "40.00"),
        ]
        for city_name, name, lat, lon, radius, price in area_rows:
            area = DeliveryArea.objects.create(
                service_city=context["cities"][city_name],
                name=name,
                center_latitude=self._decimal(lat),
                center_longitude=self._decimal(lon),
                radius_km=self._decimal(radius),
                delivery_price=self._money(price),
                is_active=True,
            )
            context["areas"][(city_name, name)] = area

    def _seed_users(self, context, now):
        user_rows = [
            {
                "key": "admin",
                "email": "seed.admin@yalla.seed",
                "username": "seed_admin",
                "name": "مدير يلا",
                "phone": "+201001000001",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "key": "amina",
                "email": "seed.amina@yalla.seed",
                "username": "seed_amina",
                "name": "أمينة حسن",
                "phone": "+201001000002",
                "role": User.Role.CLIENT,
            },
            {
                "key": "karim",
                "email": "seed.karim@yalla.seed",
                "username": "seed_karim",
                "name": "كريم محمود",
                "phone": "+201001000003",
                "role": User.Role.CLIENT,
            },
            {
                "key": "sara",
                "email": "seed.sara@yalla.seed",
                "username": "seed_sara",
                "name": "سارة عادل",
                "phone": "+201001000010",
                "role": User.Role.CLIENT,
            },
            {
                "key": "courier1",
                "email": "seed.courier1@yalla.seed",
                "username": "seed_courier1",
                "name": "أحمد مندوب",
                "phone": "+201001000004",
                "role": User.Role.REPRESENTATIVE,
            },
            {
                "key": "courier2",
                "email": "seed.courier2@yalla.seed",
                "username": "seed_courier2",
                "name": "محمود مندوب",
                "phone": "+201001000005",
                "role": User.Role.REPRESENTATIVE,
            },
            {
                "key": "courier3",
                "email": "seed.courier3@yalla.seed",
                "username": "seed_courier3",
                "name": "ليلى سائقة",
                "phone": "+201001000006",
                "role": User.Role.REPRESENTATIVE,
            },
        ]
        for row in user_rows:
            first_name, last_name = self._name_parts(row["name"])
            user = User.objects.create(
                username=row["username"],
                email=row["email"],
                phone=row["phone"],
                first_name=first_name,
                last_name=last_name,
                role=row["role"],
                is_staff=row.get("is_staff", False),
                is_superuser=row.get("is_superuser", False),
                is_active=True,
                is_verified=True,
                terms_accepted=True,
                terms_accepted_at=now,
                privacy_policy_version="seed-2026",
            )
            user.set_password(PASSWORD)
            user.save(update_fields=["password"])
            context["users"][row["key"]] = user
            context["credentials"].append(
                {
                    "label": row["key"],
                    "email": row["email"],
                    "username": row["username"],
                    "password": PASSWORD,
                }
            )

        amina = context["users"]["amina"]
        amina.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        amina.market_region_service_city = context["cities"]["القاهرة"]
        amina.market_region_updated_at = now
        amina.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
                "updated_at",
            ]
        )

        karim = context["users"]["karim"]
        karim.market_region_mode = User.MarketRegionMode.GENERAL
        karim.market_region_service_city = None
        karim.market_region_updated_at = now
        karim.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
                "updated_at",
            ]
        )

        sara = context["users"]["sara"]
        sara.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        sara.market_region_service_city = context["cities"]["الإسكندرية"]
        sara.market_region_updated_at = now
        sara.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
                "updated_at",
            ]
        )

        CourierProfile.objects.create(
            user=context["users"]["courier1"],
            vehicle_type="دراجة نارية",
            plate_number="س ي د 1234",
            service_city=context["cities"]["القاهرة"],
            delivery_area=context["areas"][("القاهرة", "مدينة نصر")],
            max_active_orders=4,
            is_available=True,
        )
        CourierProfile.objects.create(
            user=context["users"]["courier2"],
            vehicle_type="سكوتر",
            plate_number="م ن د 4578",
            service_city=context["cities"]["القاهرة"],
            delivery_area=context["areas"][("القاهرة", "المعادي")],
            max_active_orders=3,
            is_available=True,
        )
        CourierProfile.objects.create(
            user=context["users"]["courier3"],
            vehicle_type="سيارة",
            plate_number="ا س ك 9012",
            service_city=context["cities"]["الإسكندرية"],
            delivery_area=context["areas"][("الإسكندرية", "سموحة")],
            max_active_orders=3,
            is_available=False,
        )

    def _seed_addresses(self, context):
        def create_address(
            user_key,
            name,
            details,
            city_name=None,
            area_name=None,
            delivery_type=Address.DeliveryType.DELIVERY,
            is_default=False,
            manual_city=None,
            manual_area=None,
            latitude=None,
            longitude=None,
        ):
            city = context["cities"].get(city_name) if city_name else None
            area = (
                context["areas"].get((city_name, area_name))
                if city_name and area_name
                else None
            )
            return Address.objects.create(
                user=context["users"][user_key],
                name=name,
                details=details,
                manual_city=manual_city,
                manual_area=manual_area,
                latitude=self._decimal(latitude) if latitude else None,
                longitude=self._decimal(longitude) if longitude else None,
                service_city=city,
                delivery_area=area,
                delivery_type=delivery_type,
                is_default=is_default,
                is_active=True,
            )

        context["addresses"] = {
            "amina_home": create_address(
                "amina",
                "المنزل",
                "مدينة نصر، قرب النادي، الدور الثاني",
                "القاهرة",
                "مدينة نصر",
                Address.DeliveryType.FIXED_AREA,
                True,
                latitude="30.0561000",
                longitude="31.3300000",
            ),
            "amina_other": create_address(
                "amina",
                "عنوان آخر",
                "القاهرة، منطقة غير مضافة، قرب الطريق الرئيسي",
                "القاهرة",
                None,
                Address.DeliveryType.DELIVERY,
                False,
                manual_area="منطقة غير مضافة",
                latitude="30.0130000",
                longitude="31.4280000",
            ),
            "amina_salam": create_address(
                "amina",
                "عنوان السلام",
                "مدينة السلام، شارع السوق، الدور الأول",
                "القاهرة",
                "السلام",
                Address.DeliveryType.FIXED_AREA,
                False,
                latitude="30.1680000",
                longitude="31.4100000",
            ),
            "karim_general": create_address(
                "karim",
                "عنوان عام",
                "شارع الثورة بجوار بنزينة التعاون",
                None,
                None,
                Address.DeliveryType.DELIVERY,
                True,
                manual_city="القاهرة",
                manual_area="مصر الجديدة",
                latitude="30.0860000",
                longitude="31.3300000",
            ),
            "karim_home": create_address(
                "karim",
                "المنزل",
                "الدقي، بجوار محطة المترو",
                "الجيزة",
                "الدقي",
                Address.DeliveryType.FIXED_AREA,
                False,
                latitude="30.0384000",
                longitude="31.2123000",
            ),
            "karim_heliopolis": create_address(
                "karim",
                "عنوان مصر الجديدة",
                "القاهرة، مصر الجديدة، شارع الميرغني",
                "القاهرة",
                "مصر الجديدة",
                Address.DeliveryType.FIXED_AREA,
                False,
                latitude="30.0860000",
                longitude="31.3300000",
            ),
            "karim_other": create_address(
                "karim",
                "عنوان آخر",
                "الهرم، منطقة غير محددة",
                "الجيزة",
                None,
                Address.DeliveryType.DELIVERY,
                False,
                manual_area="فيصل",
                latitude="29.9900000",
                longitude="31.1600000",
            ),
            "sara_home": create_address(
                "sara",
                "المنزل",
                "سموحة، قرب النادي، الدور الخامس",
                "الإسكندرية",
                "سموحة",
                Address.DeliveryType.FIXED_AREA,
                True,
                latitude="31.2140000",
                longitude="29.9540000",
            ),
            "sara_other": create_address(
                "sara",
                "عنوان آخر",
                "لوران، منطقة غير محددة",
                "الإسكندرية",
                None,
                Address.DeliveryType.DELIVERY,
                False,
                manual_area="لوران",
                latitude="31.2400000",
                longitude="29.9700000",
            ),
        }

    def _seed_market_classifications(self, context):
        rows = [
            ("سوبرماركت", MarketClassification.ClassificationType.FEATURED),
            ("مطعم", MarketClassification.ClassificationType.POPULAR),
            ("مخبز", MarketClassification.ClassificationType.NORMAL),
            ("حلويات", MarketClassification.ClassificationType.NORMAL),
            ("صيدلية", MarketClassification.ClassificationType.FEATURED),
            ("عام", MarketClassification.ClassificationType.NORMAL),
        ]
        for name, classification_type in rows:
            context["market_classifications"][name] = (
                MarketClassification.objects.create(
                    name=name,
                    classification_type=classification_type,
                )
            )

    def _seed_markets(self, context):
        def create_market(
            name,
            classification_name,
            scope,
            status=Market.Status.ACTIVE,
            city_names=None,
            area_keys=None,
            branch="",
        ):
            market = Market.objects.create(
                classification=context["market_classifications"][classification_name],
                name=name,
                branch=branch,
                scope=scope,
                status=status,
            )
            market.service_cities.set(
                [context["cities"][city_name] for city_name in city_names or []]
            )
            market.delivery_areas.set(
                [context["areas"][area_key] for area_key in area_keys or []]
            )
            context["markets"][name] = market
            return market

        create_market("سوق يلا العام", "سوبرماركت", Market.Scope.GENERAL)
        create_market("متجر العروض العامة", "عام", Market.Scope.GENERAL)
        create_market(
            "مطبخ النيل العائلي",
            "مطعم",
            Market.Scope.SERVICE_CITY,
            city_names=["القاهرة"],
            area_keys=[("القاهرة", "مدينة نصر"), ("القاهرة", "المعادي")],
            branch="مدينة نصر",
        )
        create_market(
            "سوق يلا الطازج",
            "سوبرماركت",
            Market.Scope.SERVICE_CITY,
            city_names=["القاهرة", "الجيزة"],
            area_keys=[
                ("القاهرة", "مدينة نصر"),
                ("الجيزة", "الدقي"),
                ("الجيزة", "المهندسين"),
            ],
            branch="فرع القاهرة والجيزة",
        )
        create_market(
            "مخبز إسكندرية الذهبي",
            "مخبز",
            Market.Scope.SERVICE_CITY,
            city_names=["الإسكندرية"],
            area_keys=[("الإسكندرية", "سموحة"), ("الإسكندرية", "سيدي جابر")],
            branch="سموحة",
        )
        create_market(
            "حلويات الدلتا",
            "حلويات",
            Market.Scope.SERVICE_CITY,
            city_names=["المنصورة", "طنطا"],
            area_keys=[("المنصورة", "حي الجامعة"), ("طنطا", "شارع البحر")],
            branch="الدلتا",
        )
        create_market(
            "صيدلية الحياة",
            "صيدلية",
            Market.Scope.SERVICE_CITY,
            city_names=["الجيزة"],
            area_keys=[("الجيزة", "الدقي"), ("الجيزة", "الهرم")],
            branch="الدقي",
        )
        create_market(
            "بقالة هادئة بلا عروض",
            "سوبرماركت",
            Market.Scope.SERVICE_CITY,
            city_names=["طنطا"],
            area_keys=[("طنطا", "شارع البحر"), ("طنطا", "سيجر")],
            branch="طنطا",
        )
        create_market(
            "متجر قديم غير نشط",
            "عام",
            Market.Scope.SERVICE_CITY,
            status=Market.Status.INACTIVE,
            city_names=["القاهرة"],
            area_keys=[("القاهرة", "مصر الجديدة")],
            branch="مصر الجديدة",
        )

    def _seed_catalog(self, context):
        for name in [
            "أكل جاهز",
            "منتجات غذائية",
            "مشروبات",
            "حلويات",
            "صيدلية",
            "إضافات",
        ]:
            context["category_classifications"][name] = (
                CategoryClassification.objects.create(name=name)
            )

        category_rows = [
            ("وجبات", "أكل جاهز", "فئة مميزة", "وجبات مصرية جاهزة وطازجة."),
            ("خضر وفواكه", "منتجات غذائية", "فئة شائعة", "منتجات يومية طازجة."),
            ("منتجات بقالة", "منتجات غذائية", "فئة عادية", "أساسيات البيت."),
            ("مشروبات", "مشروبات", "فئة شائعة", "مياه وعصائر ومشروبات."),
            ("مخبوزات", "منتجات غذائية", "فئة عادية", "عيش ومخبوزات يومية."),
            ("حلويات", "حلويات", "فئة عادية", "حلويات شرقية وغربية."),
            ("أدوية", "صيدلية", "فئة مميزة", "منتجات صيدلية يومية."),
            ("مستلزمات منزلية", "إضافات", "فئة عادية", "باقات ومستلزمات للبيت."),
        ]
        for name, classification, category_type, description in category_rows:
            category = ProductCategory.objects.create(
                classification=context["category_classifications"][classification],
                name=name,
                type=category_type,
                description=description,
            )
            self._attach_image(category, "image", f"seed_category_{category.id}.png")
            context["categories"][name] = category

        attribute_rows = {
            "وجبات": {
                "الحجم": ["صغير", "عادي", "كبير"],
                "الحصة": ["فردي", "عائلي"],
            },
            "مشروبات": {"الحجم": ["250ml", "1 لتر", "2 لتر"]},
            "مخبوزات": {"العبوة": ["قطعة واحدة", "6 قطع", "12 قطعة"]},
            "خضر وفواكه": {"الوزن": ["500g", "1kg", "2kg"]},
            "أدوية": {"العبوة": ["صغيرة", "كبيرة"]},
            "حلويات": {"العبوة": ["250g", "500g", "1kg"]},
            "منتجات بقالة": {"العبوة": ["عبوة", "كرتونة"]},
        }
        for category_name, attrs in attribute_rows.items():
            category = context["categories"][category_name]
            for attr_name, option_values in attrs.items():
                attr = CategoryAttribute.objects.create(
                    category=category,
                    name=attr_name,
                )
                context["attributes"][(category_name, attr_name)] = attr
                for value in option_values:
                    option = CategoryOption.objects.create(
                        attribute=attr,
                        value=value,
                    )
                    context["options"][(category_name, attr_name, value)] = option

        for name in ["إضافات الطعام", "خدمات التعبئة"]:
            context["addition_classifications"][name] = (
                AdditionClassification.objects.create(name=name)
            )

        addition_rows = [
            ("جبنة إضافية", "Extra cheese", "80.00", "إضافات الطعام"),
            ("عيش إضافي", "Extra bread", "40.00", "إضافات الطعام"),
            ("صوص حار", "Hot sauce", "30.00", "إضافات الطعام"),
            ("بطاطس إضافية", "Extra fries", "120.00", "إضافات الطعام"),
            ("كيس إضافي", "Extra bag", "20.00", "خدمات التعبئة"),
        ]
        for name_ar, name_en, price, classification in addition_rows:
            addition = ProductAddition.objects.create(
                classification=context["addition_classifications"][classification],
                name_ar=name_ar,
                name_en=name_en,
                price=self._money(price),
                is_active=True,
            )
            self._attach_image(addition, "image", f"seed_addition_{addition.id}.png")
            context["additions"][name_ar] = addition

    def _seed_products(self, context):
        product_rows = [
            ("سوق يلا العام", "مستلزمات منزلية", "قفة رمضان", "قفة كاملة للأسرة.", ["450.00", "800.00"], 10, True, ["كيس إضافي"]),
            ("سوق يلا العام", "مستلزمات منزلية", "باقة تنظيف", "منظفات أساسية للبيت.", ["260.00", "420.00"], 0, True, ["كيس إضافي"]),
            ("سوق يلا العام", "مشروبات", "مياه معدنية", "مياه نقية معبأة.", ["35.00", "60.00"], 0, True, []),
            ("سوق يلا العام", "حلويات", "تمر مصري فاخر", "تمر طبيعي فاخر.", ["120.00", "220.00"], 5, True, []),
            ("سوق يلا العام", "منتجات بقالة", "زيت زيتون", "زيت زيتون بكر.", ["150.00", "280.00"], 0, True, []),
            ("سوق يلا العام", "منتجات بقالة", "أرز مصري", "أرز أبيض درجة أولى.", ["55.00", "105.00"], 0, True, ["كيس إضافي"]),
            ("متجر العروض العامة", "مستلزمات منزلية", "كرتونة رمضان", "كرتونة شهرية موفرة.", ["700.00", "1200.00"], 12, True, ["كيس إضافي"]),
            ("متجر العروض العامة", "مستلزمات منزلية", "عرض مدارس", "مستلزمات مدرسية مختارة.", ["150.00", "250.00"], 8, True, []),
            ("متجر العروض العامة", "مشروبات", "شاي أسوان", "شاي أسود فاخر.", ["75.00", "140.00"], 0, True, []),
            ("متجر العروض العامة", "منتجات بقالة", "سكر أبيض", "سكر ناعم معبأ.", ["38.00", "70.00"], 0, True, ["كيس إضافي"]),
            ("متجر العروض العامة", "مشروبات", "كرتونة مياه", "12 زجاجة مياه.", ["90.00", "160.00"], 5, True, []),
            ("متجر العروض العامة", "مستلزمات منزلية", "باقة عناية", "عناية شخصية يومية.", ["180.00", "320.00"], 0, True, []),
            ("مطبخ النيل العائلي", "وجبات", "دجاج مشوي", "دجاج متبل على الفحم.", ["180.00", "330.00"], 10, True, ["جبنة إضافية", "عيش إضافي", "صوص حار"]),
            ("مطبخ النيل العائلي", "وجبات", "شوربة خضار", "شوربة خفيفة يومية.", ["45.00", "80.00"], 0, True, ["عيش إضافي"]),
            ("مطبخ النيل العائلي", "وجبات", "كشري مخصوص", "كشري مصري بصلصة حارة.", ["55.00", "90.00"], 0, True, ["صوص حار"]),
            ("مطبخ النيل العائلي", "وجبات", "شاورما دجاج", "شاورما دجاج مع ثومية.", ["75.00", "130.00"], 5, True, ["جبنة إضافية", "بطاطس إضافية"]),
            ("مطبخ النيل العائلي", "وجبات", "برغر لحم", "برغر لحم بلدي.", ["95.00", "160.00"], 0, True, ["جبنة إضافية", "بطاطس إضافية"]),
            ("مطبخ النيل العائلي", "وجبات", "بيتزا عائلية", "بيتزا تكفي العائلة.", ["160.00", "280.00"], 15, True, ["جبنة إضافية", "صوص حار"]),
            ("مطبخ النيل العائلي", "وجبات", "مكرونة بشاميل", "طاجن بشاميل ساخن.", ["85.00", "150.00"], 0, False, ["عيش إضافي"]),
            ("سوق يلا الطازج", "خضر وفواكه", "تفاح أحمر", "تفاح أحمر طازج.", ["45.00", "85.00"], 0, True, ["كيس إضافي"]),
            ("سوق يلا الطازج", "خضر وفواكه", "موز", "موز بلدي ناضج.", ["38.00", "72.00"], 0, True, ["كيس إضافي"]),
            ("سوق يلا الطازج", "خضر وفواكه", "طماطم", "طماطم يومية.", ["18.00", "32.00"], 0, True, ["كيس إضافي"]),
            ("سوق يلا الطازج", "خضر وفواكه", "بطاطس", "بطاطس للتحمير والطبخ.", ["16.00", "30.00"], 0, True, ["كيس إضافي"]),
            ("سوق يلا الطازج", "مشروبات", "حليب طازج", "حليب يومي مبستر.", ["32.00", "58.00"], 0, True, []),
            ("سوق يلا الطازج", "مشروبات", "عصير برتقال", "عصير طبيعي.", ["28.00", "55.00"], 8, True, []),
            ("سوق يلا الطازج", "خضر وفواكه", "خيار", "خيار بلدي طازج.", ["15.00", "28.00"], 0, False, ["كيس إضافي"]),
            ("مخبز إسكندرية الذهبي", "مخبوزات", "عيش بلدي", "عيش طازج من الفرن.", ["5.00", "25.00"], 0, True, []),
            ("مخبز إسكندرية الذهبي", "مخبوزات", "فينو", "عيش فينو ناعم.", ["12.00", "60.00"], 0, True, []),
            ("مخبز إسكندرية الذهبي", "مخبوزات", "بريوش", "بريوش زبدة.", ["18.00", "90.00"], 0, True, []),
            ("مخبز إسكندرية الذهبي", "مخبوزات", "كرواسون بالشوكولاتة", "كرواسون محشو شوكولاتة.", ["35.00", "180.00"], 7, True, []),
            ("مخبز إسكندرية الذهبي", "مخبوزات", "باغيت", "باغيت مقرمش.", ["25.00", "130.00"], 0, True, []),
            ("مخبز إسكندرية الذهبي", "مخبوزات", "كعك إسكندراني", "كعك محلي طازج.", ["60.00", "220.00"], 5, True, []),
            ("حلويات الدلتا", "حلويات", "بقلاوة", "بقلاوة بالمكسرات.", ["90.00", "250.00"], 10, True, []),
            ("حلويات الدلتا", "حلويات", "بسبوسة", "بسبوسة بالقشطة.", ["55.00", "170.00"], 0, True, []),
            ("حلويات الدلتا", "حلويات", "كنافة", "كنافة نابلسية.", ["70.00", "220.00"], 0, True, []),
            ("حلويات الدلتا", "حلويات", "زلابية", "زلابية بالعسل.", ["35.00", "110.00"], 0, True, []),
            ("حلويات الدلتا", "حلويات", "قطايف", "قطايف بالمكسرات.", ["45.00", "140.00"], 6, True, []),
            ("حلويات الدلتا", "حلويات", "غريبة", "غريبة ناعمة.", ["80.00", "240.00"], 0, True, []),
            ("صيدلية الحياة", "أدوية", "كمامات", "كمامات طبية آمنة.", ["25.00", "100.00"], 0, True, []),
            ("صيدلية الحياة", "أدوية", "معقم يدين", "معقم كحولي.", ["45.00", "85.00"], 5, True, []),
            ("صيدلية الحياة", "أدوية", "فيتامين C", "مكمل غذائي.", ["120.00", "220.00"], 0, True, []),
            ("صيدلية الحياة", "أدوية", "مسكن ألم", "مسكن يومي.", ["35.00", "60.00"], 0, True, []),
            ("صيدلية الحياة", "أدوية", "ميزان حرارة", "ميزان حرارة رقمي.", ["180.00", "300.00"], 8, True, []),
            ("صيدلية الحياة", "أدوية", "شاش طبي", "شاش معقم.", ["20.00", "70.00"], 0, False, []),
            ("بقالة هادئة بلا عروض", "منتجات بقالة", "فول معلب", "فول جاهز.", ["28.00", "52.00"], 0, True, ["كيس إضافي"]),
            ("بقالة هادئة بلا عروض", "منتجات بقالة", "جبنة بيضاء", "جبنة طازجة.", ["65.00", "120.00"], 0, True, []),
            ("بقالة هادئة بلا عروض", "منتجات بقالة", "عسل أسود", "عسل قصب طبيعي.", ["55.00", "100.00"], 0, True, []),
            ("بقالة هادئة بلا عروض", "منتجات بقالة", "مخلل مشكل", "مخلل مصري.", ["35.00", "70.00"], 0, True, ["كيس إضافي"]),
            ("بقالة هادئة بلا عروض", "مشروبات", "لبن رايب", "لبن رايب بلدي.", ["22.00", "40.00"], 0, True, []),
            ("بقالة هادئة بلا عروض", "حلويات", "بسكويت شاي", "بسكويت خفيف.", ["18.00", "35.00"], 0, True, []),
            ("متجر قديم غير نشط", "منتجات بقالة", "منتج قديم 1", "منتج غير نشط.", ["20.00"], 0, False, []),
            ("متجر قديم غير نشط", "منتجات بقالة", "منتج قديم 2", "منتج غير نشط.", ["25.00"], 0, False, []),
            ("متجر قديم غير نشط", "مشروبات", "مشروب قديم", "مشروب غير متاح.", ["15.00"], 0, False, []),
            ("متجر قديم غير نشط", "مستلزمات منزلية", "باقة قديمة", "باقة غير نشطة.", ["100.00"], 0, False, []),
            ("متجر قديم غير نشط", "حلويات", "حلوى قديمة", "حلوى غير متاحة.", ["30.00"], 0, False, []),
        ]
        for row in product_rows:
            self._create_product(context, *row)

    def _create_product(
        self,
        context,
        market_name,
        category_name,
        name,
        description,
        prices,
        discount,
        is_available,
        addition_names,
    ):
        product = Product.objects.create(
            market=context["markets"][market_name],
            category=context["categories"][category_name],
            name=name,
            description=description,
            discount=self._money(str(discount)),
            is_available=is_available,
        )
        self._attach_image(product, "image", f"seed_product_{product.id}.png")
        context["products"][(market_name, name)] = product

        self._create_product_attribute_values(context, product, category_name)
        for index, price in enumerate(prices, start=1):
            variant = ProductVariant.objects.create(
                product=product,
                price=self._money(price),
                sku=f"SEED-{product.id:04d}-{index}",
            )
            self._create_variant_attribute_values(
                context,
                variant,
                category_name,
                index,
            )

        for addition_name in addition_names:
            context["additions"][addition_name].products.add(product)
        return product

    def _create_product_attribute_values(self, context, product, category_name):
        attrs = [
            (key, attr)
            for key, attr in context["attributes"].items()
            if key[0] == category_name
        ]
        for key, attr in attrs[:1]:
            options = [
                option
                for option_key, option in context["options"].items()
                if option_key[:2] == key
            ]
            if options:
                ProductAttributeValue.objects.create(
                    product=product,
                    attribute=attr,
                    option=options[0],
                )

    def _create_variant_attribute_values(self, context, variant, category_name, index):
        attrs = [
            (key, attr)
            for key, attr in context["attributes"].items()
            if key[0] == category_name
        ]
        for key, attr in attrs[:1]:
            options = [
                option
                for option_key, option in context["options"].items()
                if option_key[:2] == key
            ]
            if options:
                VariantAttributeValue.objects.create(
                    variant=variant,
                    attribute=attr,
                    option=options[(index - 1) % len(options)],
                )

    def _seed_likes(self, context):
        like_sets = {
            "amina": [
                ("مطبخ النيل العائلي", "دجاج مشوي"),
                ("مطبخ النيل العائلي", "بيتزا عائلية"),
                ("سوق يلا الطازج", "تفاح أحمر"),
                ("سوق يلا العام", "قفة رمضان"),
                ("حلويات الدلتا", "بقلاوة"),
            ],
            "karim": [
                ("سوق يلا العام", "مياه معدنية"),
                ("متجر العروض العامة", "كرتونة رمضان"),
                ("صيدلية الحياة", "معقم يدين"),
            ],
            "sara": [
                ("مخبز إسكندرية الذهبي", "كرواسون بالشوكولاتة"),
                ("مخبز إسكندرية الذهبي", "كعك إسكندراني"),
            ],
        }
        for user_key, product_keys in like_sets.items():
            user = context["users"][user_key]
            for product_key in product_keys:
                context["products"][product_key].liked_by.add(user)

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

    def _seed_notifications(self, context, now):
        pending_orders = [
            order
            for order in context["orders"]
            if order.review_status == Order.ReviewStatus.PENDING_REVIEW
        ]
        for order in pending_orders:
            context["notifications"].append(
                self._notification(
                    audience=Notification.Audience.ADMIN,
                    notification_type=Notification.Type.NEW_ORDER_REVIEW,
                    title="طلب جديد يحتاج مراجعة",
                    message=f"الطلب #{order.id} يحتاج مراجعة الإدارة.",
                    order=order,
                    is_blocking=True,
                    created_at=order.created_at,
                )
            )

        assigned_orders = [
            order
            for order in context["orders"]
            if order.assigned_representative_id is not None
        ]
        for order in assigned_orders[:6]:
            context["notifications"].append(
                self._notification(
                    audience=Notification.Audience.COURIER,
                    notification_type=Notification.Type.ORDER_ASSIGNED,
                    title="تم تعيين طلب جديد",
                    message=f"تم تعيين الطلب #{order.id} لك.",
                    order=order,
                    recipient=order.assigned_representative,
                    created_at=order.assigned_at or order.created_at,
                )
            )

        rejected_orders = [
            order
            for order in context["orders"]
            if order.review_status == Order.ReviewStatus.REJECTED
        ]
        for order in rejected_orders:
            context["notifications"].append(
                self._notification(
                    audience=Notification.Audience.CLIENT,
                    notification_type=Notification.Type.ORDER_REJECTED,
                    title="تم رفض الطلب",
                    message=f"تم رفض الطلب #{order.id}: {order.rejection_reason}",
                    order=order,
                    recipient=order.user,
                    created_at=order.rejected_at or order.created_at,
                )
            )

        context["notifications"].append(
            self._notification(
                audience=Notification.Audience.ADMIN,
                notification_type=Notification.Type.NEW_ORDER_REVIEW,
                title="تنبيه عام غير مقروء",
                message="تنبيه إداري تجريبي غير مقروء.",
                is_blocking=False,
                created_at=now - timedelta(hours=3),
            )
        )
        context["notifications"].append(
            self._notification(
                audience=Notification.Audience.ADMIN,
                notification_type=Notification.Type.NEW_ORDER_REVIEW,
                title="تنبيه عام مقروء",
                message="تنبيه إداري تجريبي مقروء.",
                is_blocking=False,
                is_read=True,
                created_at=now - timedelta(days=1),
            )
        )
        context["notifications"].append(
            self._notification(
                audience=Notification.Audience.ADMIN,
                notification_type=Notification.Type.NEW_ORDER_REVIEW,
                title="مراجعة محلولة",
                message="إشعار مراجعة محلول ضمن البيانات التجريبية.",
                order=context["orders"][4],
                is_blocking=True,
                is_read=True,
                is_resolved=True,
                created_at=now - timedelta(days=2),
            )
        )
        self.skipped.append(
            "Notification.Type only supports new_order_review, "
            "order_assigned, and order_rejected; separate approved/status-update "
            "types were not invented."
        )

    def _notification(
        self,
        audience,
        notification_type,
        title,
        message,
        order=None,
        recipient=None,
        is_read=False,
        is_blocking=False,
        is_resolved=False,
        created_at=None,
    ):
        created_at = created_at or timezone.now()
        read_at = created_at if is_read else None
        resolved_at = created_at if is_resolved else None
        notification = Notification.objects.create(
            audience=audience,
            type=notification_type,
            title=title,
            message=message,
            order=order,
            recipient=recipient,
            is_read=is_read,
            is_blocking=is_blocking,
            is_resolved=is_resolved,
            read_at=read_at,
            resolved_at=resolved_at,
        )
        Notification.objects.filter(pk=notification.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )
        notification.created_at = created_at
        notification.updated_at = created_at
        return notification

    def _assert_seed_data(self, context):
        assertions = {
            "admin_user_exists": User.objects.filter(
                email="seed.admin@yalla.seed",
                role=User.Role.ADMIN,
            ).exists(),
            "clients": User.objects.filter(role=User.Role.CLIENT).count(),
            "couriers": User.objects.filter(role=User.Role.REPRESENTATIVE).count(),
            "service_cities": ServiceCity.objects.count(),
            "delivery_areas": DeliveryArea.objects.count(),
            "market_classifications": MarketClassification.objects.count(),
            "markets": Market.objects.count(),
            "general_markets": Market.objects.filter(scope=Market.Scope.GENERAL).count(),
            "service_city_markets": Market.objects.filter(
                scope=Market.Scope.SERVICE_CITY
            ).count(),
            "categories": ProductCategory.objects.count(),
            "products": Product.objects.count(),
            "variants": ProductVariant.objects.count(),
            "products_without_variants": Product.objects.filter(
                variants__isnull=True
            ).count(),
            "offers": Offer.objects.count(),
            "orders": Order.objects.count(),
            "order_sections": OrderMarketSection.objects.count(),
            "orders_with_sections": Order.objects.filter(
                market_sections__isnull=False
            ).distinct().count(),
            "multi_market_orders": Order.objects.annotate(
                section_count=Count("market_sections")
            ).filter(section_count__gt=1).count(),
            "notifications": Notification.objects.count(),
            "pending_review_orders": Order.objects.filter(
                review_status=Order.ReviewStatus.PENDING_REVIEW
            ).count(),
            "assigned_courier_orders": Order.objects.filter(
                status=Order.Status.ASSIGNED,
                assigned_representative__isnull=False,
            ).count(),
            "fixed_area_orders": Order.objects.filter(
                delivery_type=Order.DeliveryType.FIXED_AREA
            ).count(),
            "other_delivery_orders": Order.objects.filter(
                delivery_type=Order.DeliveryType.DELIVERY,
                delivery_area__isnull=True,
                delivery_price__isnull=True,
            ).count(),
            "general_orders_with_fixed_delivery": Order.objects.filter(
                order_scope=Order.Scope.GENERAL,
            )
            .exclude(
                delivery_area__isnull=True,
                delivery_type=Order.DeliveryType.DELIVERY,
                delivery_price__isnull=True,
            )
            .count(),
            "general_manual_masr_el_gedida_order": Order.objects.filter(
                order_scope=Order.Scope.GENERAL,
                delivery_address__manual_city="القاهرة",
                delivery_address__manual_area="مصر الجديدة",
                delivery_address__details="شارع الثورة بجوار بنزينة التعاون",
            )
            .annotate(section_count=Count("market_sections"))
            .filter(section_count__gt=1)
            .exists(),
            "service_city_salam_fixed_order": Order.objects.filter(
                order_scope=Order.Scope.SERVICE_CITY,
                service_city__name="القاهرة",
                delivery_area__name="السلام",
                delivery_type=Order.DeliveryType.FIXED_AREA,
            ).exists(),
            "service_city_manual_unsupported_order": Order.objects.filter(
                order_scope=Order.Scope.SERVICE_CITY,
                service_city__name="القاهرة",
                delivery_area__isnull=True,
                delivery_type=Order.DeliveryType.DELIVERY,
                delivery_address__manual_area="منطقة غير مضافة",
            ).exists(),
        }
        failures = []
        checks = [
            ("admin user exists", assertions["admin_user_exists"]),
            ("at least 3 clients", assertions["clients"] >= 3),
            ("at least 3 couriers", assertions["couriers"] >= 3),
            ("at least 5 service cities", assertions["service_cities"] >= 5),
            ("at least 10 delivery areas", assertions["delivery_areas"] >= 10),
            (
                "at least 6 market classifications",
                assertions["market_classifications"] >= 6,
            ),
            ("at least 7 markets", assertions["markets"] >= 7),
            ("general markets exist", assertions["general_markets"] >= 2),
            (
                "service-city markets exist",
                assertions["service_city_markets"] >= 5,
            ),
            ("at least 6 categories", assertions["categories"] >= 6),
            ("at least 40 products", assertions["products"] >= 40),
            (
                "all products have variants",
                assertions["products_without_variants"] == 0,
            ),
            ("at least 15 offers", assertions["offers"] >= 15),
            ("at least 20 orders", assertions["orders"] >= 20),
            (
                "every order has a market section",
                assertions["orders_with_sections"] == assertions["orders"],
            ),
            (
                "at least 3 multi-market parent orders",
                assertions["multi_market_orders"] >= 3,
            ),
            ("at least 5 notifications", assertions["notifications"] >= 5),
            (
                "at least 3 pending review orders",
                assertions["pending_review_orders"] >= 3,
            ),
            (
                "at least 1 assigned courier order",
                assertions["assigned_courier_orders"] >= 1,
            ),
            (
                "general orders do not use fixed-area delivery",
                assertions["general_orders_with_fixed_delivery"] == 0,
            ),
            (
                "general manual Masr El Gedida multi-market order exists",
                assertions["general_manual_masr_el_gedida_order"],
            ),
            (
                "service-city Salam fixed-area order exists",
                assertions["service_city_salam_fixed_order"],
            ),
            (
                "service-city manual unsupported-area order exists",
                assertions["service_city_manual_unsupported_order"],
            ),
        ]
        for label, passed in checks:
            if not passed:
                failures.append(label)
        if failures:
            raise CommandError(
                "Seed assertions failed: " + ", ".join(failures)
            )
        return assertions

    def _print_summary(self, context, deleted, assertions):
        counts = {
            "users": User.objects.count(),
            "cities": ServiceCity.objects.count(),
            "delivery_areas": DeliveryArea.objects.count(),
            "market_classifications": MarketClassification.objects.count(),
            "markets": Market.objects.count(),
            "category_classifications": CategoryClassification.objects.count(),
            "categories": ProductCategory.objects.count(),
            "attributes": CategoryAttribute.objects.count(),
            "options": CategoryOption.objects.count(),
            "additions": ProductAddition.objects.count(),
            "products": Product.objects.count(),
            "variants": ProductVariant.objects.count(),
            "offers": Offer.objects.count(),
            "orders": Order.objects.count(),
            "order_sections": OrderMarketSection.objects.count(),
            "notifications": Notification.objects.count(),
            "liked_products": Product.objects.filter(liked_by__isnull=False)
            .distinct()
            .count(),
        }
        self.stdout.write(self.style.SUCCESS("Seed demo data complete."))
        self.stdout.write("Counts:")
        for key, value in counts.items():
            self.stdout.write(f"  {key}: {value}")

        self.stdout.write("Credentials:")
        for credential in context["credentials"]:
            self.stdout.write(
                "  {label}: email={email} username={username} password={password}".format(
                    **credential
                )
            )

        self.stdout.write("Coverage:")
        self.stdout.write(
            f"  general_markets/offers: yes "
            f"({assertions['general_markets']} markets)"
        )
        self.stdout.write(
            f"  service_city_markets/offers: yes "
            f"({assertions['service_city_markets']} markets)"
        )
        self.stdout.write(
            "  fixed_area_and_other_delivery_orders: yes "
            f"({assertions['fixed_area_orders']} fixed, "
            f"{assertions['other_delivery_orders']} other)"
        )
        self.stdout.write(
            "  pending_review_blocker_data: yes "
            f"({assertions['pending_review_orders']} pending)"
        )
        self.stdout.write(
            "  courier_flow_data: yes "
            f"({assertions['assigned_courier_orders']} assigned)"
        )
        self.stdout.write(
            f"  product_and_offer_images: {'no (--no-media)' if self.no_media else 'yes'}"
        )

        if self.skipped:
            self.stdout.write("Skipped unsupported fields/types:")
            for item in self.skipped:
                self.stdout.write(f"  - {item}")
            self.stdout.write(
                "  - Product.price does not exist; prices are on ProductVariant."
            )
            self.stdout.write(
                "  - Address.delivery_price does not exist; order delivery prices "
                "come from DeliveryArea or stay null for other delivery."
            )
        else:
            self.stdout.write("Skipped unsupported fields/types: none")

    def _attach_image(self, instance, field_name, filename):
        if self.no_media:
            return
        field = getattr(instance, field_name)
        upload_to = instance._meta.get_field(field_name).upload_to
        stored_name = f"{str(upload_to).strip('/')}/{filename}" if upload_to else filename
        field.storage.delete(stored_name)
        field.save(filename, ContentFile(TINY_PNG), save=True)

    def _write(self, message):
        if not self.quiet:
            self.stdout.write(message)

    @staticmethod
    def _decimal(value):
        return Decimal(str(value))

    @staticmethod
    def _money(value):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _percentage_amount(amount, percentage):
        return (amount * percentage / Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _name_parts(name):
        parts = name.split(maxsplit=1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]
