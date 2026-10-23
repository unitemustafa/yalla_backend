"""Short mixed-app campaign on the isolated stack; preserves every stage."""

import json
import os
import sys
import time

import psutil

from tools.performance.collect import COMPOSE, ROOT, command, inventory, snapshot
from tools.performance.run import (
    classify,
    generator_sample,
    managed_generator,
    read_rows,
    stop_generator,
)


def main():
    run_id = "mixed-20261023"
    destination = ROOT / "artifacts" / run_id
    destination.mkdir(exist_ok=False)
    report = {
        "scope": "isolated-stack-on-production-host-loopback-http",
        "limits": "Same host generator, synthetic data, no TLS/mobile/FCM/SMTP benchmark",
        "inventory": inventory(),
        "results": [],
        "finished": False,
    }

    def save():
        temporary = destination / "report.tmp"
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(destination / "report.json")

    save()
    for users, duration in ((10, 45), (50, 60), (100, 300)):
        folder = destination / str(users)
        folder.mkdir()
        warmup, ramp = 20, users / 2
        total = ramp + warmup + duration + 2
        env = dict(
            os.environ,
            PERF_USERS=str(users),
            PERF_WARMUP_S=str(warmup),
            PERF_MEASUREMENT_S=str(duration),
            PERF_RUN_ID=run_id,
            PERF_OUT=str(folder),
        )
        args = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(ROOT / "locust_mixed.py"),
            "--headless",
            "--host",
            "http://127.0.0.1:18081",
            "--users",
            str(users),
            "--spawn-rate",
            "2",
            "--run-time",
            f"{int(total)}s",
            "--stop-timeout",
            "20",
            "--only-summary",
            "--exit-code-on-error",
            "0",
        ]
        samples, reason = [], None
        started = time.monotonic()
        with (folder / "locust.log").open("w", encoding="utf-8") as log:
            with managed_generator(args, env, log) as process:
                child = psutil.Process(process.pid)
                previous, _, _ = generator_sample(child, {}, 1)
                previous_time = time.monotonic()
                while process.poll() is None:
                    tick = time.monotonic()
                    sample = snapshot("http://127.0.0.1:18081")
                    elapsed = time.monotonic() - started
                    sample["phase"] = (
                        "measurement"
                        if ramp + warmup <= elapsed < total - 2
                        else "warmup"
                    )
                    try:
                        sample["load"] = json.loads(
                            (folder / "load-state.json").read_text()
                        )
                    except (OSError, ValueError):
                        sample["errors"].append("load_state_unavailable")
                    previous, cpu, rss = generator_sample(
                        child, previous, time.monotonic() - previous_time
                    )
                    previous_time = time.monotonic()
                    sample.update(generator_cpu_percent=cpu, generator_rss=rss)
                    samples.append(sample)
                    with (folder / "resources.jsonl").open(
                        "a", encoding="utf-8"
                    ) as output:
                        output.write(json.dumps(sample) + "\n")
                    production_health = command(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            "{{.State.Health.Status}}",
                            "yalla-django-1",
                        ]
                    ).strip()
                    if sample["host_memory_percent"] > 85:
                        reason = "host_memory_above_85_percent"
                    elif elapsed > ramp + warmup and not sample["ready"]:
                        reason = "isolated_readiness_failed"
                    elif production_health != "healthy":
                        reason = "production_health_not_healthy"
                    elif elapsed > total + 45:
                        reason = "generator_timeout"
                    if reason:
                        stop_generator(process)
                        break
                    time.sleep(max(0, 5 - (time.monotonic() - tick)))
        elapsed = time.monotonic() - started
        complete = process.returncode == 0 and elapsed >= total - 3
        result = classify(
            read_rows(folder / "requests.jsonl"),
            duration,
            samples,
            complete=complete,
            stop_reason=reason,
        )
        result.update(users=users, stage=str(users), measurement_s=duration)
        result["missing_courier_endpoints"] = sorted(
            {
                "courier_active",
                "courier_history",
                "courier_detail",
                "courier_picked_up",
                "courier_delivered",
                "courier_retry",
            }.difference(result["groups"])
        )
        result["stable"] &= not result["missing_courier_endpoints"]
        result["host_memory_peak_percent"] = max(
            s["host_memory_percent"] for s in samples
        )
        result["host_cpu_peak_percent"] = max(s["host_cpu_percent"] for s in samples)
        report["results"].append(result)
        save()
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in (
                        "users",
                        "complete",
                        "stable",
                        "requests",
                        "unexpected_failures",
                        "rate_limited",
                        "stop_reason",
                        "missing_endpoints",
                        "missing_courier_endpoints",
                    )
                }
            ),
            flush=True,
        )
        if reason or result["unexpected_failures"]:
            break
    report["finished"] = True
    save()
    print("Mixed campaign evidence: " + str(destination / "report.json"), flush=True)


if __name__ == "__main__":
    main()
