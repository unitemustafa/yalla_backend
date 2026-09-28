"""Small, read-only HTTP load probe for a deployed API endpoint.

Example: python tools/load_smoke.py https://api.example.com/healthz/ --users 20 --requests 400
Set LOAD_TEST_BEARER_TOKEN in the environment for an authenticated GET.
"""

import argparse
import math
import os
import ssl
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def probe(url, token, timeout, forwarded_https, host, ssl_context):
    headers = {"User-Agent": "YallaLoadSmoke/1.0", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if forwarded_https:
        headers["X-Forwarded-Proto"] = "https"
    if host:
        headers["Host"] = host
    started = time.perf_counter()
    try:
        with urlopen(
            Request(url, headers=headers), timeout=timeout, context=ssl_context
        ) as response:
            response.read()
            status = response.status
    except HTTPError as error:
        status = error.code
        error.close()
    except (URLError, TimeoutError, OSError):
        status = "network_error"
    return status, (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Full URL of a read-only GET endpoint")
    parser.add_argument(
        "--users", type=int, default=10, help="Concurrent clients (1-100)"
    )
    parser.add_argument(
        "--requests", type=int, default=200, help="Total GETs (1-10000)"
    )
    parser.add_argument(
        "--timeout", type=float, default=10, help="Per-request timeout in seconds"
    )
    parser.add_argument(
        "--forwarded-https",
        action="store_true",
        help="For isolated local Gunicorn tests behind a trusted proxy",
    )
    parser.add_argument("--host", help="Host header for a loopback test")
    parser.add_argument("--ca-file", help="CA certificate for a local HTTPS test")
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parser.error("url must be an absolute HTTP(S) URL")
    if args.forwarded_https and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        parser.error("--forwarded-https is limited to local loopback tests")
    if args.host and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("--host is limited to local loopback tests")
    if not 1 <= args.users <= 100 or not 1 <= args.requests <= 10000:
        parser.error("users must be 1-100 and requests must be 1-10000")
    if args.timeout <= 0:
        parser.error("timeout must be positive")

    token = os.environ.get("LOAD_TEST_BEARER_TOKEN", "")
    ssl_context = (
        ssl.create_default_context(cafile=args.ca_file) if args.ca_file else None
    )
    statuses = Counter()
    durations = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.users) as executor:
        futures = [
            executor.submit(
                probe,
                args.url,
                token,
                args.timeout,
                args.forwarded_https,
                args.host,
                ssl_context,
            )
            for _ in range(args.requests)
        ]
        for future in as_completed(futures):
            status, duration = future.result()
            statuses[status] += 1
            durations.append(duration)
    elapsed = time.perf_counter() - started
    print(f"requests={args.requests} users={args.users} elapsed_s={elapsed:.2f}")
    print(f"throughput_rps={args.requests / elapsed:.2f}")
    print(
        "statuses="
        + ", ".join(
            f"{key}:{count}"
            for key, count in sorted(statuses.items(), key=lambda item: str(item[0]))
        )
    )
    print(
        "latency_ms "
        + " ".join(
            f"{label}={percentile(durations, fraction):.1f}"
            for label, fraction in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99))
        )
    )
    if any(not isinstance(status, int) or status >= 400 for status in statuses):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
