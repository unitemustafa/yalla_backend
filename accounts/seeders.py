from .seeders_catalog import CatalogSeederMixin
from .seeders_orders import OrderSeederMixin
from .seeders_users import UserLocationSeederMixin


class SeedDataMixin(
    UserLocationSeederMixin,
    CatalogSeederMixin,
    OrderSeederMixin,
):
    """Composable seed operations used by the management command."""

