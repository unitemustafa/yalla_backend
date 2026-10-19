"""Compare equivalent order responses on isolated fixtures; never export bodies."""

import hashlib
import argparse
import csv
from datetime import datetime, timezone
import json
import os
import re
import statistics
import time
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="20261019-address-reuse")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", args.run_id):
        parser.error("run-id must contain only letters, digits, underscores or hyphens")
    if os.environ.get("DJANGO_SETTINGS_MODULE", "config.performance_settings") != "config.performance_settings":
        raise RuntimeError("Refusing settings outside the isolated performance environment")
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.performance_settings"
    import django

    django.setup()
    from django.conf import settings
    from django.db import connection
    from rest_framework.test import APIClient
    from accounts.models import User
    from orders import serializers, views

    if (settings.SETTINGS_MODULE != "config.performance_settings"
            or connection.settings_dict["NAME"] != "yalla_perf"):
        raise RuntimeError("Requires the isolated performance database")
    output = Path("/artifacts") / f"serializer-comparison-{args.run_id}.json"
    if output.exists() or output.with_suffix(".csv").exists():
        raise RuntimeError("Preserve the previous comparison; choose a new run filename")

    class LegacyOrderSerializer(serializers.OrderSerializer):
        """Address summary fields were rebuilt for every fallback address."""

        def get_delivery_address(self, instance):
            return instance.delivery_address_snapshot or serializers.order_delivery_address_data(
                instance.delivery_address
            )

    manifest = json.loads(Path("/artifacts/accounts.private.json").read_text())
    report = {
        "run_id": args.run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "isolated_in_process_diagnostic_not_http_capacity",
        "services": "one-off diagnostic process with PostgreSQL and Redis; no Gunicorn or load generator",
        "source_sha256": hashlib.sha256(Path(serializers.__file__).read_bytes()).hexdigest(),
        "warmup_per_variant": 1,
        "measured_rounds": 5,
        "samples": [],
        "completed": False,
    }
    variants = [("before", LegacyOrderSerializer), ("after", serializers.OrderSerializer)]
    for account in manifest["accounts"][:2]:
        user = User.objects.get(pk=account["user_id"])
        client = APIClient()
        client.force_authenticate(user)
        count = user.orders.count()
        reference = None
        for round_number in range(6):
            for name, serializer in (variants if round_number % 2 == 0 else variants[::-1]):
                sql_times = []

                def capture(execute, sql, params, many, context):
                    started = time.perf_counter()
                    try:
                        return execute(sql, params, many, context)
                    finally:
                        sql_times.append((time.perf_counter() - started) * 1000)

                started = time.perf_counter()
                with (patch.object(views.ClientOrderListView, "serializer_class", serializer),
                      connection.execute_wrapper(capture)):
                    response = client.get("/api/v1/orders/my/")
                elapsed = (time.perf_counter() - started) * 1000
                digest = hashlib.sha256(response.content).hexdigest()
                if response.status_code != 200 or len(response.data) != count:
                    raise RuntimeError("Unexpected order history response")
                if reference is None:
                    reference = digest
                if digest != reference:
                    raise RuntimeError("Response changed between serializers")
                if round_number:
                    report["samples"].append({
                        "variant": name, "round": round_number, "orders": count,
                        "elapsed_ms": elapsed, "sql_ms": sum(sql_times),
                        "queries": len(sql_times), "response_bytes": len(response.content),
                        "response_sha256": digest,
                    })
                    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["summaries"] = [
        {"orders": count, "variant": name,
         "median_ms": statistics.median(
             row["elapsed_ms"] for row in report["samples"]
             if row["orders"] == count and row["variant"] == name)}
        for count in sorted({row["orders"] for row in report["samples"]})
        for name, _ in variants
    ]
    report["completed"] = True
    with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report["samples"][0]))
        writer.writeheader()
        writer.writerows(report["samples"])
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summaries"]))


if __name__ == "__main__":
    main()
