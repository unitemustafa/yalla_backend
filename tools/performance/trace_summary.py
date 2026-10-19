"""Diagnostic inclusive timeline spans; never substitute them for FrameTiming."""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.performance.metrics import distribution


def summarize_trace(data):
    stacks, durations = defaultdict(list), defaultdict(list)
    unmatched_end = 0
    for event in sorted(data["traceEvents"], key=lambda event: event.get("ts", 0)):
        key = (event.get("pid"), event.get("tid"))
        phase = event.get("ph")
        if phase == "B":
            stacks[key].append(event)
        elif phase == "E":
            if not stacks[key]:
                unmatched_end += 1
                continue
            begin = stacks[key].pop()
            durations[begin["name"]].append((event["ts"] - begin["ts"]) / 1000)
        elif phase == "X":
            durations[event["name"]].append(event["dur"] / 1000)
    return {
        "definition": "Inclusive synchronous B/E and X spans by thread; overlaps must not be added together; trace overhead excluded from acceptance",
        "unmatched_end": unmatched_end,
        "unmatched_begin": sum(len(stack) for stack in stacks.values()),
        "spans": {
            name: {**distribution(values), "inclusive_sum_ms": sum(values)}
            for name, values in durations.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize_trace(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with args.output.with_suffix(".csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        fields = ["n", "p50_ms", "p95_ms", "p99_ms", "max_ms", "inclusive_sum_ms"]
        writer.writerow(["span"] + fields)
        for name, value in result["spans"].items():
            writer.writerow([name] + [value[field] for field in fields])
    print("Timeline spans: " + str(len(result["spans"])))


if __name__ == "__main__":
    main()
