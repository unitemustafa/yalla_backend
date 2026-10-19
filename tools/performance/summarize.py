"""Summarize mobile raw timings with the same tested statistics as server runs."""

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.performance.metrics import distribution, frames


def summarize_mobile(data):
    result = {key: value for key, value in data.items() if not isinstance(value, dict)}
    result["scenarios"] = {}
    for name, value in data.items():
        if not isinstance(value, dict) or "frame_build_times" not in value:
            continue
        ui = frames(value["frame_build_times"], data.get("refresh_hz", 60))
        raster = frames(
            value.get("frame_rasterizer_times", []), data.get("refresh_hz", 60)
        )
        result["scenarios"][name] = {
            "ui": ui,
            "raster": raster,
            "passes": ui["passes"] and raster["passes"],
        }
    result["actions"] = {}
    for name, value in data.get("observations", {}).items():
        if isinstance(value, list) and ("_us" in name):
            result["actions"][name] = distribution([x / 1000 for x in value])
    result["observations"] = data.get("observations", {})
    result["search_input_quality"] = (
        "verified_profile_text_callback"
        if result["observations"].get("search_input_method")
        == "EditableTextState.updateEditingValue"
        else "invalid_legacy_profile_text_input"
        if "search_action_us" in result["observations"]
        else "not_applicable"
    )
    scroll_count = sum("scroll" in name for name in result["scenarios"])
    motion = [
        v
        for v in result["observations"].values()
        if isinstance(v, dict) and "distance_px" in v
    ]
    motion_valid = len(motion) == scroll_count and all(
        v["elapsed_ms"] >= 30000
        and v["distance_px"] > 0
        and v["moving_flings"] >= 5
        and v["moving_flings"] / v["flings"] >= 0.8
        for v in motion
    )
    result["scroll_motion_quality"] = (
        "not_applicable"
        if not scroll_count
        else "legacy_motion_unverified"
        if not data.get("scroll_protocol")
        else "verified_motion_v2"
        if motion_valid
        else "motion_verification_failed"
    )
    result["all_recorded_frames_pass"] = bool(result["scenarios"]) and all(
        s["passes"] for s in result["scenarios"].values()
    )
    result["full_plan_complete"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        parser.error("No mobile timing data was returned")
    summary = summarize_mobile(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, value in data.items():
        if isinstance(value, dict) and "traceEvents" in value:
            safe_name = "".join(c for c in name if c.isalnum() or c in "-_")
            args.output.with_name(
                args.output.stem + "-" + safe_name + ".trace.json"
            ).write_text(json.dumps(value), encoding="utf-8")
    with args.output.with_suffix(".csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "scenario",
                "thread",
                "n",
                "p50_ms",
                "p95_ms",
                "p99_ms",
                "max_ms",
                "late_percent",
                "passes",
            ]
        )
        for name, scenario in summary["scenarios"].items():
            for thread in ("ui", "raster"):
                value = scenario[thread]
                writer.writerow(
                    [name, thread]
                    + [
                        value.get(key)
                        for key in (
                            "n",
                            "p50_ms",
                            "p95_ms",
                            "p99_ms",
                            "max_ms",
                            "late_percent",
                            "passes",
                        )
                    ]
                )
    with args.output.with_suffix(".actions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        keys = ("n", "p50_ms", "p95_ms", "p99_ms", "max_ms")
        writer.writerow(["action", *keys, "search_input_quality"])
        for name, value in summary["actions"].items():
            writer.writerow(
                [
                    name,
                    *(value[key] for key in keys),
                    summary["search_input_quality"]
                    if "search" in name
                    else "not_applicable",
                ]
            )
    print(
        f"Recorded {len(summary['scenarios'])} scenarios; all pass={summary['all_recorded_frames_pass']}"
    )


if __name__ == "__main__":
    main()
