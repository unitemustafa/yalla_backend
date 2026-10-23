"""Loopback-only customer/courier HTTP traffic for the disposable stack."""

import json
import time
from collections import deque

from locust import HttpUser, between, events, task
from locust.exception import StopUser

from tools.performance import locustfile as base


COURIER_COUNT = max(1, base.TARGET // 5)
_couriers = deque()


@events.test_start.add_listener
def prepare_couriers(environment, **kwargs):
    if not base.local_target(environment.host) or base.TARGET < 2:
        raise ValueError(
            "Mixed traffic requires an isolated target and at least 2 users"
        )
    manifest = json.loads(base.MANIFEST.read_text(encoding="utf-8"))
    accounts = manifest.get("couriers", [])
    if len(accounts) < COURIER_COUNT:
        raise ValueError("Seed a distinct courier account per simulated courier")
    _couriers.clear()
    # Share the objects persisted by the existing token/session lifecycle hook.
    base._manifest["couriers"] = accounts
    _couriers.extend(accounts[:COURIER_COUNT])


class Customer(base.Customer):
    fixed_count = base.TARGET - COURIER_COUNT


class Courier(HttpUser):
    fixed_count = COURIER_COUNT
    wait_time = between(2, 5)
    request_json = base.Customer.request_json
    refresh = base.Customer.refresh
    pause = base.Customer.pause

    def on_start(self):
        if not base.local_target(self.client.base_url) or not _couriers:
            raise StopUser()
        self.account = _couriers.popleft()
        self.client.headers.update(
            {"Authorization": "Bearer " + self.account["access"]}
        )
        self.token_refreshed = time.monotonic()

    def on_stop(self):
        if hasattr(self, "account"):
            _couriers.append(self.account)

    @task(3)
    @base.journey
    def active(self):
        self.refresh()
        for page in range(1, 6):
            result = self.request_json(
                "GET",
                "/api/v1/courier/orders/",
                "courier_active",
                params={"scope": "active", "page": page, "page_size": 100},
                validate=lambda r: isinstance(r, dict)
                and isinstance(r.get("results"), list),
            )
            if result is None or not result.get("next"):
                return
        raise StopUser()  # Do not silently truncate an unexpectedly large fixture.

    @task(1)
    @base.journey
    def history(self):
        self.refresh()
        self.request_json(
            "GET",
            "/api/v1/courier/orders/",
            "courier_history",
            params={"scope": "history", "page": 1, "page_size": 30},
            validate=lambda r: isinstance(r, dict)
            and isinstance(r.get("results"), list),
        )

    @task(2)
    @base.journey
    def deliver(self):
        self.refresh()
        if not self.account["order_ids"]:
            raise StopUser()  # An exhausted fixture invalidates the user-count check.
        order_id = self.account["order_ids"].pop()
        path = f"/api/v1/courier/orders/{order_id}/"
        detail = self.request_json(
            "GET",
            path,
            "courier_detail",
            validate=lambda r: isinstance(r, dict) and r.get("id") == order_id,
        )
        if detail is None:
            return
        for state in ("picked_up", "delivered"):
            self.pause()
            result = self.request_json(
                "PATCH",
                path + "status/",
                "courier_" + state,
                json={"status": state},
                validate=lambda r: isinstance(r, dict) and r.get("status") == state,
            )
            if result is None:
                return
        self.request_json(
            "PATCH",
            path + "status/",
            "courier_retry",
            json={"status": "delivered"},
            validate=lambda r: isinstance(r, dict) and r.get("status") == "delivered",
        )
