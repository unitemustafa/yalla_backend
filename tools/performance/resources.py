"""Parse Android samples without treating stale cpuinfo windows as current CPU."""

import re


def summarize_resources(rows):
    pss, cpu, temperatures = [], [], []
    for row in rows:
        match = re.search(r"TOTAL PSS:\s*(\d+)", row.get("memory", ""))
        if match:
            pss.append(int(match[1]) / 1024)
        if row.get("cpu_method", "").startswith("top second"):
            for line in row.get("cpu", "").splitlines():
                if line.strip().endswith("com.yallamarket.app.performance"):
                    fields = line.split()
                    if len(fields) >= 12:
                        cpu.append(float(fields[8]))
        match = re.search(r"temperature:\s*(\d+)", row.get("battery", ""))
        if match:
            temperatures.append(int(match[1]) / 10)
    return {
        "samples": len(rows),
        "duration_s": rows[-1]["time"] - rows[0]["time"] if rows else 0,
        "pss_samples": len(pss),
        "pss_first_mib": pss[0] if pss else None,
        "pss_last_mib": pss[-1] if pss else None,
        "pss_max_mib": max(pss) if pss else None,
        "current_cpu_samples": len(cpu),
        "cpu_mean_one_core_percent": sum(cpu) / len(cpu) if cpu else None,
        "cpu_max_sample_one_core_percent": max(cpu) if cpu else None,
        "battery_max_c": max(temperatures) if temperatures else None,
        "limitations": "CPU is a one-second sample every five seconds, not a continuous peak; USB charging excludes battery-life inference",
    }
