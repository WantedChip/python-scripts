#!/usr/bin/env python3
"""Port Conflict Doctor.

Diagnoses "address already in use" errors by identifying the process, parent,
working directory, and container mapping, and recommends the safest cleanup commands.
"""

import argparse
import subprocess  # nosec B404
import sys
from typing import List

# Optional psutil
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def check_docker_containers(port: int) -> List[str]:
    """Check if Docker containers are mapping the target conflict port."""
    containers = []
    try:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.ID}}|{{.Names}}|{{.Ports}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        if res.returncode == 0:
            for line in res.stdout.split("\n"):
                if f":{port}->" in line or f"0.0.0.0:{port}" in line:
                    containers.append(line.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return containers


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def diagnose_port(port: int) -> None:
    """Scan and print detailed process metrics for a specific conflict port."""
    print("========================================================================")
    print(f"DIAGNOSING PORT CONFLICT: {port}")
    print("========================================================================")

    docker_mappings = check_docker_containers(port)
    if docker_mappings:
        print("[!] PORT CONFLICT DETECTED IN DOCKER CONTAINER:")
        for dm in docker_mappings:
            cid, name, ports = dm.split("|")
            print(f"  Container ID:   {cid}")
            print(f"  Container Name: {name}")
            print(f"  Port Mapping:   {ports}")
            print("  Safe Fix:")
            print(f"    $ docker stop {cid}")
        print("-" * 80)

    proc_found = False
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                proc_found = True
                pid = conn.pid
                if not pid:
                    msg = (
                        "  [-] Port is listening but process ID could not be "
                        "resolved (admin permissions needed)."
                    )
                    print(msg)
                    continue

                try:
                    proc = psutil.Process(pid)
                    parent = proc.parent()
                    parent_name = parent.name() if parent else "N/A"
                    parent_pid = parent.pid if parent else "N/A"

                    print(f"[!] LOCAL PROCESS DETECTED (PID {pid}):")
                    print(f"  Process Name:     {proc.name()}")
                    print(f"  Working Dir:      {proc.cwd()}")
                    print(f"  Launch Command:   {' '.join(proc.cmdline())}")
                    print(f"  Parent Process:   {parent_name} (PID {parent_pid})")

                    print("\n  Safest way to stop this service:")
                    if sys.platform == "win32":
                        print(f"    Run: taskkill /F /PID {pid}")
                    else:
                        print(f"    Run: kill -9 {pid}")
                except (OSError, psutil.Error) as pe:
                    print(f"  [-] Failed to read process {pid} details: {pe}")
    except (OSError, psutil.Error) as e:
        print(f"[-] Net connection query error: {e}", file=sys.stderr)

    if not proc_found and not docker_mappings:
        print(f"[+] Port {port} appears to be free and available for use.")
    print("========================================================================")


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose 'address already in use' port conflict owners and "
            "recommend safe stops."
        )
    )
    parser.add_argument(
        "port", type=int, nargs="?", help="Target port number to audit (e.g. 8080)."
    )

    args = parser.parse_args()

    if not HAS_PSUTIL:
        print(
            "Error: The 'psutil' package is required to trace active processes.",
            file=sys.stderr,
        )
        print("Please run: pip install psutil", file=sys.stderr)
        sys.exit(1)

    port = args.port
    if port is None:
        active_ports = []
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.status == "LISTEN" and conn.laddr:
                    active_ports.append(conn.laddr.port)
        except (OSError, psutil.Error):
            pass

        active_ports = sorted(list(set(active_ports)))
        if not active_ports:
            print("[+] No active listening ports discovered on localhost.")
            sys.exit(0)

        print("Active listening ports discovered:")
        for p in active_ports:
            print(f"  - {p}")
        print("-" * 80)
        try:
            choice_str = input("Enter port number to diagnose: ").strip()
            port = int(choice_str)
        except (ValueError, KeyboardInterrupt):
            print("\nOperation aborted.")
            sys.exit(0)

    diagnose_port(port)


if __name__ == "__main__":
    main()
