#!/usr/bin/env python3
"""Setup Diff.

Compares development environment snapshots (OS, runtimes, PATH, environment keys,
pip packages, listening ports) between two machines to diagnose differences.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Optional

# Optional psutil
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def check_binary(name: str) -> Optional[str]:
    """Find absolute path of system binary if reachable in PATH."""
    return shutil.which(name)


def get_listening_ports() -> List[int]:
    """Retrieve currently active listening port numbers."""
    ports: List[int] = []
    if not HAS_PSUTIL:
        return ports
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "LISTEN" and conn.laddr:
                ports.append(conn.laddr.port)
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return list(set(ports))


def generate_snapshot() -> Dict[str, Any]:
    """Construct a JSON-serializable snapshot of the active system state."""
    # Check common dev binaries
    binaries = ["git", "node", "docker", "npm", "python", "pip"]
    bin_status = {b: check_binary(b) for b in binaries}

    # Fetch Python packages
    packages = {}
    try:
        res = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pip", "list", "--format=json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            for pkg in json.loads(res.stdout):
                packages[pkg["name"]] = pkg["version"]
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    path_entries = os.environ.get("PATH", "").split(os.pathsep)

    return {
        "os_platform": platform.platform(),
        "python_version": sys.version,
        "binaries": bin_status,
        "environment_keys": sorted(list(os.environ.keys())),
        "packages": packages,
        "path_entries": path_entries,
        "listening_ports": get_listening_ports(),
    }


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def compare_snapshots(p_a: Dict[str, Any], p_b: Dict[str, Any]) -> None:
    """Compare and report side-by-side mismatches between two snapshots."""
    print("========================================================================")
    print("SETUP COMPARISON REPORT")
    print("========================================================================")

    # 1. OS & Platform
    print("OS & PLATFORM:")
    if p_a["os_platform"] == p_b["os_platform"]:
        print(f"  [+] Matches: {p_a['os_platform']}")
    else:
        print("  [!] MISMATCH:")
        print(f"      Machine A: {p_a['os_platform']}")
        print(f"      Machine B: {p_b['os_platform']}")
    print("-" * 80)

    # 2. Python Runtimes
    print("PYTHON VERSION:")
    v_a = p_a["python_version"].split("\n")[0]
    v_b = p_b["python_version"].split("\n")[0]
    if v_a == v_b:
        print(f"  [+] Matches: {v_a}")
    else:
        print("  [!] MISMATCH:")
        print(f"      Machine A: {v_a}")
        print(f"      Machine B: {v_b}")
    print("-" * 80)

    # 3. Binaries
    print("SYSTEM BINARIES PATHS:")
    bin_mismatch = False
    for name in p_a["binaries"]:
        path_a = p_a["binaries"].get(name)
        path_b = p_b["binaries"].get(name)
        if path_a != path_b:
            bin_mismatch = True
            print(f"  [!] Binary '{name}':")
            print(f"      Machine A: {path_a or 'Not Found'}")
            print(f"      Machine B: {path_b or 'Not Found'}")
    if not bin_mismatch:
        print("  [+] All common dev binaries have matching PATH lookups.")
    print("-" * 80)

    # 4. Env Keys
    print("ENVIRONMENT VARIABLE KEYS:")
    keys_a = set(p_a["environment_keys"])
    keys_b = set(p_b["environment_keys"])
    missing_b = keys_a - keys_b
    missing_a = keys_b - keys_a
    if not missing_a and not missing_b:
        print("  [+] Environment keys match exactly.")
    else:
        if missing_b:
            msg_b = ", ".join(sorted(list(missing_b))[:5])
            print(f"  [!] Missing on Machine B: {msg_b}")
            if len(missing_b) > 5:
                print(f"      ... and {len(missing_b) - 5} more.")
        if missing_a:
            msg_a = ", ".join(sorted(list(missing_a))[:5])
            print(f"  [!] Missing on Machine A: {msg_a}")
            if len(missing_a) > 5:
                print(f"      ... and {len(missing_a) - 5} more.")
    print("-" * 80)

    # 5. Installed Packages
    print("PYTHON PACKAGES VERSION CONFLICTS:")
    pkgs_a = p_a["packages"]
    pkgs_b = p_b["packages"]
    all_pkgs = set(pkgs_a.keys()) | set(pkgs_b.keys())
    pkg_mismatches = []

    for pkg in all_pkgs:
        ver_a = pkgs_a.get(pkg)
        ver_b = pkgs_b.get(pkg)
        if ver_a != ver_b:
            pkg_mismatches.append((pkg, ver_a, ver_b))

    if not pkg_mismatches:
        print("  [+] Installed package configurations match.")
    else:
        print(f"  [!] Found {len(pkg_mismatches)} mismatched packages:")
        print(f"      {'PACKAGE NAME':<25} | {'MACHINE A':<15} | {'MACHINE B'}")
        print(f"      {'-'*25} | {'-'*15} | {'-'*15}")
        for name, va, vb in pkg_mismatches[:10]:
            print(f"      {name:<25} | {va or 'Missing':<15} | {vb or 'Missing'}")
        if len(pkg_mismatches) > 10:
            print(f"      ... and {len(pkg_mismatches) - 10} more conflicts.")
    print("========================================================================")


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose reproducibility issues by comparing development "
            "configurations of two machines."
        )
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute.")

    # Snapshot
    snap_parser = subparsers.add_parser(
        "snapshot", help="Create a local system snapshot file."
    )
    snap_parser.add_argument("output_file", help="Path to write the snapshot JSON.")

    # Compare
    comp_parser = subparsers.add_parser(
        "compare", help="Compare two machine snapshots."
    )
    comp_parser.add_argument("snapshot_a", help="First snapshot JSON file path.")
    comp_parser.add_argument("snapshot_b", help="Second snapshot JSON file path.")

    args = parser.parse_args()

    if args.command == "snapshot":
        snap = generate_snapshot()
        out_path = os.path.abspath(args.output_file)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(snap, f, indent=4)
            print(f"[+] Saved system configuration snapshot to: {out_path}")
        except OSError as e:
            print(f"[-] Error writing snapshot: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "compare":
        path_a = os.path.abspath(args.snapshot_a)
        path_b = os.path.abspath(args.snapshot_b)

        if not os.path.exists(path_a) or not os.path.exists(path_b):
            print("Error: One or both snapshot files not found.", file=sys.stderr)
            sys.exit(1)

        try:
            with open(path_a, "r", encoding="utf-8") as f:
                snap_a = json.load(f)
            with open(path_b, "r", encoding="utf-8") as f:
                snap_b = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error parsing snapshot JSON: {e}", file=sys.stderr)
            sys.exit(1)

        compare_snapshots(snap_a, snap_b)
    else:
        # Default snapshot to local file
        snap = generate_snapshot()
        print(json.dumps(snap, indent=4))


if __name__ == "__main__":
    main()
