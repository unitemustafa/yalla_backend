from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

from accounts.models import CourierProfile, OneTimePassword
from locations.models import Address, DeliveryArea, ServiceCity

User = get_user_model()


class UserLocationSeederMixin:
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
                "is_verified": True,
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
                "is_verified": True,
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
                "is_verified": True,
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
                "is_verified": True,
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
                "is_active": True,
                "is_verified": False,
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
                "is_verified": True,
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
                "is_verified": True,
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
                "is_verified": True,
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
                "is_verified": True,
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

