"""Local-only stateful customer traffic. Raw output contains metrics, not bodies."""

import json
import os
import time
import uuid
from collections import deque
from decimal import Decimal
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from locust import HttpUser, between, events, task
from locust.exception import StopUser
import gevent

from tools.performance.schedule import spike_target

ROOT = Path(__file__).resolve().parent
MANIFEST = Path(
    os.environ.get("PERF_ACCOUNTS", ROOT / "artifacts/accounts.private.json")
)
OUT = Path(os.environ.get("PERF_OUT", ROOT / "artifacts/smoke"))
RUN_ID = os.environ.get("PERF_RUN_ID", "local-smoke")
TARGET = int(os.environ.get("PERF_USERS", "1"))
WARMUP = float(os.environ.get("PERF_WARMUP_S", "60"))
MEASUREMENT = float(os.environ.get("PERF_MEASUREMENT_S", "300"))
SPIKE = os.environ.get("PERF_SHAPE") == "spike"
RAMP = 0 if SPIKE else TARGET / 2
_pool = deque()
_catalogs = []
_started = None
_stream = None
_manifest = None
_heartbeat = None
_journeys = None


def local_target(host):
    parsed = urlsplit(host or "")
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.port in {18080, 18081}
    )


def journey(method):
    @wraps(method)
    def measured(self):
        started = time.monotonic()
        elapsed = started - _started - RAMP - WARMUP
        self._journey_id = uuid.uuid4().hex
        self._journey_failed = False
        completed = False
        try:
            method(self)
            completed = True
        finally:
            _journeys.write(
                json.dumps(
                    {
                        "run_id": RUN_ID,
                        "time": time.time(),
                        "name": method.__name__,
                        "journey_id": self._journey_id,
                        "completed": completed,
                        "phase": "warmup"
                        if elapsed < 0
                        else "boundary"
                        if elapsed
                        < MEASUREMENT
                        <= time.monotonic() - _started - RAMP - WARMUP
                        else "measurement"
                        if elapsed < MEASUREMENT
                        else "cooldown",
                        "duration_ms": (time.monotonic() - started) * 1000,
                        "ok": completed and not self._journey_failed,
                        "definition": "Full journey including 2-5s think time",
                    }
                )
                + "\n"
            )

    return measured


@events.test_start.add_listener
def start(environment, **kwargs):
    global _stream, _started, _catalogs, _manifest, _heartbeat, _journeys
    if not local_target(environment.host):
        _pool.clear()
        raise ValueError("Load tests are restricted to the isolated loopback listeners")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _manifest = manifest
    if manifest.get("environment") != "isolated-local-performance":
        raise ValueError("Missing isolated performance manifest")
    _pool.clear()
    _pool.extend(manifest["accounts"][:100])
    _catalogs = manifest["catalogs"]
    if len(_pool) < TARGET:
        raise ValueError("One distinct account is required per concurrent user")
    OUT.mkdir(parents=True, exist_ok=True)
    _stream = (OUT / "requests.jsonl").open("w", encoding="utf-8", buffering=1)
    _journeys = (OUT / "journeys.jsonl").open("w", encoding="utf-8", buffering=1)
    _started = time.monotonic()
    (OUT / "timing.json").write_text(
        json.dumps(
            {
                "start_epoch": time.time(),
                "ramp_s": RAMP,
                "warmup_s": WARMUP,
                "planned_measurement_s": MEASUREMENT,
            }
        ),
        encoding="utf-8",
    )

    def heartbeat():
        while True:
            target = (
                spike_target(time.monotonic() - _started, TARGET)
                if SPIKE
                else (TARGET, 2)
            )
            value = {
                "time": time.time(),
                "active_users": environment.runner.user_count,
                "expected_users": target[0] if target else 0,
            }
            temporary = OUT / "load-state.tmp"
            temporary.write_text(json.dumps(value), encoding="utf-8")
            temporary.replace(OUT / "load-state.json")
            gevent.sleep(1)

    _heartbeat = gevent.spawn(heartbeat)


@events.request.add_listener
def record(
    request_type,
    name,
    response_time,
    response_length,
    response=None,
    context=None,
    exception=None,
    **kwargs,
):
    global _started
    if _stream is None:
        return
    now = time.monotonic()
    context = context or {}
    # The runner's user count includes on_start; a separate ready count is
    # emitted by the supervisor. Warmup starts after the spawn ramp ends.
    if _started is None:
        _started = now
    elapsed = now - _started - (RAMP + WARMUP)
    phase = (
        "setup"
        if context.get("setup")
        else (
            "warmup"
            if elapsed < 0
            else "measurement"
            if elapsed < MEASUREMENT
            else "cooldown"
        )
    )
    status = response.status_code if response is not None else 0
    _stream.write(
        json.dumps(
            {
                "run_id": RUN_ID,
                "time": time.time(),
                "name": name,
                "request_id": context.get("request_id"),
                "journey_id": context.get("journey_id"),
                "method": request_type,
                "phase": phase,
                "duration_ms": response_time,
                "bytes": response_length,
                "status": status,
                "ok": exception is None,
                "spike_segment": (
                    "before"
                    if elapsed < 120
                    else "peak"
                    if elapsed < 240
                    else "recovery"
                )
                if SPIKE
                else None,
            }
        )
        + "\n"
    )


@events.test_stop.add_listener
def stop(**kwargs):
    global _stream, _journeys
    if _stream is not None:
        _stream.close()
        _stream = None
    if _journeys is not None:
        _journeys.close()
        _journeys = None
    if _heartbeat is not None:
        _heartbeat.kill()
    if _manifest is not None:
        temporary = MANIFEST.with_suffix(".tmp")
        temporary.write_text(json.dumps(_manifest), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(MANIFEST)


class Customer(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        if not local_target(self.client.base_url) or not _pool:
            raise StopUser()
        self.account = _pool.popleft()
        self.catalog = _catalogs[-1]
        self.client.headers.update(
            {"Authorization": "Bearer " + self.account["access"]}
        )
        self.token_refreshed = time.monotonic()

    def on_stop(self):
        if hasattr(self, "account"):
            _pool.append(self.account)

    def request_json(self, method, path, name, *, validate=None, setup=False, **kwargs):
        if not local_target(self.client.base_url):
            raise StopUser()
        headers = kwargs.pop("headers", {})
        headers["X-Request-ID"] = RUN_ID + ":" + uuid.uuid4().hex
        result = None
        with self.client.request(
            method,
            path,
            name=name,
            catch_response=True,
            timeout=15,
            allow_redirects=False,
            headers=headers,
            context={
                "setup": setup,
                "request_id": headers["X-Request-ID"],
                "journey_id": getattr(self, "_journey_id", None),
            },
            **kwargs,
        ) as response:
            if response.status_code not in (200, 201):
                self._journey_failed = True
                response.failure("HTTP " + str(response.status_code))
                return None
            try:
                result = response.json()
                if validate is not None and not validate(result):
                    self._journey_failed = True
                    response.failure("Response contract/business validation failed")
                    return None
            except (ValueError, TypeError, KeyError, IndexError):
                self._journey_failed = True
                response.failure("Invalid JSON response contract")
                return None
        return result

    def refresh(self):
        if time.monotonic() - self.token_refreshed < 600:
            return
        result = self.request_json(
            "POST",
            "/api/v1/auth/refresh/",
            "auth_refresh",
            setup=True,
            json={"refresh": self.account["refresh"]},
            validate=lambda r: isinstance(r, dict) and bool(r.get("accessToken")),
        )
        if result is None:
            raise StopUser()
        self.account["refresh"] = result.get("refreshToken", self.account["refresh"])
        self.client.headers["Authorization"] = "Bearer " + result["accessToken"]
        self.token_refreshed = time.monotonic()

    def pause(self):
        self.wait()
        self.refresh()

    @task(7)
    @journey
    def browse(self):
        self.refresh()
        self.request_json(
            "GET", "/api/v1/home/", "home", validate=lambda r: isinstance(r, dict)
        )
        self.pause()
        market = self.catalog["market_id"]
        self.request_json(
            "GET",
            f"/api/v1/home/markets/{market}/storefront/",
            "storefront",
            params={"include_products": "false"},
            validate=lambda r: isinstance(r, dict),
        )
        seen = set()
        for page in (1, 2):
            self.pause()

            def valid(r):
                if not isinstance(r, dict) or not isinstance(r.get("results"), list):
                    return False
                ids = [item["id"] for item in r["results"]]
                good = (
                    bool(ids)
                    and len(ids) <= 30
                    and len(set(ids)) == len(ids)
                    and not seen.intersection(ids)
                )
                seen.update(ids)
                return good

            self.request_json(
                "GET",
                f"/api/v1/home/markets/{market}/storefront/products/",
                "store_products",
                params={"page": page, "page_size": 30},
                validate=valid,
            )
        self.pause()
        self.request_json(
            "GET",
            f"/api/v1/home/products/{self.catalog['product_id']}/",
            "product_detail",
            validate=lambda r: isinstance(r, dict)
            and r.get("id") == self.catalog["product_id"],
        )

    @task(2)
    @journey
    def search(self):
        self.refresh()
        self.request_json(
            "GET",
            "/api/v1/home/search/",
            "search",
            params={"q": "PERF", "page": 1},
            validate=lambda r: isinstance(r, (dict, list)),
        )
        self.pause()
        self.request_json(
            "GET",
            f"/api/v1/home/markets/{self.catalog['market_id']}/storefront/products/",
            "store_filter",
            params={
                "q": "PERF",
                "subcategory_id": self.catalog["subcategory_id"],
                "sort": "price_asc",
                "page_size": 30,
            },
            validate=lambda r: isinstance(r, dict) and bool(r.get("results")),
        )

    @task(1)
    @journey
    def checkout(self):
        self.refresh()
        payload = {
            "address_id": self.account["address_id"],
            "payment_method": "cash",
            "items": [{"variant_id": self.catalog["variant_id"], "quantity": 1}],
        }
        preview = self.request_json(
            "POST",
            "/api/v1/orders/preview/",
            "order_preview",
            json=payload,
            validate=lambda r: isinstance(r, dict)
            and isinstance(r.get("summary"), dict),
        )
        if preview is None:
            return
        self.pause()
        key = RUN_ID + "-" + uuid.uuid4().hex
        created = self.request_json(
            "POST",
            "/api/v1/orders/create/",
            "order_create",
            json=payload,
            headers={"Idempotency-Key": key},
            validate=lambda r: isinstance(r, list)
            and len(r) == 1
            and bool(r[0].get("id"))
            and Decimal(str(r[0]["total_price"]))
            == Decimal(str(preview["summary"]["grand_total"])),
        )
        if created is None:
            return
        self.pause()
        self.request_json(
            "GET",
            "/api/v1/orders/my/",
            "order_detail",
            validate=lambda r: isinstance(r, list)
            and any(order.get("id") == created[0]["id"] for order in r),
        )
        # One retry per created order proves real HTTP idempotency, separately
        # named so retry latency never gets merged with first creation.
        retried = self.request_json(
            "POST",
            "/api/v1/orders/create/",
            "order_retry",
            json=payload,
            headers={"Idempotency-Key": key},
            validate=lambda r: isinstance(r, list)
            and len(r) == 1
            and r[0].get("id") == created[0]["id"],
        )
        if retried is None:
            return

    def smoke_journey(self):
        self.browse()
        self.pause()
        self.search()
        self.pause()
        self.checkout()


if os.environ.get("PERF_SMOKE") == "1":
    Customer.tasks = [Customer.smoke_journey]


if SPIKE:
    from locust import LoadTestShape

    class ContinuousSpike(LoadTestShape):
        def tick(self):
            return spike_target(self.get_run_time(), TARGET)
