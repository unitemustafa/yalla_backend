import base64
from decimal import Decimal

from django.core.files.base import ContentFile

from catalog.models import (
    AdditionClassification,
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductAttribute,
    ProductAttributeOption,
    ProductAttributeValue,
    ProductCategory,
    ProductImage,
    ProductVariant,
    StoreSubcategory,
    VariantAttributeValue,
)
from markets.models import Market, MarketClassification, MarketSubcategory, MarketType

SEED_PRODUCT_IMAGE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class CatalogSeederMixin:
    def _seed_markets(self, areas):
        classifications = {}
        market_types = {}
        classification_types = {
            "سوبرماركت": MarketClassification.ClassificationType.POPULAR,
            "مطعم": MarketClassification.ClassificationType.FEATURED,
            "مخبزة": MarketClassification.ClassificationType.NORMAL,
            "حلويات": MarketClassification.ClassificationType.NORMAL,
            "منتجات عضوية": MarketClassification.ClassificationType.NORMAL,
        }
        market_type_names = {
            "سوبرماركت": "Supermarket",
            "مطعم": "Restaurant",
            "مخبزة": "Bakery",
            "حلويات": "Desserts",
            "منتجات عضوية": "Organic",
        }
        for name, classification_type in classification_types.items():
            obj, _ = MarketClassification.objects.update_or_create(
                name=name,
                defaults={"classification_type": classification_type},
            )
            classifications[name] = obj
            market_type, _ = MarketType.objects.update_or_create(
                classification=obj,
                name_ar=name,
                defaults={
                    "name_en": market_type_names[name],
                    "image": f"seed/market-types/{market_type_names[name].lower()}.webp",
                    "is_active": True,
                },
            )
            market_types[name] = market_type

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
            market.market_types.set([market_types[classification]])
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
        store_subcategories = {}
        for name, classification, category_type, description in category_definitions:
            category, _ = ProductCategory.objects.update_or_create(
                name=name,
                classification=classification,
                defaults={"type": category_type, "description": description},
            )
            categories[name] = category
            subcategory, _ = StoreSubcategory.objects.update_or_create(
                name_ar=name,
                defaults={
                    "name_en": name,
                    "description_ar": description,
                    "description_en": description,
                    "is_active": True,
                },
            )
            store_subcategories[name] = subcategory

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
                    "subcategory": store_subcategories[category_name],
                    "description": f"منتج تجريبي: {name}.",
                    "discount": Decimal("0.00"),
                },
            )
            MarketSubcategory.objects.get_or_create(
                market=markets[market_name],
                subcategory=store_subcategories[category_name],
                defaults={
                    "sort_order": MarketSubcategory.objects.filter(
                        market=markets[market_name],
                    ).count()
                },
            )
            self._seed_product_image(product, index)
            products[name] = product
            attribute = attributes[category_name]
            first_option, second_option = options[category_name]
            ProductAttributeValue.objects.update_or_create(
                product=product,
                attribute=attribute,
                defaults={"option": first_option},
            )
            product_attribute, _ = ProductAttribute.objects.update_or_create(
                product=product,
                name=attribute.name,
                defaults={"sort_order": 0},
            )
            product_options = []
            for option_index, legacy_option in enumerate(
                (first_option, second_option),
            ):
                product_option, _ = ProductAttributeOption.objects.update_or_create(
                    attribute=product_attribute,
                    value=legacy_option.value,
                    defaults={"sort_order": option_index},
                )
                product_options.append(product_option)

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
                    defaults={
                        "option": option,
                        "product_attribute": product_attribute,
                        "product_attribute_option": product_options[variant_index - 1],
                    },
                )
                product_variants.append(variant)
            variants[name] = product_variants

        return {"products": products, "variants": variants}

    def _seed_product_image(self, product, index):
        image_name = f"products/seed-product-{index:02d}.png"
        storage = ProductImage._meta.get_field("image").storage
        if not storage.exists(image_name):
            image_name = storage.save(
                image_name,
                ContentFile(SEED_PRODUCT_IMAGE_BYTES),
            )
        product_image, _ = ProductImage.objects.update_or_create(
            product=product,
            sort_order=0,
            defaults={
                "image": image_name,
                "is_primary": True,
            },
        )
        if product.image.name != product_image.image.name:
            product.image = product_image.image.name
            product.save(update_fields=("image", "updated_at"))

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

