"""Run separately from load: query counts, query time, and read-only plans."""

import hashlib
import json
import os
import time
from pathlib import Path


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.performance_settings")
    import django

    django.setup()
    from django.conf import settings
    from django.db import connection
    from rest_framework.test import APIClient
    from accounts.models import User

    if (
        settings.SETTINGS_MODULE != "config.performance_settings"
        or connection.settings_dict["NAME"] != "yalla_perf"
    ):
        raise RuntimeError("Diagnostics require the isolated performance database")
    manifest = json.loads(Path("/artifacts/accounts.private.json").read_text())
    client = APIClient()
    client.force_authenticate(User.objects.get(pk=manifest["accounts"][0]["user_id"]))
    output = []
    for catalog in manifest["catalogs"]:
        for name, route in (
            (
                "page_30",
                f"/api/v1/home/markets/{catalog['market_id']}/storefront/products/?page_size=30",
            ),
            (
                "metadata",
                f"/api/v1/home/markets/{catalog['market_id']}/storefront/?include_products=false",
            ),
            ("order_history_1000", "/api/v1/orders/my/"),
        ):
            account = manifest["accounts"][
                1
                if name == "order_history_1000"
                and catalog["count"] == min(c["count"] for c in manifest["catalogs"])
                else 0
            ]
            user = User.objects.get(pk=account["user_id"])
            client.force_authenticate(user)
            history_count = (
                user.orders.count() if name == "order_history_1000" else None
            )
            queries = []

            def capture(execute, sql, params, many, context):
                started = time.perf_counter()
                try:
                    return execute(sql, params, many, context)
                finally:
                    queries.append(
                        (sql, params, (time.perf_counter() - started) * 1000)
                    )

            started = time.perf_counter()
            with connection.execute_wrapper(capture):
                response = client.get(route)
            record = {
                "scenario": name,
                "catalog_count": catalog["count"],
                "status": response.status_code,
                "history_count": history_count,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "response_bytes": len(response.content),
                "query_count": len(queries),
                "sql_ms": sum(q[2] for q in queries),
                "plans": [],
            }
            for sql, params, duration in sorted(
                queries, key=lambda q: q[2], reverse=True
            )[:3]:
                if not sql.lstrip().upper().startswith("SELECT"):
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
                    )
                    plan = cursor.fetchone()[0]
                record["plans"].append(
                    {
                        "query_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                        "duration_ms": duration,
                        "plan": plan,
                    }
                )
            output.append(record)
    Path("/artifacts/query-diagnostics.json").write_text(
        json.dumps(
            {
                "scope": "separate_in_process_diagnostic_not_http_benchmark",
                "scenarios": output,
            },
            indent=2,
        )
    )
    print("Query diagnostics written; no request bodies or SQL parameters exported")


if __name__ == "__main__":
    main()
