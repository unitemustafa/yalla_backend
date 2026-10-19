"""Pure, auditable statistics: no successful-repeat selection or averaging p95s."""

import math
from collections import Counter


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def distribution(values):
    return {
        "n": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values) if values else None,
    }


def frames(values_us, hz=60):
    if not math.isfinite(hz) or hz <= 0:
        raise ValueError("Refresh rate must be finite and positive")
    if any(not math.isfinite(x) or x < 0 for x in values_us):
        raise ValueError("Frame durations must be finite and nonnegative")
    budget = 1000000 / hz
    # Integer microsecond recordings round the 60 Hz budget to 16667 us.
    late = sum(n > round(budget) for n in values_us)
    result = distribution([n / 1000 for n in values_us])
    result.update(
        budget_ms=budget / 1000,
        late_frames=late,
        late_percent=100 * late / len(values_us) if values_us else None,
        passes=bool(values_us)
        and late / len(values_us) < 0.05
        and max(values_us) <= 100000,
    )
    return result


def requests_summary(rows, duration_s):
    if duration_s <= 0:
        raise ValueError("Measurement duration must be positive")
    groups = {}
    for row in rows:
        if row.get("phase") != "measurement":
            continue
        groups.setdefault(row["name"], []).append(row)
    output = {}
    for name, entries in groups.items():
        codes = Counter(str(r.get("status", 0)) for r in entries)
        result = distribution([r["duration_ms"] for r in entries])
        failed = sum(not r["ok"] for r in entries)
        limited = sum(r.get("status") == 429 for r in entries)
        result.update(
            statuses=dict(codes),
            failures=failed,
            rate_limited=limited,
            unexpected_failures=failed - limited,
            rps=len(entries) / duration_s,
            bytes=sum(r.get("bytes", 0) for r in entries),
        )
        result["within_initial_latency"] = result["p95_ms"] <= (
            3000 if name == "order_create" else 2000
        )
        output[name] = result
    return output


def journeys_summary(rows, start_epoch=None, end_epoch=None):
    """Keep boundary attempts visible, outside complete-window percentiles."""
    groups, boundary = {}, 0
    for row in rows:
        if row.get("phase") == "boundary":
            boundary += 1
            continue
        if row.get("phase") != "measurement":
            continue
        started = row["time"] - row["duration_ms"] / 1000
        if start_epoch is not None and (
            started < start_epoch or row["time"] >= end_epoch
        ):
            boundary += 1
            continue
        groups.setdefault(row["name"], []).append(row)
    return {
        "boundary_rows": boundary,
        "groups": {
            name: {
                **distribution([r["duration_ms"] for r in entries]),
                "failures": sum(not r["ok"] for r in entries),
                "definition": "Whole journey within measurement window, including 2-5s think time",
            }
            for name, entries in groups.items()
        },
    }
