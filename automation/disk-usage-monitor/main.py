"""Disk Usage Monitor.

Monitors disk space usage across mounts and triggers warning alerts/logs
when free space drops below threshold %.
"""

import argparse
import json
import logging
import os
import shutil
import string
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def setup_logger(log_file: Optional[str] = None) -> logging.Logger:
    """Configure logger for disk usage monitoring alerts.

    Args:
        log_file: Optional path to file for log messages.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger("DiskUsageMonitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_mount_points() -> List[str]:
    """Retrieve list of active mount points / disk roots.

    Returns:
        List of mount paths.
    """
    mounts = []
    if HAS_PSUTIL:
        try:
            for part in psutil.disk_partitions(all=False):
                if part.mountpoint and os.path.exists(part.mountpoint):
                    mounts.append(part.mountpoint)
        except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
            pass

    if not mounts:
        # Fallback to root or drive letters
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    mounts.append(drive)
        else:
            mounts.append("/")

    return list(set(mounts))


def check_disk_usage(mount_point: str) -> Dict[str, Any]:
    """Get total, used, free bytes, and free percentage for a mount point.

    Args:
        mount_point: Directory path/mount point to check.

    Returns:
        Dictionary with usage metrics.
    """
    usage = shutil.disk_usage(mount_point)
    total_gb = usage.total / (1024**3)
    used_gb = usage.used / (1024**3)
    free_gb = usage.free / (1024**3)
    free_percent = (usage.free / usage.total) * 100.0 if usage.total > 0 else 0.0
    used_percent = (usage.used / usage.total) * 100.0 if usage.total > 0 else 0.0

    return {
        "mount": mount_point,
        "total_gb": round(total_gb, 2),
        "used_gb": round(used_gb, 2),
        "free_gb": round(free_gb, 2),
        "used_percent": round(used_percent, 2),
        "free_percent": round(free_percent, 2),
    }


def evaluate_thresholds(
    usage_list: List[Dict[str, Any]],
    threshold_percent: float,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    """Evaluate usage records against free space threshold.

    Args:
        usage_list: List of disk usage metric dicts.
        threshold_percent: Free space % threshold below which an alert is sent.
        logger: Logger instance to output warnings.

    Returns:
        List of alerts generated.
    """
    # pylint: disable=logging-fstring-interpolation
    alerts = []
    for item in usage_list:
        if item["free_percent"] < threshold_percent:
            msg = (
                f"ALERT: Low free disk space on '{item['mount']}'! "
                f"Free: {item['free_percent']:.2f}% ({item['free_gb']} GB), "
                f"Threshold: {threshold_percent:.2f}%"
            )
            logger.warning(msg)
            alerts.append(
                {
                    "mount": item["mount"],
                    "free_percent": item["free_percent"],
                    "free_gb": item["free_gb"],
                    "message": msg,
                }
            )
        else:
            free_p = item["free_percent"]
            free_g = item["free_gb"]
            logger.info(
                f"OK: '{item['mount']}' free space: {free_p:.2f}% ({free_g} GB)"
            )
    return alerts


def export_report_json(report_data: Dict[str, Any], filepath: str) -> None:
    """Export disk monitoring report to a JSON file.

    Args:
        report_data: Report dictionary.
        filepath: Target JSON file path.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)


def main() -> None:
    """CLI entry point for disk usage monitor."""
    # pylint: disable=logging-fstring-interpolation
    parser = argparse.ArgumentParser(
        description="Monitor disk space usage across mounts."
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=15.0,
        help="Free space warning threshold %% (default: 15.0%%)",
    )
    parser.add_argument(
        "-m",
        "--mount",
        type=str,
        help="Specific mount point or directory to check (checks all if omitted)",
    )
    parser.add_argument("-l", "--log-file", type=str, help="Path to write log output")
    parser.add_argument(
        "-o", "--output-json", type=str, help="Path to export report as JSON"
    )

    args = parser.parse_args()
    logger = setup_logger(args.log_file)

    mounts = [args.mount] if args.mount else get_mount_points()
    logger.info(
        f"Checking disk usage for mounts: {mounts} "
        f"(Free space threshold: {args.threshold}%)"
    )

    usage_results = []
    for mount in mounts:
        try:
            usage_results.append(check_disk_usage(mount))
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error(f"Failed to check mount '{mount}': {err}")

    alerts = evaluate_thresholds(usage_results, args.threshold, logger)

    report = {
        "timestamp": datetime.now().isoformat(),
        "threshold_free_percent": args.threshold,
        "results": usage_results,
        "alerts_count": len(alerts),
        "alerts": alerts,
    }

    if args.output_json:
        export_report_json(report, args.output_json)
        logger.info(f"Report saved to '{args.output_json}'.")


if __name__ == "__main__":
    main()
