"""Service Status Checker.

Checks whether a list of systemd services or processes are running
and optionally restarts stopped ones.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import json
import shutil
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def check_systemd_service(service_name: str) -> bool:
    """Check if a systemd service is active/running via systemctl.

    Args:
        service_name: Name of the service (e.g., 'nginx', 'ssh').

    Returns:
        True if active/running, False otherwise.
    """
    if not shutil.which("systemctl"):
        return False

    try:
        res = subprocess.run(  # nosec B603 B607
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return res.stdout.strip() == "active"
    except (subprocess.SubprocessError, OSError):
        return False


def restart_systemd_service(service_name: str) -> bool:
    """Attempt to restart a systemd service via systemctl restart.

    Args:
        service_name: Name of the service to restart.

    Returns:
        True if command succeeded (exit code 0), False otherwise.
    """
    if not shutil.which("systemctl"):
        return False

    try:
        res = subprocess.run(  # nosec B603 B607
            ["systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def check_process_running(process_name: str) -> Tuple[bool, List[int]]:
    """Check if any process matching process_name is currently running.

    Args:
        process_name: Substring or exact name of the process executable.

    Returns:
        Tuple of (is_running, list_of_pids).
    """
    pids = []
    if HAS_PSUTIL:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = proc.info.get("name") or ""
                cmd = " ".join(proc.info.get("cmdline") or [])
                target = process_name.lower()
                if target in name.lower() or target in cmd.lower():
                    pids.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return len(pids) > 0, pids


def inspect_service(service_name: str, check_systemd: bool = True) -> Dict[str, Any]:
    """Inspect status of a single service or process.

    Args:
        service_name: Name of service or process.
        check_systemd: If True and systemctl is available, check systemd first.

    Returns:
        Status dictionary with fields: name, status, pids, systemd_active.
    """
    systemd_available = bool(shutil.which("systemctl"))
    is_active = False
    pids: List[int] = []

    if check_systemd and systemd_available:
        is_active = check_systemd_service(service_name)

    if not is_active:
        is_running, pids = check_process_running(service_name)
        is_active = is_running

    return {
        "service": service_name,
        "status": "RUNNING" if is_active else "STOPPED",
        "systemd_checked": systemd_available and check_systemd,
        "pids": pids,
    }


def process_services(services: List[str], auto_restart: bool = False) -> Dict[str, Any]:
    """Inspect a list of services and optionally restart stopped services.

    Args:
        services: List of service or process names.
        auto_restart: Whether to attempt restarting stopped services.

    Returns:
        Report payload with overall health status and service results.
    """
    results = []
    stopped_count = 0
    restarted_count = 0

    for svc in services:
        info = inspect_service(svc)
        if info["status"] == "STOPPED":
            stopped_count += 1
            if auto_restart:
                restarted = restart_systemd_service(svc)
                info["restarted"] = restarted
                if restarted:
                    restarted_count += 1
                    # Re-check status
                    info["status"] = "RESTARTED"
                else:
                    info["restart_failed"] = True
        results.append(info)

    if stopped_count in (0, restarted_count):
        overall_status = "HEALTHY"
    elif restarted_count > 0:
        overall_status = "DEGRADED"
    else:
        overall_status = "UNHEALTHY"

    return {
        "overall_status": overall_status,
        "total_services": len(services),
        "running_count": len(services) - stopped_count,
        "stopped_count": stopped_count,
        "restarted_count": restarted_count,
        "services": results,
    }


def print_health_report(report: Dict[str, Any]) -> None:
    """Print health status report table to stdout.

    Args:
        report: Report data dictionary.
    """
    print("\n" + "=" * 60)
    print(f"      SERVICE HEALTH REPORT - OVERALL: {report['overall_status']}")
    print("=" * 60)
    summary_str = (
        f" Total: {report['total_services']} | "
        f"Running: {report['running_count']} | "
        f"Stopped: {report['stopped_count']} | "
        f"Restarted: {report['restarted_count']}"
    )
    print(summary_str)
    print("-" * 60)
    print(f" {'SERVICE NAME':<20} | {'STATUS':<12} | DETAILS")
    print("-" * 60)
    for svc in report["services"]:
        pids_str = f"PIDs: {svc['pids']}" if svc["pids"] else ""
        if svc.get("restarted"):
            restart_str = " (Restart Attempted)"
        elif svc.get("restart_failed"):
            restart_str = " (Restart Failed)"
        else:
            restart_str = ""
        details = f"{pids_str}{restart_str}".strip()
        print(f" {svc['service']:<20} | {svc['status']:<12} | {details}")
    print("=" * 60 + "\n")


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Check status of services/processes and optionally restart stopped ones."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "services",
        nargs="+",
        help="Names of services or processes to check (e.g. nginx mysqld sshd)",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Auto-restart stopped systemd services",
    )
    parser.add_argument(
        "-o",
        "--output-json",
        type=str,
        help="Export health report to JSON file",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Service Status Checker."""
    parsed = parse_args(args)

    report = process_services(parsed.services, auto_restart=parsed.restart)
    print_health_report(report)

    if parsed.output_json:
        with open(parsed.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Health report exported to '{parsed.output_json}'.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
