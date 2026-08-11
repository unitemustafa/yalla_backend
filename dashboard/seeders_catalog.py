from decimal import Decimal

from catalog.models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductAttributeValue,
    ProductCategory,
    StoreSubcategory,
    ProductVariant,
    VariantAttributeValue,
)
from markets.models import Market, MarketClassification, MarketSubcategory

from .seed_constants import ACTIVE_DAYS


class DemoCatalogSeederMixin:
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
            subcategory = StoreSubcategory.objects.create(
                name_ar=name,
                name_en=name,
                description_ar=description,
                description_en=description,
                is_active=True,
            )
            context["store_subcategories"][name] = subcategory

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
            subcategory=context["store_subcategories"][category_name],
            name=name,
            description=description,
            discount=self._money(str(discount)),
            is_available=is_available,
        )
        MarketSubcategory.objects.get_or_create(
            market=context["markets"][market_name],
            subcategory=context["store_subcategories"][category_name],
            defaults={
                "sort_order": MarketSubcategory.objects.filter(
                    market=context["markets"][market_name],
                ).count()
            },
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

