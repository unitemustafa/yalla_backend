"""Independent, sequential authentication samples against local Staging only."""

import argparse
import csv
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import psutil

from tools.performance.metrics import distribution

ROOT = Path(__file__).resolve().parent
BASES = ("http://127.0.0.1:18080", "http://127.0.0.1:18081")
ENDPOINTS = ("/api/v1/auth/login/client", "/api/v1/auth/refresh/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def persist_session(path, manifest, account, session):
    """Keep synthetic load fixtures usable after client login rotates a session."""
    if not all(
        isinstance(session.get(key), str) and session[key]
        for key in ("accessToken", "refreshToken")
    ):
        raise ValueError("Cannot persist an incomplete authentication session")
    account["access"] = session["accessToken"]
    account["refresh"] = session["refreshToken"]
    temporary = path.with_suffix(".auth.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def request(opener, base, endpoint, payload):
    if base not in BASES or endpoint not in ENDPOINTS:
        raise ValueError("Only isolated loopback Staging is allowed")
    request_id = "auth-probe:" + uuid.uuid4().hex
    started = time.perf_counter()
    code, body = 0, b""
    try:
        with opener.open(
            Request(
                base + endpoint,
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id,
                },
            ),
            timeout=20,
        ) as response:
            code, body = response.status, response.read()
    except HTTPError as error:
        code, body = error.code, error.read()
    except (URLError, TimeoutError):
        pass
    duration = (time.perf_counter() - started) * 1000
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    valid = (
        code == 200
        and isinstance(data, dict)
        and isinstance(data.get("accessToken"), str)
        and bool(data["accessToken"])
    )
    return data, {
        "endpoint": endpoint,
        "duration_ms": duration,
        "status": code,
        "valid": valid,
        "response_bytes": len(body),
        "request_id": request_id,
        "host_memory_percent": psutil.virtual_memory().percent,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", choices=BASES, default=BASES[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=range(1, 31), default=30)
    parser.add_argument("--interval", type=float, default=4)
    args = parser.parse_args()
    if args.interval < 2:
        parser.error("Keep at least two seconds between accounts")
    if args.output.exists():
        parser.error("Existing measurement output must be preserved")
    manifest_path = ROOT / "artifacts/accounts.private.json"
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("environment") != "isolated-local-performance"
        or len(manifest["accounts"]) < args.count
    ):
        parser.error("Isolated independent account fixtures are required")
    args.output.mkdir(parents=True)
    opener, rows = build_opener(NoRedirect()), []
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "count_requested": args.count,
        "interval_seconds": args.interval,
        "rate_limits": "unchanged",
        "scope": "sequential_local_auth_not_capacity",
    }
    for index, account in enumerate(manifest["accounts"][: args.count]):
        login, row = request(
            opener,
            args.base,
            "/api/v1/auth/login/client",
            {"email": account["email"], "password": account["password"]},
        )
        rows.append(row)
        if row["valid"] and isinstance(login.get("refreshToken"), str):
            refreshed, row = request(
                opener,
                args.base,
                "/api/v1/auth/refresh/",
                {"refresh": login["refreshToken"]},
            )
            rows.append(row)
            session = {**login, **refreshed} if row["valid"] else login
            persist_session(manifest_path, manifest, account, session)
        with (args.output / "samples.jsonl").open("a", encoding="utf-8") as stream:
            for value in (
                rows[-2:]
                if len(rows) >= 2 and rows[-1]["endpoint"].endswith("refresh/")
                else rows[-1:]
            ):
                stream.write(json.dumps(value) + "\n")
        print(f"Authentication account sample {index + 1}/{args.count}", flush=True)
        if index + 1 < args.count:
            time.sleep(args.interval)
    summaries = {}
    for endpoint in ("/api/v1/auth/login/client", "/api/v1/auth/refresh/"):
        group = [r for r in rows if r["endpoint"] == endpoint]
        summaries[endpoint] = {
            "attempts": len(group),
            "successful": distribution([r["duration_ms"] for r in group if r["valid"]]),
            "rate_limited": sum(r["status"] == 429 for r in group),
            "failures": sum(not r["valid"] for r in group),
        }
    complete = all(v["successful"]["n"] == args.count for v in summaries.values())
    (args.output / "report.json").write_text(
        json.dumps(
            {**metadata, "completed": complete, "endpoints": summaries}, indent=2
        ),
        encoding="utf-8",
    )
    with (args.output / "samples.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
