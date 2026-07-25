"""Memory Usage Monitor.

Tracks system memory (RAM & Swap) consumption over time and logs periodic stats
to a CSV file.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


CSV_FIELDNAMES = [
    "timestamp",
    "ram_total_mb",
    "ram_used_mb",
    "ram_free_mb",
    "ram_percent",
    "swap_total_mb",
    "swap_used_mb",
    "swap_free_mb",
    "swap_percent",
]


def get_memory_sample() -> Dict[str, Any]:
    """Capture a snapshot of system memory (RAM and Swap).

    Returns:
        Dictionary containing memory metrics in MB and percentages.
    """
    if not HAS_PSUTIL:
        raise RuntimeError("psutil module is required for memory usage monitoring.")

    virtual_mem = psutil.virtual_memory()
    swap_mem = psutil.swap_memory()

    mb = 1024 * 1024

    return {
        "timestamp": datetime.now().isoformat(),
        "ram_total_mb": round(virtual_mem.total / mb, 2),
        "ram_used_mb": round(virtual_mem.used / mb, 2),
        "ram_free_mb": round(virtual_mem.available / mb, 2),
        "ram_percent": round(virtual_mem.percent, 2),
        "swap_total_mb": round(swap_mem.total / mb, 2),
        "swap_used_mb": round(swap_mem.used / mb, 2),
        "swap_free_mb": round(swap_mem.free / mb, 2),
        "swap_percent": round(swap_mem.percent, 2),
    }


def initialize_csv(filepath: str) -> None:
    """Ensure CSV file exists with standard headers.

    Args:
        filepath: Path to the target CSV log file.
    """
    file_exists = os.path.exists(filepath)
    if not file_exists:
        # Create directory if necessary
        dirname = os.path.dirname(filepath)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()


def append_to_csv(filepath: str, sample: Dict[str, Any]) -> None:
    """Append a memory sample record to CSV log file.

    Args:
        filepath: Path to CSV log file.
        sample: Dictionary containing memory metrics.
    """
    initialize_csv(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writerow(sample)


def run_monitor(
    output_file: str, interval: float = 2.0, count: Optional[int] = None
) -> None:
    """Run memory monitoring loop.

    Args:
        output_file: CSV file path to record stats.
        interval: Sampling interval in seconds.
        count: Number of iterations to sample (None for infinite).
    """
    print(
        f"Starting memory usage monitoring... Logging to '{output_file}' "
        f"every {interval}s."
    )
    iterations = 0
    try:
        while count is None or iterations < count:
            sample = get_memory_sample()
            append_to_csv(output_file, sample)
            ram_u = sample["ram_used_mb"]
            ram_t = sample["ram_total_mb"]
            swap_u = sample["swap_used_mb"]
            swap_t = sample["swap_total_mb"]
            print(
                f"[{sample['timestamp']}] RAM: {sample['ram_percent']}% "
                f"({ram_u}/{ram_t} MB) | Swap: {sample['swap_percent']}% "
                f"({swap_u}/{swap_t} MB)"
            )
            iterations += 1
            if count is None or iterations < count:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")


def main() -> None:
    """CLI entry point for Memory Usage Monitor."""
    parser = argparse.ArgumentParser(
        description="Track system RAM and Swap usage over time."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="memory_log.csv",
        help="Path to CSV log file (default: memory_log.csv)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=2.0,
        help="Sampling interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        help="Number of samples to record before exiting (default: continuous)",
    )

    args = parser.parse_args()

    if not HAS_PSUTIL:
        print(
            "Error: psutil is not installed. Please install with 'pip install psutil'.",
            file=sys.stderr,
        )
        sys.exit(1)

    run_monitor(args.output, interval=args.interval, count=args.count)


if __name__ == "__main__":
    main()
