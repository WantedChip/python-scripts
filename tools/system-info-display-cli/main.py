"""System Info Display CLI.

Displays system details (OS, CPU usage, RAM, Disk, Uptime, Active Processes)
in a formatted ASCII terminal dashboard or outputs as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught


try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False


def get_uptime_seconds() -> float:
    """Get system uptime in seconds."""
    if HAS_PSUTIL and psutil is not None:
        return float(time.time() - psutil.boot_time())
    try:
        if hasattr(os, "uptime"):
            return float(os.uptime())
    except Exception:  # nosec B110
        pass
    return 0.0


def format_bytes(bytes_val: int) -> str:
    """Format byte counts into human readable strings (GB, MB, KB)."""
    val = float(bytes_val)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if val < 1024.0:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to days, hours, minutes, seconds."""
    secs = int(seconds)
    days, secs = divmod(secs, 86400)
    hours, secs = divmod(secs, 3600)
    minutes, secs = divmod(secs, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def get_system_info(top_n_processes: int = 5) -> Dict[str, Any]:
    """Gather comprehensive system information.

    Args:
        top_n_processes: Number of top active processes to retrieve.

    Returns:
        Dictionary containing OS, CPU, RAM, Disk, Uptime, and Process stats.
    """
    # OS & Host
    sys_info = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
        "python_version": sys.version.split()[0],
        "uptime_seconds": round(get_uptime_seconds(), 2),
        "uptime_formatted": format_duration(get_uptime_seconds()),
    }

    # CPU
    cpu_count_logical = os.cpu_count() or 1
    cpu_count_physical = (
        psutil.cpu_count(logical=False)
        if HAS_PSUTIL and psutil is not None
        else cpu_count_logical
    )
    cpu_usage_pct = (
        psutil.cpu_percent(interval=0.1) if HAS_PSUTIL and psutil is not None else 0.0
    )

    cpu_info = {
        "logical_cores": cpu_count_logical,
        "physical_cores": cpu_count_physical,
        "usage_percent": cpu_usage_pct,
    }

    # Memory
    if HAS_PSUTIL and psutil is not None:
        mem = psutil.virtual_memory()
        mem_info = {
            "total_bytes": mem.total,
            "total_formatted": format_bytes(mem.total),
            "used_bytes": mem.used,
            "used_formatted": format_bytes(mem.used),
            "free_bytes": mem.available,
            "free_formatted": format_bytes(mem.available),
            "usage_percent": mem.percent,
        }
    else:
        mem_info = {
            "total_bytes": 0,
            "total_formatted": "N/A (psutil missing)",
            "used_bytes": 0,
            "used_formatted": "N/A",
            "free_bytes": 0,
            "free_formatted": "N/A",
            "usage_percent": 0.0,
        }

    # Disk
    root_path = "C:\\" if os.name == "nt" else "/"
    total_disk, used_disk, free_disk = shutil.disk_usage(root_path)
    disk_pct = round((used_disk / total_disk) * 100, 2) if total_disk > 0 else 0.0

    disk_info = {
        "total_bytes": total_disk,
        "total_formatted": format_bytes(total_disk),
        "used_bytes": used_disk,
        "used_formatted": format_bytes(used_disk),
        "free_bytes": free_disk,
        "free_formatted": format_bytes(free_disk),
        "usage_percent": disk_pct,
    }

    # Active Processes
    processes: List[Dict[str, Any]] = []
    if HAS_PSUTIL and psutil is not None:
        try:
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get("cpu_percent") or 0.0,
                reverse=True,
            )
            for proc in procs[:top_n_processes]:
                processes.append(
                    {
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "cpu_percent": round(proc.info.get("cpu_percent") or 0.0, 1),
                        "memory_percent": round(
                            proc.info.get("memory_percent") or 0.0, 1
                        ),
                    }
                )
        except Exception:  # nosec B110
            pass

    return {
        "system": sys_info,
        "cpu": cpu_info,
        "memory": mem_info,
        "disk": disk_info,
        "top_processes": processes,
    }


def render_dashboard(data: Dict[str, Any]) -> str:
    """Render system info dictionary into ASCII dashboard string.

    Args:
        data: System details dictionary.

    Returns:
        Formatted ASCII string representation.
    """
    sys_data = data["system"]
    cpu_data = data["cpu"]
    mem_data = data["memory"]
    disk_data = data["disk"]

    lines = []
    lines.append("=" * 65)
    lines.append("              SYSTEM INFORMATION DASHBOARD              ")
    lines.append("=" * 65)

    # OS Info
    lines.append(f" Hostname      : {sys_data['hostname']}")
    os_str = (
        f"{sys_data['os_name']} {sys_data['os_release']}"
        f" ({sys_data['architecture']})"
    )
    lines.append(f" OS            : {os_str}")
    lines.append(f" Python        : {sys_data['python_version']}")
    lines.append(f" Uptime        : {sys_data['uptime_formatted']}")
    lines.append("-" * 65)

    # CPU Info
    c_pct = cpu_data["usage_percent"]
    c_hash = "#" * int(c_pct // 5)
    cpu_bar = f"[{c_hash:<20}] {c_pct}%"
    cores_str = (
        f"{cpu_data['physical_cores']} Physical / {cpu_data['logical_cores']}"
        " Logical"
    )
    lines.append(f" CPU Cores     : {cores_str}")
    lines.append(f" CPU Load      : {cpu_bar}")
    lines.append("-" * 65)

    # Memory Info
    m_pct = mem_data["usage_percent"]
    m_hash = "#" * int(m_pct // 5)
    mem_bar = f"[{m_hash:<20}] {m_pct}%"
    lines.append(f" Memory Total  : {mem_data['total_formatted']}")
    lines.append(f" Memory Used   : {mem_data['used_formatted']} {mem_bar}")
    lines.append(f" Memory Free   : {mem_data['free_formatted']}")
    lines.append("-" * 65)

    # Disk Info
    d_pct = disk_data["usage_percent"]
    d_hash = "#" * int(d_pct // 5)
    disk_bar = f"[{d_hash:<20}] {d_pct}%"
    lines.append(f" Disk Total    : {disk_data['total_formatted']}")
    lines.append(f" Disk Used     : {disk_data['used_formatted']} {disk_bar}")
    lines.append(f" Disk Free     : {disk_data['free_formatted']}")

    # Top processes
    if data["top_processes"]:
        lines.append("-" * 65)
        lines.append(f" TOP {len(data['top_processes'])} PROCESSES:")
        lines.append(f"  {'PID':<8} {'NAME':<30} {'CPU %':<8} {'MEM %':<8}")
        for p in data["top_processes"]:
            p_name = p["name"][:28]
            lines.append(
                f"  {p['pid']:<8} {p_name:<30} {p['cpu_percent']:<8}"
                f" {p['memory_percent']:<8}"
            )

    lines.append("=" * 65)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        description="Display system information dashboard."
    )
    parser.add_argument(
        "--json", action="store_true", help="Output information in JSON format"
    )
    parser.add_argument(
        "--top-processes",
        type=int,
        default=5,
        help="Number of top processes to show",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for system info display."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    info = get_system_info(top_n_processes=parsed.top_processes)

    if parsed.json:
        print(json.dumps(info, indent=2))
    else:
        print(render_dashboard(info))

    return 0


if __name__ == "__main__":
    sys.exit(main())
