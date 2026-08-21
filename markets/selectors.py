def user_home_address(user):
    """Return the preferred address used to scope home-page results."""

    return (
        user.addresses.filter(is_default=True).order_by("-created_at").first()
        or user.addresses.order_by("-created_at").first()
    )
