from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.db.models import Count
from django.utils import timezone

from accounts.models import CourierProfile, OneTimePassword, User
from catalog.models import (
    CategoryAttribute,
    CategoryClassification,
    CategoryOption,
    Product,
    ProductAddition,
    ProductCategory,
    ProductVariant,
)
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from notifications.models import Notification
from offers.models import Offer
from orders.models import Order, OrderItem, OrderMarketSection, OrderOffer

from .seed_constants import TINY_PNG


class DemoReportingMixin:
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
