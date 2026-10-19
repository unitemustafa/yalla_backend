"""Supervise isolated load, preserve raw repeats, and classify coverage honestly."""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.performance.collect import COMPOSE, ROOT, command, inventory, snapshot
from tools.performance.metrics import journeys_summary, requests_summary


def read_rows(path):
    if not path.exists():
        return []
    rows = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except ValueError:
            if index == len(lines) - 1 and not content.endswith("\n"):
                break  # The writer may still be appending this final record.
            raise ValueError(
                f"Corrupt measurement record {index + 1}: {path.name}"
            ) from None
    return rows


def generator_sample(root, previous, elapsed):
    """Include the real interpreter behind Windows virtualenv launchers."""
    current, rss = {}, 0
    try:
        processes = [root] + root.children(recursive=True)
    except psutil.Error:
        processes = []
    for process in processes:
        try:
            cpu = process.cpu_times()
            current[process.pid] = cpu.user + cpu.system
            rss += process.memory_info().rss
        except psutil.Error:
            continue
    delta = sum(
        max(0, value - previous.get(pid, value)) for pid, value in current.items()
    )
    return current, 100 * delta / max(elapsed, 0.001), rss


def stop_generator(process):
    if process.poll() is not None:
        return
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        descendants = []
    for descendant in reversed(descendants):
        try:
            descendant.terminate()
        except psutil.Error:
            pass
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@contextmanager
def managed_generator(args, env, log):
    process = subprocess.Popen(
        args, env=env, cwd=ROOT.parents[1], stdout=log, stderr=subprocess.STDOUT
    )
    try:
        yield process
    finally:
        stop_generator(process)


def classify(rows, duration, samples, *, complete, stop_reason=None):
    samples = [s for s in samples if s.get("phase", "measurement") == "measurement"]
    groups = requests_summary(rows, duration)
    measured = [r for r in rows if r.get("phase") == "measurement"]
    unexpected = sum(not r["ok"] and r.get("status") != 429 for r in measured)
    limited = sum(r.get("status") == 429 for r in measured)
    required = {
        "home",
        "storefront",
        "store_products",
        "product_detail",
        "search",
        "store_filter",
        "order_preview",
        "order_create",
        "order_detail",
        "order_retry",
    }
    missing = sorted(required.difference(groups))
    required_monitoring = {
        "ready",
        "containers",
        "container_states",
        "database",
        "redis",
        "queues",
        "load",
        "generator_cpu_percent",
    }
    monitoring_complete = bool(samples) and all(
        not s.get("errors", [])
        and required_monitoring.issubset(s)
        and bool(s["container_states"])
        and bool(s["database"])
        for s in samples
    )
    generator_saturated = any(s.get("generator_cpu_percent", 0) > 85 for s in samples)
    lifecycle_problem = any(
        c["state"] != "running" or c["oom"] or c["restarts"] > 0
        for s in samples
        for c in s.get("container_states", [])
    )
    user_count_problem = any(
        s.get("load", {}).get("active_users") != s.get("load", {}).get("expected_users")
        for s in samples
    )
    deadlocks = [s["database"]["deadlocks"] for s in samples if "database" in s]
    queue_growth = False
    if len(samples) >= 12:
        recent = [sum(s.get("queues", {}).values()) for s in samples[-12:]]
        queue_growth = all(b > a for a, b in zip(recent, recent[1:]))
    stable = (
        complete
        and not stop_reason
        and bool(measured)
        and not missing
        and unexpected / len(measured) < 0.01
        and limited / len(measured) < 0.01
        and all(g["within_initial_latency"] for g in groups.values())
        and monitoring_complete
        and not generator_saturated
        and not queue_growth
        and not lifecycle_problem
        and not user_count_problem
        and (not deadlocks or max(deadlocks) == min(deadlocks))
        and all(s["ready"] for s in samples)
    )
    return {
        "complete": complete,
        "stable": stable,
        "stop_reason": stop_reason,
        "generator_saturated": generator_saturated,
        "monitoring_complete": monitoring_complete,
        "missing_endpoints": missing,
        "queue_growth": queue_growth,
        "lifecycle_problem": lifecycle_problem,
        "user_count_problem": user_count_problem,
        "requests": len(measured),
        "unexpected_failures": unexpected,
        "rate_limited": limited,
        "duration_s": duration,
        "groups": groups,
    }


def run_stage(folder, users, measurement, warmup, base, run_id, *, spike=False):
    # Each invocation has fresh normal-lifetime tokens, including after a
    # safety stop that killed the previous generator before refresh persistence.
    command(
        COMPOSE
        + [
            "exec",
            "-T",
            "app",
            "python",
            "manage.py",
            "seed_performance",
            "--refresh-tokens",
        ],
        timeout=30,
    )
    folder.mkdir(parents=True, exist_ok=False)
    ramp = 0 if spike else math.ceil(users / 2)
    total = ramp + warmup + measurement + 2
    env = dict(
        os.environ,
        PERF_USERS=str(users),
        PERF_WARMUP_S=str(warmup),
        PERF_RUN_ID=run_id,
        PERF_OUT=str(folder),
        PERF_MEASUREMENT_S=str(measurement),
        PERF_SMOKE="1" if folder.name.endswith("smoke") else "0",
        PERF_SHAPE="spike" if spike else "constant",
    )
    args = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(ROOT / "locustfile.py"),
        "--headless",
        "--host",
        base,
        "--users",
        str(users),
        "--spawn-rate",
        "2",
        "--run-time",
        str(total) + "s",
        "--stop-timeout",
        "20",
        "--only-summary",
        "--csv",
        str(folder / "locust"),
        "--csv-full-history",
        "--exit-code-on-error",
        "0",
    ]
    samples, reason = [], None
    with (
        (folder / "locust.log").open("w", encoding="utf-8") as log,
        managed_generator(args, env, log) as process,
    ):
        child = psutil.Process(process.pid)
        previous, _, _ = generator_sample(child, {}, 1)
        last_sample = time.monotonic()
        started = time.monotonic()
        readiness_failures = 0
        last_ready_check = 0
        high_memory_since = None
        while process.poll() is None:
            tick = time.monotonic()
            sample = snapshot(base)
            try:
                sample["load"] = json.loads(
                    (folder / "load-state.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                sample["errors"].append("load_state_unavailable")
            elapsed = time.monotonic() - started
            sample["phase"] = (
                "measurement"
                if ramp + warmup <= elapsed < ramp + warmup + measurement
                else "warmup_or_cooldown"
            )
            previous, cpu, rss = generator_sample(
                child, previous, time.monotonic() - last_sample
            )
            last_sample = time.monotonic()
            sample["generator_cpu_percent"] = cpu
            sample["generator_rss"] = rss
            samples.append(sample)
            with (folder / "resources.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps(sample) + "\n")
            if tick - last_ready_check >= 10:
                readiness_failures = 0 if sample["ready"] else readiness_failures + 1
                last_ready_check = tick
            if sample["host_memory_percent"] > 90:
                high_memory_since = high_memory_since or tick
            else:
                high_memory_since = None
            recent = [
                r
                for r in read_rows(folder / "requests.jsonl")
                if r.get("phase") == "measurement" and r["time"] >= time.time() - 60
            ]
            if readiness_failures >= 2:
                reason = "readiness_failed_twice"
            elif high_memory_since and tick - high_memory_since >= 60:
                reason = "host_memory_above_90_percent_for_60s"
            elif sample["host_disk_percent"] >= 85:
                reason = "host_disk_above_85_percent"
            elif (
                tick - started > ramp + warmup + 60
                and recent
                and sum(not r["ok"] and r["status"] != 429 for r in recent)
                / len(recent)
                > 0.05
            ):
                reason = "unexpected_errors_above_5_percent_for_60s"
            elif tick - started > total + 45:
                reason = "load_generator_shutdown_timeout"
            if reason:
                ended_epoch = time.time()
                stop_generator(process)
                break
            time.sleep(max(0, 5 - (time.monotonic() - tick)))
        if reason is None:
            ended_epoch = time.time()
    rows = read_rows(folder / "requests.jsonl")
    complete = process.returncode == 0 and time.monotonic() - started >= total - 3
    timing_path = folder / "timing.json"
    timing = None
    measured_seconds = 0.0
    if timing_path.exists():
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        measured_seconds = max(
            0,
            min(
                measurement,
                ended_epoch
                - timing["start_epoch"]
                - timing["ramp_s"]
                - timing["warmup_s"],
            ),
        )
    result = classify(
        rows,
        max(measured_seconds, 0.001),
        samples,
        complete=complete,
        stop_reason=reason,
    )
    result.update(
        planned_measurement_s=measurement,
        actual_measurement_s=measured_seconds,
        throughput_usable=complete and measured_seconds >= measurement - 1,
    )
    measurement_start = (
        timing["start_epoch"] + timing["ramp_s"] + timing["warmup_s"]
        if timing
        else None
    )
    journeys = journeys_summary(
        read_rows(folder / "journeys.jsonl"),
        measurement_start,
        measurement_start + measurement if timing else None,
    )
    result["journeys"] = journeys["groups"]
    result["journey_boundary_rows"] = journeys["boundary_rows"]
    result.update(
        stage=folder.name,
        users=users,
        exit_code=process.returncode,
        warmup_s=warmup,
        route="policy" if base.endswith("18080") else "capacity",
    )
    if spike:
        result["segments"] = {
            name: requests_summary(
                [r for r in rows if r.get("spike_segment") == name], seconds
            )
            for name, seconds in (("before", 120), ("peak", 120), ("recovery", 300))
        }
    # Logs are restricted to the performance project, never other containers.
    try:
        (folder / "server.jsonl").write_text(
            command(
                COMPOSE + ["logs", "--no-color", "--since", str(int(total + 60)) + "s"],
                timeout=30,
            ),
            encoding="utf-8",
        )
    except subprocess.SubprocessError:
        result["server_logs"] = "unavailable"
    (folder / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", action="store_true")
    parser.add_argument(
        "--route", choices=["policy", "capacity", "both"], default="both"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--smoke-seconds", type=int, default=60)
    options = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", options.run_id):
        parser.error(
            "run-id requires 1..64 ASCII letters, digits, hyphens or underscores"
        )
    if options.smoke_seconds < 10:
        parser.error("smoke-seconds must be at least 10")
    destination = ROOT / "artifacts" / options.run_id
    destination.mkdir(exist_ok=False)
    (destination / "inventory.json").write_text(
        json.dumps(inventory(), indent=2), encoding="utf-8"
    )
    results = []
    report = {
        "schema_version": 1,
        "run_id": options.run_id,
        "scope": "isolated-local-staging-not-production",
        "campaign_requested": options.campaign,
        "campaign_finished": False,
        "results": results,
        "gaps": [
            "Production resource parity unverified",
            "External FCM/SMTP delivery excluded",
            "Controlled mobile network requires a shaping gateway",
            "iOS and 4GB device unavailable",
        ],
    }

    def checkpoint(value=None, *, finished=False):
        if value is not None:
            results.append(value)
        report["campaign_finished"] = finished
        temporary = destination / "report.tmp"
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(destination / "report.json")

    checkpoint()
    for route in ["policy", "capacity"] if options.route == "both" else [options.route]:
        base = "http://127.0.0.1:" + ("18080" if route == "policy" else "18081")
        smoke = run_stage(
            destination / f"{route}-smoke",
            1,
            options.smoke_seconds,
            5,
            base,
            options.run_id,
        )
        checkpoint(smoke)
        print(
            f"{route} smoke: complete={smoke['complete']} stable={smoke['stable']}",
            flush=True,
        )
        smoke_valid = (
            smoke["complete"]
            and not smoke["stop_reason"]
            and smoke["unexpected_failures"] == 0
            and not smoke["missing_endpoints"]
        )
        if not options.campaign or not smoke_valid:
            continue
        repeats = []
        safety_stopped = False
        for repeat in range(1, 4):
            passed = []
            for users in (10, 25, 50, 100):
                name = f"{route}-r{repeat}-{users}"
                value = run_stage(
                    destination / name, users, 300, 60, base, options.run_id
                )
                checkpoint(value)
                if value["stable"]:
                    passed.append(users)
                print(
                    f"{name}: stable={value['stable']} stop={value['stop_reason']}",
                    flush=True,
                )
                if value["stop_reason"]:
                    safety_stopped = True
                    break
            repeats.append(set(passed))
            if safety_stopped:
                break
        if safety_stopped:
            continue
        common = set.intersection(*repeats)
        if common:
            level = max(common)
            checkpoint(
                run_stage(
                    destination / f"{route}-soak", level, 3600, 60, base, options.run_id
                )
            )
            if results[-1]["stop_reason"]:
                continue
            checkpoint(
                run_stage(
                    destination / f"{route}-spike",
                    level,
                    540,
                    0,
                    base,
                    options.run_id,
                    spike=True,
                )
            )
    checkpoint(finished=True)
    print("Report: " + str(destination / "report.json"), flush=True)


if __name__ == "__main__":
    main()
