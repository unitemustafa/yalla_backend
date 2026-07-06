from orders.models import Order


ACTIVE_ASSIGNED_ORDER_STATUSES = (
    Order.Status.CONFIRMED,
    Order.Status.UNDER_PREPARATION,
    Order.Status.READY,
    Order.Status.PICKED_UP,
    Order.Status.ON_THE_WAY,
)


def active_assigned_orders_for_user(user):
    return user.assigned_orders.filter(status__in=ACTIVE_ASSIGNED_ORDER_STATUSES)
