from .seeders_catalog import DemoCatalogSeederMixin
from .seeders_core import DemoSeedCoreMixin
from .seeders_locations import DemoLocationSeederMixin
from .seeders_offers import DemoOfferSeederMixin
from .seeders_orders import DemoOrderSeederMixin
from .seeders_reporting import DemoReportingMixin


class DemoSeedMixin(
    DemoSeedCoreMixin,
    DemoLocationSeederMixin,
    DemoCatalogSeederMixin,
    DemoOfferSeederMixin,
    DemoOrderSeederMixin,
    DemoReportingMixin,
):
    """Seed stages shared by the demo-data management command."""

