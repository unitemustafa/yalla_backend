import mimetypes
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CourierProfile
from accounts.permissions import (
    IsOrderAdminRole,
    IsOrderClientRole,
    IsRepresentativeRole,
)
from config.pagination import paginated_list_response
from offers.models import Offer
from .models import Order, OrderEvent, OrderMarketSection
from .request_validation import normalized_order_request_data
from .selectors import (
    active_available_representatives,
    courier_order_list_queryset,
    courier_orders_for_user,
    courier_service_city_for_order,
    eligible_representatives_for_order,
    order_queryset,
    same_city_representatives,
)
from .serializers import (
    AdminOrderCreateSerializer,
    ClientOrderCreateSerializer,
    CourierOrderDetailSerializer,
    CourierOrderListSerializer,
    CourierOrderStatusSerializer,
    OrderAssignmentSerializer,
    OrderDeliveryPriceSerializer,
    OrderListSerializer,
    OrderPreviewSerializer,
    OrderReviewActionSerializer,
    OrderSerializer,
    OrderStatusSerializer,
    RepresentativeSummarySerializer,
)
from .services import (
    COURIER_STATUSES,
    COURIER_TRANSITIONS,
    allowed_statuses_for_order,
    record_order_event,
    resolve_order_target_user,
)
from .admin_review_views import (
    AdminOrderApproveView,
    AdminOrderRejectView,
    AdminOrderReviewBlockerView,
    AdminOrderServiceCityRepresentativesView,
)
from .courier_views import (
    CourierOrderDetailView,
    CourierOrderListView,
    CourierOrderStatusView,
)
from notifications.services import (
    create_new_order_review_notification,
    resolve_order_review_notifications,
)
from notifications.courier_services import (
    notify_courier_order_assigned,
    notify_courier_order_cancelled,
    notify_courier_order_unassigned,
)
from notifications.order_services import (
    create_admin_courier_order_status_notification,
    schedule_order_lifecycle_notification,
)

User = get_user_model()


IsAdminRole = IsOrderAdminRole
IsClientRole = IsOrderClientRole
IsCourierRole = IsRepresentativeRole


class OrderPrivateMediaView(APIView):
    permission_classes = (IsAuthenticated,)
    field_name = ""

    def get(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_related("user", "assigned_representative"),
            pk=order_id,
        )
        if not self._can_access(request.user, order):
            raise PermissionDenied("You cannot access this order image.")

        field = getattr(order, self.field_name)
        if not field or not field.name:
            raise NotFound("This order image is not available.")
        relative_path = PurePosixPath(field.name)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or "\\" in field.name
        ):
            raise NotFound("This order image is not available.")

        content_type = (
            mimetypes.guess_type(field.name)[0]
            or "application/octet-stream"
        )
        if settings.PRIVATE_MEDIA_X_ACCEL_REDIRECT:
            response = HttpResponse(content_type=content_type)
            internal_prefix = settings.PRIVATE_MEDIA_INTERNAL_URL.rstrip("/")
            response["X-Accel-Redirect"] = (
                f"{internal_prefix}/{quote(relative_path.as_posix(), safe='/')}"
            )
        else:
            response = FileResponse(
                field.storage.open(field.name, "rb"),
                content_type=content_type,
                as_attachment=False,
                filename=field.name.rsplit("/", 1)[-1],
            )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @staticmethod
    def _can_access(user, order):
        return bool(
            user.role == User.Role.ADMIN
            or order.user_id == user.id
            or order.assigned_representative_id == user.id
        )


class OrderImageView(OrderPrivateMediaView):
    field_name = "image"


class OrderDeliveryProofView(OrderPrivateMediaView):
    field_name = "delivery_proof"


class OrderListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    serializer_class = OrderSerializer

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminOrderCreateSerializer
        return OrderListSerializer

    def get_queryset(self):
        queryset = order_queryset()
        order_status = self.request.query_params.get("status")
        if order_status:
            queryset = queryset.filter(status=order_status)
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        target_user = resolve_order_target_user(request, action="create", lock=True)
        data = request.data.copy()
        if "delivery_address_id" not in data and "address_id" in data:
            data["delivery_address_id"] = data["address_id"]
        data["user_id"] = target_user.id
        serializer = AdminOrderCreateSerializer(
            data=data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        record_order_event(
            order,
            OrderEvent.EventType.ORDER_CREATED,
            actor=self.request.user,
            to_status=order.status,
        )
        create_new_order_review_notification(order)
        order = order_queryset().get(pk=order.pk)
        return Response(
            OrderSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ClientOrderListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, IsClientRole)
    serializer_class = OrderSerializer

    def get_queryset(self):
        queryset = order_queryset().filter(user=self.request.user)
        order_status = self.request.query_params.get("status")
        if order_status:
            queryset = queryset.filter(status=order_status)
        return queryset


class OrderPreviewView(APIView):
    permission_classes = (IsAuthenticated,)
    rate_limit_scopes = ("order_preview_user",)

    def post(self, request):
        preview_user = resolve_order_target_user(request, action="preview")
        data = normalized_order_request_data(request.data)
        serializer = OrderPreviewSerializer(
            data=data,
            context={"request": request, "preview_user": preview_user},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.preview_data())


class ClientOrderCreateView(APIView):
    permission_classes = (IsAuthenticated, IsClientRole)
    rate_limit_scopes = ("order_create_user",)

    @transaction.atomic
    def post(self, request):
        target_user = resolve_order_target_user(request, action="create", lock=True)
        data = normalized_order_request_data(request.data, include_create_fields=True)
        serializer = ClientOrderCreateSerializer(
            data=data,
            context={"request": request, "preview_user": target_user},
        )
        serializer.is_valid(raise_exception=True)
        orders = serializer.create_orders()
        for order in orders:
            event = record_order_event(
                order,
                OrderEvent.EventType.ORDER_CREATED,
                actor=request.user,
                to_status=order.status,
            )
            schedule_order_lifecycle_notification(
                order,
                event,
                "order_created",
                new_status=order.status,
            )
        return Response(
            OrderSerializer(
                orders,
                many=True,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    serializer_class = OrderSerializer
    lookup_url_kwarg = "order_id"

    def get_queryset(self):
        return order_queryset()

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        old_status = order.status
        old_representative = order.assigned_representative
        order.status = Order.Status.CANCELLED
        order.assigned_representative = None
        order.assigned_at = None
        order.save(
            update_fields=[
                "status",
                "assigned_representative",
                "assigned_at",
                "updated_at",
            ]
        )
        event = record_order_event(
            order,
            OrderEvent.EventType.CANCELLED,
            actor=request.user,
            from_status=old_status,
            to_status=order.status,
        )
        if old_representative is not None and old_status != Order.Status.CANCELLED:
            notify_courier_order_cancelled(
                order,
                old_representative,
                order_event=event,
            )
        schedule_order_lifecycle_notification(
            order,
            event,
            "order_cancelled",
            old_status=old_status,
            new_status=order.status,
        )
        resolve_order_review_notifications(order)
        return Response(
            self.get_serializer(order_queryset().get(pk=order.pk)).data,
            status=status.HTTP_200_OK,
        )


class OrderStatusView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
        )
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        if new_status not in allowed_statuses_for_order(order):
            return Response(
                {"status": "Invalid status transition."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = order.status
        old_representative = order.assigned_representative
        order.status = new_status
        if order.status in (Order.Status.CANCELLED, Order.Status.FAILED_DELIVERY):
            order.assigned_representative = None
            order.assigned_at = None
        order.save()
        event = record_order_event(
            order,
            (
                OrderEvent.EventType.CANCELLED
                if new_status == Order.Status.CANCELLED
                else OrderEvent.EventType.STATUS_CHANGED
            ),
            actor=request.user,
            from_status=old_status,
            to_status=new_status,
        )
        if (
            new_status == Order.Status.CANCELLED
            and old_status != Order.Status.CANCELLED
            and old_representative is not None
        ):
            notify_courier_order_cancelled(
                order,
                old_representative,
                order_event=event,
            )
        schedule_order_lifecycle_notification(
            order,
            event,
            (
                "order_cancelled"
                if new_status == Order.Status.CANCELLED
                else "order_failed_delivery"
                if new_status == Order.Status.FAILED_DELIVERY
                else "order_status_changed"
            ),
            old_status=old_status,
            new_status=new_status,
        )
        return Response(
            OrderSerializer(
                order_queryset().get(pk=order.pk),
                context={"request": request},
            ).data
        )


class OrderDeliveryPriceView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
        )
        if order.status in (
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
            Order.Status.CANCELLED,
        ):
            return Response(
                {
                    "detail": (
                        "Delivery price cannot be changed after delivery, failed delivery, or cancellation."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderDeliveryPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old_delivery_price = order.delivery_price
        delivery_price = serializer.validated_data["delivery_price"]
        action = serializer.validated_data["action"]
        if (
            action == "request_approval"
            and order.delivery_type != Order.DeliveryType.DELIVERY
        ):
            return Response(
                {
                    "action": (
                        "Customer approval is only available for manually "
                        "quoted delivery orders."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            delivery_price > Decimal("0.00")
            and order.order_offers.filter(
                offer__type=Offer.OfferType.DELIVERY,
            ).exists()
        ):
            return Response(
                {
                    "delivery_price": (
                        "Delivery price must remain zero while a free-delivery offer "
                        "is applied to the order."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        total = (
            order.subtotal_price
            - order.discount
            + delivery_price
            + order.multi_market_fee
        )
        order.delivery_price = delivery_price
        order.total_price = max(total, Decimal("0.00"))
        if order.delivery_type == Order.DeliveryType.FIXED_AREA:
            order.fulfillment_type = Order.FulfillmentType.DIRECT
            order.external_shipping_status = Order.ExternalShippingStatus.NOT_REQUIRED
        else:
            order.fulfillment_type = Order.FulfillmentType.EXTERNAL_SHIPPING
            order.external_shipping_status = (
                Order.ExternalShippingStatus.AWAITING_CUSTOMER_APPROVAL
                if action == "request_approval"
                else Order.ExternalShippingStatus.QUOTED
            )
        order.save(
            update_fields=[
                "delivery_price",
                "total_price",
                "fulfillment_type",
                "external_shipping_status",
                "updated_at",
            ]
        )
        event = record_order_event(
            order,
            (
                OrderEvent.EventType.DELIVERY_QUOTE_SENT
                if action == "request_approval"
                else OrderEvent.EventType.DELIVERY_PRICE_CHANGED
            ),
            actor=request.user,
            from_status=order.status,
            to_status=order.status,
            metadata={
                "from_delivery_price": (
                    f"{old_delivery_price:.2f}"
                    if old_delivery_price is not None
                    else None
                ),
                "to_delivery_price": f"{delivery_price:.2f}",
                "requires_customer_approval": action == "request_approval",
            },
        )
        if action == "request_approval":
            schedule_order_lifecycle_notification(
                order,
                event,
                "delivery_quote_sent",
                old_status=order.status,
                new_status=order.status,
            )

        refreshed_order = order_queryset().get(pk=order.pk)
        return Response(
            OrderSerializer(refreshed_order, context={"request": request}).data
        )


class ClientOrderDeliveryQuoteAcceptView(APIView):
    permission_classes = (IsAuthenticated, IsClientRole)

    @transaction.atomic
    def post(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
            user=request.user,
        )
        if (
            order.external_shipping_status
            != Order.ExternalShippingStatus.AWAITING_CUSTOMER_APPROVAL
            or order.delivery_price is None
        ):
            return Response(
                {"detail": "This order has no delivery quote awaiting approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.status in (
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
            Order.Status.CANCELLED,
        ):
            return Response(
                {"detail": "A closed order quote cannot be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.external_shipping_status = Order.ExternalShippingStatus.QUOTED
        order.save(update_fields=["external_shipping_status", "updated_at"])
        record_order_event(
            order,
            OrderEvent.EventType.DELIVERY_QUOTE_ACCEPTED,
            actor=request.user,
            from_status=order.status,
            to_status=order.status,
            metadata={"delivery_price": f"{order.delivery_price:.2f}"},
        )
        refreshed_order = order_queryset().get(pk=order.pk)
        return Response(
            OrderSerializer(refreshed_order, context={"request": request}).data
        )


class OrderAssignmentView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    @transaction.atomic
    def patch(self, request, order_id):
        order = generics.get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
        )
        serializer = OrderAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        representative = serializer.validated_data["representative"]
        terminal_statuses = (
            Order.Status.DELIVERED,
            Order.Status.FAILED_DELIVERY,
            Order.Status.CANCELLED,
        )
        if representative is None:
            if (
                order.status in terminal_statuses
                or order.status == Order.Status.PICKED_UP
            ):
                return Response(
                    {
                        "detail": "Order cannot be unassigned after pickup or terminal status."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not order.assigned_representative_id:
                refreshed_order = order_queryset().get(pk=order.pk)
                return Response(
                    OrderSerializer(
                        refreshed_order,
                        context={"request": request},
                    ).data
                )
            old_status = order.status
            old_representative_id = order.assigned_representative_id
            order.assigned_representative = None
            order.assigned_at = None
            if order.status == Order.Status.ASSIGNED:
                order.status = Order.Status.CONFIRMED
            order.save(
                update_fields=[
                    "assigned_representative",
                    "assigned_at",
                    "status",
                    "updated_at",
                ]
            )
            event = record_order_event(
                order,
                OrderEvent.EventType.UNASSIGNED,
                actor=request.user,
                from_status=old_status,
                to_status=order.status,
                metadata={"representative_id": old_representative_id},
            )
            old_representative = User.objects.filter(pk=old_representative_id).first()
            if old_representative is not None:
                notify_courier_order_unassigned(
                    order,
                    old_representative,
                    order_event=event,
                )
            schedule_order_lifecycle_notification(
                order,
                event,
                "order_status_changed",
                old_status=old_status,
                new_status=order.status,
            )
            return Response(
                OrderSerializer(
                    order_queryset().get(pk=order.pk),
                    context={"request": request},
                ).data
            )
        if order.review_status != Order.ReviewStatus.APPROVED:
            return Response(
                {"detail": "Order must be approved before assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.status not in (Order.Status.CONFIRMED, Order.Status.ASSIGNED):
            return Response(
                {"detail": "Only confirmed or assigned orders can be assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = (
            CourierProfile.objects.select_related("service_city")
            .filter(user=representative)
            .first()
        )
        if profile is None:
            return Response(
                {"representative_id": "Representative must have a courier profile."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        courier_service_city = courier_service_city_for_order(order)
        if (
            courier_service_city is not None
            and profile.service_city_id != courier_service_city.id
        ):
            return Response(
                {"representative_id": ("هذا المندوب لا يعمل في نفس مدينة الطلب.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_status = order.status
        old_representative = order.assigned_representative
        if (
            old_representative is not None
            and old_representative.pk == representative.pk
        ):
            refreshed_order = order_queryset().get(pk=order.pk)
            return Response(
                OrderSerializer(refreshed_order, context={"request": request}).data
            )
        order.assigned_representative = representative
        order.assigned_at = timezone.now()
        order.status = Order.Status.ASSIGNED
        order.save(
            update_fields=[
                "assigned_representative",
                "assigned_at",
                "status",
                "updated_at",
            ]
        )
        event = record_order_event(
            order,
            OrderEvent.EventType.ASSIGNED,
            actor=request.user,
            from_status=old_status,
            to_status=order.status,
            metadata={"representative_id": representative.id},
        )
        schedule_order_lifecycle_notification(
            order,
            event,
            "order_status_changed",
            old_status=old_status,
            new_status=order.status,
        )
        if old_representative is not None:
            notify_courier_order_unassigned(
                order,
                old_representative,
                order_event=event,
            )
        notify_courier_order_assigned(order, representative, order_event=event)
        return Response(
            {
                "message": "Order assigned successfully.",
                "order": OrderSerializer(order, context={"request": request}).data,
                "representative": RepresentativeSummarySerializer(representative).data,
            }
        )
