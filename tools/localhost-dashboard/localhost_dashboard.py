#!/usr/bin/env python3
"""Localhost Dashboard.

Scans active localhost TCP listeners, determines the owner processes, guesses
their dev frameworks, runs HTTP health checks, and lists them in a dashboard.
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Tuple

# Optional psutil
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def check_port_health(port: int) -> Tuple[str, float]:
    """Perform a quick HTTP GET probe on localhost:port."""
    url = f"http://localhost:{port}/"
    start = time.perf_counter()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "LocalhostDashboard/1.0"}
        )
        with urllib.request.urlopen(req, timeout=0.5) as response:  # nosec B310
            latency = (time.perf_counter() - start) * 1000.0
            return f"{response.status} {response.reason}", latency
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - start) * 1000.0
        return f"{e.code} {e.reason}", latency
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "timed out" in reason:
            return "Timeout", 500.0
        return "Unresponsive", 0.0
    except (OSError, ValueError) as e:
        return f"Error: {str(e)[:15]}", 0.0


# pylint: disable=too-many-return-statements
def guess_framework(cwd: str) -> str:
    """Guess dev framework type by checking configuration files in CWD."""
    if not cwd or cwd == "N/A" or not os.path.exists(cwd):
        return "Generic Process"

    try:
        files = os.listdir(cwd)
    except OSError:
        return "Generic Process"

    indicators = {
        "package.json": "Node.js (npm)",
        "pyproject.toml": "Python (poetry/pip)",
        "requirements.txt": "Python (pip)",
        "go.mod": "Go Server",
        "Cargo.toml": "Rust Server",
        "Gemfile": "Ruby/Rails",
        "composer.json": "PHP/Composer",
        "build.gradle": "Java/Gradle",
        "pom.xml": "Java/Maven",
    }

    for name, desc in indicators.items():
        if name in files:
            return desc

    package_json_path = os.path.join(cwd, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "next" in content:
                    return "Next.js"
                if "react" in content:
                    return "React/Vite"
                if "vue" in content:
                    return "Vue.js"
                if "express" in content:
                    return "Express.js"
        except (OSError, ValueError):
            pass

    return "Generic Dev Server"


def get_dev_servers() -> List[Dict[str, Any]]:
    """Scan listening ports and processes to build dev server statistics."""
    servers: List[Dict[str, Any]] = []
    if not HAS_PSUTIL:
        return servers

    try:
        connections = psutil.net_connections(kind="tcp")
    except (OSError, psutil.Error) as e:
        print(f"Error querying net connections: {e}", file=sys.stderr)
        return servers

    seen_ports = set()

    for conn in connections:
        if conn.status != "LISTEN" or not conn.laddr:
            continue

        port = conn.laddr.port
        if port in seen_ports:
            continue
        seen_ports.add(port)

        pid = conn.pid
        if not pid:
            continue

        try:
            proc = psutil.Process(pid)
            name = proc.name()
            cwd = proc.cwd()
            start_time = proc.create_time()
            uptime_sec = time.time() - start_time
            framework = guess_framework(cwd)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            name = "Access Denied"
            cwd = "N/A"
            uptime_sec = 0.0
            framework = "Unknown"

        status, latency = check_port_health(port)

        servers.append(
            {
                "port": port,
                "pid": pid,
                "name": name,
                "cwd": cwd,
                "framework": framework,
                "uptime_sec": uptime_sec,
                "status": status,
                "latency": latency,
            }
        )

    servers.sort(key=lambda x: x["port"])
    return servers


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Scans and monitors local development servers."
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="Run in continuous watch dashboard mode (refreshes every 3 seconds).",
    )

    args = parser.parse_args()

    if not HAS_PSUTIL:
        print(
            "Error: Required library 'psutil' is not installed.\n"
            "Please install it: pip install psutil",
            file=sys.stderr,
        )
        sys.exit(1)

    while True:
        servers = get_dev_servers()

        if args.watch:
            print("\033[H\033[J", end="")

        now_str = datetime.now().strftime("%H:%M:%S")
        print(
            "========================================================================"
        )
        print(f"LOCALHOST DASHBOARD — ACTIVE DEVELOPMENT SERVERS ({now_str})")
        print(
            "========================================================================"
        )

        if not servers:
            print("\n[-] No local development servers detected listening on TCP ports.")
        else:
            header_str = (
                f"{'PORT':<6} | {'PROJECT TYPE':<22} | {'PROCESS (PID)':<20} | "
                f"{'UPTIME':<10} | {'HEALTH STATUS'}"
            )
            print(header_str)
            print("-" * 80)

            for s in servers:
                up = s["uptime_sec"]
                if up >= 3600:
                    up_str = f"{up / 3600.0:.1f}h"
                elif up >= 60:
                    up_str = f"{up / 60.0:.1f}m"
                else:
                    up_str = f"{int(up)}s"

                latency_str = f" ({s['latency']:.1f}ms)" if s["latency"] > 0 else ""
                health_str = f"{s['status']}{latency_str}"

                proc_str = f"{s['name']} ({s['pid']})"
                if len(proc_str) > 18:
                    proc_str = proc_str[:15] + "..."

                row_str = (
                    f"{s['port']:<6} | {s['framework']:<22} | {proc_str:<20} | "
                    f"{up_str:<10} | {health_str}"
                )
                print(row_str)

        print("=" * 80)

        if not args.watch:
            break

        try:
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nExiting dashboard.")
            break


if __name__ == "__main__":
    main()
