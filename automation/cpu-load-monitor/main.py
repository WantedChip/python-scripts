"""CPU Load Monitor.

Records CPU load averages and per-core utilization at intervals, generating
a summary report with peak times.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def sample_cpu(interval_sec: float = 1.0) -> Dict[str, Any]:
    """Capture a single CPU metric sample.

    Args:
        interval_sec: Time in seconds to measure CPU percentage.

    Returns:
        Dictionary with overall load %, per-core %, and load averages.
    """
    if not HAS_PSUTIL:
        raise RuntimeError("psutil module is required for CPU monitoring.")

    overall = psutil.cpu_percent(interval=interval_sec)
    per_core = psutil.cpu_percent(interval=None, percpu=True)

    # Load averages (Linux/macOS getloadavg; Windows returns (0,0,0) or fails)
    load_avg = None
    if hasattr(os, "getloadavg"):
        try:
            load_avg = os.getloadavg()
        except OSError:
            pass
    elif hasattr(psutil, "getloadavg"):
        try:
            load_avg = psutil.getloadavg()
        except AttributeError:
            pass

    return {
        "timestamp": datetime.now().isoformat(),
        "overall_percent": overall,
        "per_core_percent": per_core,
        "load_avg": load_avg,
    }


def generate_summary(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary analysis from collected CPU samples.

    Args:
        samples: List of sample dictionaries.

    Returns:
        Summary metrics including overall avg/peak, peak timestamp, per-core.
    """
    if not samples:
        return {}

    overall_usages = [s["overall_percent"] for s in samples]
    avg_overall = sum(overall_usages) / len(overall_usages)
    max_sample = max(samples, key=lambda s: s["overall_percent"])

    has_cores = bool(samples[0].get("per_core_percent"))
    num_cores = len(samples[0]["per_core_percent"]) if has_cores else 0
    per_core_summary = []

    for core_idx in range(num_cores):
        core_values = [
            s["per_core_percent"][core_idx]
            for s in samples
            if len(s["per_core_percent"]) > core_idx
        ]
        if core_values:
            per_core_summary.append(
                {
                    "core_id": core_idx,
                    "avg_percent": round(sum(core_values) / len(core_values), 2),
                    "peak_percent": round(max(core_values), 2),
                }
            )

    return {
        "total_samples": len(samples),
        "start_time": samples[0]["timestamp"],
        "end_time": samples[-1]["timestamp"],
        "average_overall_percent": round(avg_overall, 2),
        "peak_overall_percent": round(max_sample["overall_percent"], 2),
        "peak_timestamp": max_sample["timestamp"],
        "per_core_summary": per_core_summary,
    }


def print_console_summary(summary: Dict[str, Any]) -> None:
    """Format and print summary report as a clean console table.

    Args:
        summary: Calculated summary dictionary.
    """
    if not summary:
        print("No CPU data collected.")
        return

    print("\n" + "=" * 60)
    print("                CPU LOAD MONITOR SUMMARY REPORT")
    print("=" * 60)
    print(f" Monitoring Window: {summary['start_time']} -> {summary['end_time']}")
    print(f" Total Samples    : {summary['total_samples']}")
    print(f" Average CPU Load : {summary['average_overall_percent']}%")
    print(
        f" Peak CPU Load    : {summary['peak_overall_percent']}% "
        f"(at {summary['peak_timestamp']})"
    )
    print("-" * 60)
    print(" Core ID | Average Usage (%) | Peak Usage (%)")
    print("-" * 60)
    for core in summary.get("per_core_summary", []):
        avg_p = core["avg_percent"]
        peak_p = core["peak_percent"]
        print(f" Core {core['core_id']:<2} | {avg_p:<17} | {peak_p}")
    print("=" * 60 + "\n")


def export_json_report(data: Dict[str, Any], filepath: str) -> None:
    """Export summary report and raw samples to JSON file.

    Args:
        data: Combined data dictionary.
        filepath: Destination file path.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    """CLI entry point for CPU Load Monitor."""
    parser = argparse.ArgumentParser(
        description="Record CPU load averages and per-core utilization."
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=1.0,
        help="Sample duration / interval in seconds",
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=5,
        help="Total number of samples to record (default: 5)",
    )
    parser.add_argument(
        "-o", "--output-json", type=str, help="Export summary and samples to JSON file"
    )

    args = parser.parse_args()

    if not HAS_PSUTIL:
        print(
            "Error: psutil is required. Please run 'pip install psutil'.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Collecting {args.count} CPU samples (interval: {args.interval}s)...")
    samples = []
    for idx in range(1, args.count + 1):
        sample = sample_cpu(interval_sec=args.interval)
        samples.append(sample)
        print(
            f"  Sample {idx}/{args.count}: {sample['overall_percent']}% overall usage"
        )

    summary = generate_summary(samples)
    print_console_summary(summary)

    if args.output_json:
        full_data = {"summary": summary, "samples": samples}
        export_json_report(full_data, args.output_json)
        print(f"Exported JSON report to '{args.output_json}'.")


if __name__ == "__main__":
    main()
