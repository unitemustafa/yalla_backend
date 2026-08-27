from datetime import timedelta
from decimal import Decimal

from accounts.models import CourierProfile, OneTimePassword, User
from locations.models import Address, DeliveryArea, ServiceCity

from .seed_constants import PASSWORD


class DemoLocationSeederMixin:
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
                "name": "أحمد طيار",
                "phone": "+201001000004",
                "role": User.Role.REPRESENTATIVE,
            },
            {
                "key": "courier2",
                "email": "seed.courier2@yalla.seed",
                "username": "seed_courier2",
                "name": "محمود طيار",
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

