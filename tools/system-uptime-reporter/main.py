"""System Uptime Reporter.

Reports system uptime, boot timestamp, and load averages in formatted
human-readable text or JSON export.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import sys
import time
from typing import Any, Dict, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught,import-outside-toplevel


try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False


def get_boot_timestamp() -> float:
    """Get system boot timestamp in epoch seconds."""
    if HAS_PSUTIL and psutil is not None:
        return float(psutil.boot_time())

    # Fallback mechanisms
    if platform.system() == "Linux":
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                uptime_seconds = float(f.readline().split()[0])
                return float(time.time() - uptime_seconds)
        except Exception:  # nosec B110
            pass
    elif platform.system() == "Windows":
        try:
            import ctypes

            lib = ctypes.windll.kernel32
            uptime_ms = lib.GetTickCount64()
            return float(time.time() - (uptime_ms / 1000.0))
        except Exception:  # nosec B110
            pass

    # Default fallback to start of process if OS metrics unavailable
    return float(time.time())


def format_uptime_duration(seconds: float) -> str:
    """Formats duration seconds into X days, Y hours, Z mins, W secs."""
    sec = int(seconds)
    days, sec = divmod(sec, 86400)
    hours, sec = divmod(sec, 3600)
    minutes, sec = divmod(sec, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0 or days > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    parts.append(f"{sec} sec{'s' if sec != 1 else ''}")

    return ", ".join(parts)


def get_load_averages() -> Dict[str, Any]:
    """Get 1, 5, 15 minute system load averages if supported."""
    load_dict: Dict[str, Any] = {"1m": None, "5m": None, "15m": None}

    if hasattr(os, "getloadavg"):
        try:
            l1, l5, l15 = os.getloadavg()
            load_dict = {
                "1m": round(l1, 2),
                "5m": round(l5, 2),
                "15m": round(l15, 2),
            }
        except OSError:
            pass
    elif HAS_PSUTIL and psutil is not None and hasattr(psutil, "getloadavg"):
        try:
            l1, l5, l15 = psutil.getloadavg()
            load_dict = {
                "1m": round(l1, 2),
                "5m": round(l5, 2),
                "15m": round(l15, 2),
            }
        except (AttributeError, OSError):
            pass

    if load_dict["1m"] is None and HAS_PSUTIL and psutil is not None:
        # Fallback to CPU percentage on systems like Windows
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            load_dict["cpu_usage_percent"] = cpu_percent
        except Exception:  # nosec B110
            pass

    return load_dict


def get_system_uptime_report() -> Dict[str, Any]:
    """Generate complete system uptime and platform diagnostic dictionary."""
    boot_time = get_boot_timestamp()
    now = time.time()
    uptime_sec = max(0.0, now - boot_time)

    boot_dt = datetime.datetime.fromtimestamp(boot_time, datetime.timezone.utc)

    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "boot_timestamp": boot_time,
        "boot_iso_utc": boot_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "uptime_seconds": round(uptime_sec, 2),
        "uptime_formatted": format_uptime_duration(uptime_sec),
        "load_average": get_load_averages(),
    }


def format_text_report(report: Dict[str, Any]) -> str:
    """Format report dictionary into clean printable text block."""
    lines = [
        "========== System Uptime Report ==========",
        f" Hostname        : {report['hostname']}",
        f" OS Platform     : {report['platform']}",
        f" Boot Timestamp  : {report['boot_iso_utc']}",
        f" System Uptime   : {report['uptime_formatted']}",
    ]
    load = report["load_average"]
    if load.get("1m") is not None:
        load_str = f"1m: {load['1m']}, 5m: {load['5m']}, 15m: {load['15m']}"
        lines.append(f" Load Average    : {load_str}")
    elif load.get("cpu_usage_percent") is not None:
        lines.append(f" CPU Usage       : {load['cpu_usage_percent']}%")
    lines.append("==========================================")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="System Uptime Reporter")
    parser.add_argument(
        "--json", action="store_true", help="Output summary report as JSON"
    )
    return parser


def main(args: Optional[list[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    report = get_system_uptime_report()
    if parsed.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_text_report(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
