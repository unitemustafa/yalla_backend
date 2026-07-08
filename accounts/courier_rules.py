from orders.models import Order


ACTIVE_ASSIGNED_ORDER_STATUSES = (
    Order.Status.ASSIGNED,
    Order.Status.PICKED_UP,
)


def active_assigned_orders_for_user(user):
    return user.assigned_orders.filter(status__in=ACTIVE_ASSIGNED_ORDER_STATUSES)
