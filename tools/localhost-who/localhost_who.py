#!/usr/bin/env python3
"""Localhost Who.

Scans listening TCP ports to identify active development services, exposing
project names, PIDs, start times, working directories, launch commands, and
health states.
"""

import argparse
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime

# Optional psutil
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def check_port_health(port: int) -> str:
    """Send a fast HTTP request to probe the port's health status."""
    url = f"http://127.0.0.1:{port}/"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=0.2) as response:  # nosec B310
            return f"Healthy ({response.status})"
    except urllib.error.HTTPError as e:
        return f"Responsive ({e.code})"
    except (OSError, ValueError, urllib.error.URLError):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return "TCP Open (No HTTP)"
        except OSError:
            return "Unreachable"


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "List all active localhost development services and their "
            "process metadata."
        )
    )
    parser.parse_args()

    print("========================================================================")
    print("LOCALHOST WHO: RUNNING SERVICES DISCOVERER")
    print("========================================================================")

    if not HAS_PSUTIL:
        print(
            "Error: The 'psutil' package is required to trace running processes.",
            file=sys.stderr,
        )
        print("Please run: pip install psutil", file=sys.stderr)
        sys.exit(1)

    print("Scanning active TCP listening sockets...")
    print("-" * 80)

    listeners = []
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "LISTEN" and conn.laddr:
                port = conn.laddr.port
                if 3000 <= port <= 9999 or port in (80, 443, 8080, 8443):
                    listeners.append((port, conn.pid))
    except (OSError, psutil.Error) as e:
        print(f"[-] Failed to read net connections: {e}", file=sys.stderr)
        sys.exit(1)

    if not listeners:
        print("\n[+] No dev servers or active listening ports detected on localhost.")
        sys.exit(0)

    listeners = sorted(list(set(listeners)), key=lambda x: x[0])

    header_str = (
        f"{'PORT':<6} | {'PROJECT/PROC':<20} | {'UPTIME':<10} | "
        f"{'HEALTH':<20} | {'LAUNCH COMMAND'}"
    )
    print(header_str)
    print("-" * 80)

    for port, pid in listeners:
        proj_name = "Unknown"
        uptime_str = "N/A"
        cmd_str = "N/A"

        if pid:
            try:
                proc = psutil.Process(pid)
                created = proc.create_time()
                diff_seconds = datetime.now().timestamp() - created
                if diff_seconds < 60:
                    uptime_str = f"{int(diff_seconds)}s"
                elif diff_seconds < 3600:
                    uptime_str = f"{int(diff_seconds // 60)}m"
                else:
                    uptime_str = f"{int(diff_seconds // 3600)}h"

                cmd = proc.cmdline()
                if cmd:
                    cmd_str = " ".join(cmd)

                cwd = proc.cwd()
                if cwd:
                    proj_name = f"{os.path.basename(cwd)} ({proc.name()})"
                else:
                    proj_name = proc.name()
            except (OSError, psutil.Error):
                proj_name = f"PID {pid}"

        health = check_port_health(port)

        if len(cmd_str) > 28:
            cmd_str = cmd_str[:25] + "..."

        row_str = (
            f"{port:<6} | {proj_name[:20]:<20} | {uptime_str:<10} | "
            f"{health:<20} | {cmd_str}"
        )
        print(row_str)
    print("=" * 80)


if __name__ == "__main__":
    main()
