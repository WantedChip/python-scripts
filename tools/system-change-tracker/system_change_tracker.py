#!/usr/bin/env python3
"""What Changed My System? Tracker.

Snapshots and diffs directory files, Python environment packages, OS-level
programs, environment variables, and active services before and after installations.
"""

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any

# Try importing winreg on Windows
try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


def calculate_file_hash(file_path: Path) -> str:
    """Compute the SHA-256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        The hex digest of the file hash.
    """
    sha = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        return "error_reading_file"


def snapshot_files(paths: list[str]) -> dict[str, dict[str, Any]]:
    """Capture snapshot of sizes, mtimes, and hashes for specified directories/files.

    Args:
        paths: List of file and directory paths.

    Returns:
        A dictionary mapping file paths to their metadata.
    """
    metadata: dict[str, dict[str, Any]] = {}
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue

        if path.is_file():
            try:
                stat = path.stat()
                metadata[path.as_posix()] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "sha256": calculate_file_hash(path),
                }
            except OSError:
                continue
        elif path.is_dir():
            # Recursively walk directories
            for root, _, files in os.walk(path):
                for f in files:
                    f_path = Path(root) / f
                    try:
                        stat = f_path.stat()
                        metadata[f_path.as_posix()] = {
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "sha256": calculate_file_hash(f_path),
                        }
                    except OSError:
                        continue
    return metadata


def get_python_packages() -> dict[str, str]:
    """Retrieve installed Python packages and versions in active environment.

    Returns:
        A dictionary mapping package name to version.
    """
    packages: dict[str, str] = {}
    try:
        for dist in importlib.metadata.distributions():
            name = dist.metadata.get("Name")
            version = dist.version
            if name:
                packages[name.lower()] = version
    except Exception:  # pylint: disable=broad-exception-caught # nosec B110
        pass
    return packages


def get_windows_programs() -> dict[str, str]:
    """Read Windows Registry to get installed programs and versions.

    Returns:
        A dictionary mapping program name to version.
    """
    programs: dict[str, str] = {}
    if not HAS_WINREG:
        return programs

    keys = [
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    ]

    for hkey, subkey in keys:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as sub:
                            try:
                                disp_name, _ = winreg.QueryValueEx(sub, "DisplayName")
                                try:
                                    disp_ver, _ = winreg.QueryValueEx(
                                        sub, "DisplayVersion"
                                    )
                                except FileNotFoundError:
                                    disp_ver = "unknown"
                                if disp_name:
                                    programs[str(disp_name).strip()] = str(
                                        disp_ver
                                    ).strip()
                            except FileNotFoundError:
                                continue
                    except OSError:
                        continue
        except OSError:
            continue
    return programs


def get_linux_packages() -> dict[str, str]:
    """Run dpkg-query to fetch active package versions on Linux systems.

    Returns:
        A dictionary mapping package names to versions.
    """
    programs: dict[str, str] = {}
    try:
        import subprocess  # pylint: disable=import-outside-toplevel # nosec B404

        # Run dpkg-query safely with shell=False
        res = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package} ${Version}\\n"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603 B607
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                programs[parts[0]] = parts[1]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return programs


def get_system_packages() -> dict[str, str]:
    """Collect OS-level package inventory.

    Returns:
        Dictionary of programs and versions.
    """
    if sys.platform == "win32":
        return get_windows_programs()
    if sys.platform.startswith("linux"):
        return get_linux_packages()
    return {}


def get_windows_services() -> dict[str, str]:
    """Audit Windows Service statuses using sc.exe.

    Returns:
        A dictionary of service names and states.
    """
    services: dict[str, str] = {}
    try:
        import subprocess  # pylint: disable=import-outside-toplevel # nosec B404

        res = subprocess.run(
            ["sc", "query", "type=", "service", "state=", "all"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603 B607

        current_service = ""
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                current_service = line.split(":", 1)[1].strip()
            elif line.startswith("STATE") and current_service:
                # STATE              : 4  RUNNING
                parts = line.split(":", 1)[1].strip().split()
                if len(parts) >= 2:
                    status = parts[1]
                    services[current_service] = status
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return services


def get_linux_services() -> dict[str, str]:
    """Query Linux systemd service states.

    Returns:
        A dictionary of service names and status.
    """
    services: dict[str, str] = {}
    try:
        import subprocess  # pylint: disable=import-outside-toplevel # nosec B404

        res = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603 B607
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4:
                # systemctl outputs: UNIT LOAD ACTIVE SUB DESCRIPTION
                # e.g. ssh.service loaded active running OpenBSD Secure Shell server
                name = parts[0].replace(".service", "")
                status = parts[3]
                services[name] = status
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return services


def get_system_services() -> dict[str, str]:
    """Get active system services.

    Returns:
        A dictionary mapping service name to status.
    """
    if sys.platform == "win32":
        return get_windows_services()
    if sys.platform.startswith("linux"):
        return get_linux_services()
    return {}


def create_system_snapshot(paths: list[str]) -> dict[str, Any]:
    """Generate a full system snapshot.

    Args:
        paths: List of directories/files to scan.

    Returns:
        The snapshot dictionary structure.
    """
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "files": snapshot_files(paths),
        "env": dict(os.environ),
        "python_packages": get_python_packages(),
        "system_packages": get_system_packages(),
        "services": get_system_services(),
    }


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshots and return the structured difference dictionary.

    Args:
        before: The base snapshot.
        after: The comparison snapshot.

    Returns:
        A dictionary containing categorised differences.
    """
    diff_report: dict[str, Any] = {
        "files": {"added": [], "deleted": [], "modified": []},
        "env": {"added": {}, "deleted": {}, "modified": {}},
        "python_packages": {"added": {}, "deleted": {}, "modified": {}},
        "system_packages": {"added": {}, "deleted": {}, "modified": {}},
        "services": {"added": {}, "deleted": {}, "modified": {}},
    }

    # Helper function to compare dictionaries
    def compare_dicts(
        before_dict: dict[str, Any], after_dict: dict[str, Any], category: str
    ) -> None:
        b_keys = set(before_dict.keys())
        a_keys = set(after_dict.keys())

        # Added
        for k in a_keys - b_keys:
            diff_report[category]["added"][k] = after_dict[k]
        # Deleted
        for k in b_keys - a_keys:
            diff_report[category]["deleted"][k] = before_dict[k]
        # Modified
        for k in b_keys & a_keys:
            if before_dict[k] != after_dict[k]:
                diff_report[category]["modified"][k] = {
                    "before": before_dict[k],
                    "after": after_dict[k],
                }

    # Initialize sub-structures as dictionaries for comparing
    diff_report["env"] = {"added": {}, "deleted": {}, "modified": {}}
    diff_report["python_packages"] = {"added": {}, "deleted": {}, "modified": {}}
    diff_report["system_packages"] = {"added": {}, "deleted": {}, "modified": {}}
    diff_report["services"] = {"added": {}, "deleted": {}, "modified": {}}

    compare_dicts(before.get("env", {}), after.get("env", {}), "env")
    compare_dicts(
        before.get("python_packages", {}),
        after.get("python_packages", {}),
        "python_packages",
    )
    compare_dicts(
        before.get("system_packages", {}),
        after.get("system_packages", {}),
        "system_packages",
    )
    compare_dicts(before.get("services", {}), after.get("services", {}), "services")

    # Files compare (special lists formatting)
    b_files = before.get("files", {})
    a_files = after.get("files", {})
    b_f_keys = set(b_files.keys())
    a_f_keys = set(a_files.keys())

    for f in a_f_keys - b_f_keys:
        diff_report["files"]["added"].append(f)
    for f in b_f_keys - a_f_keys:
        diff_report["files"]["deleted"].append(f)
    for f in b_f_keys & a_f_keys:
        # Check size or SHA-256 modifications
        if (
            b_files[f]["sha256"] != a_files[f]["sha256"]
            or b_files[f]["size"] != a_files[f]["size"]
        ):
            diff_report["files"]["modified"].append(
                {
                    "path": f,
                    "before": {
                        "size": b_files[f]["size"],
                        "sha256": b_files[f]["sha256"],
                    },
                    "after": {
                        "size": a_files[f]["size"],
                        "sha256": a_files[f]["sha256"],
                    },
                }
            )

    return diff_report


def print_diff_dashboard(diff: dict[str, Any]) -> None:
    # pylint: disable=too-many-branches
    """Format and print a user-friendly terminal comparison dashboard.

    Args:
        diff: The difference report.
    """
    print("\n" + "=" * 60)
    print("🖥️  SYSTEM CHANGELOG REPORT")
    print("=" * 60)

    # 1. Files
    files = diff["files"]
    if files["added"] or files["deleted"] or files["modified"]:
        print("\n📁 FILE SYSTEM CHANGES:")
        for f in files["added"]:
            print(f"  [+] {f} (Added)")
        for f in files["deleted"]:
            print(f"  [-] {f} (Removed)")
        for f in files["modified"]:
            print(
                f"  [*] {f['path']} (Modified: "
                f"{f['before']['size']}B -> {f['after']['size']}B)"
            )
    else:
        print("\n📁 File System: No changes detected.")

    # 2. Env Vars
    env = diff["env"]
    if env["added"] or env["deleted"] or env["modified"]:
        print("\n🔌 ENVIRONMENT VARIABLES CHANGES:")
        for k, v in env["added"].items():
            print(f"  [+] {k} = {v}")
        for k in env["deleted"]:
            print(f"  [-] {k}")
        for k, v in env["modified"].items():
            print(f"  [*] {k} changed: '{v['before']}' -> '{v['after']}'")
    else:
        print("\n🔌 Environment Variables: No changes detected.")

    # 3. Python Packages
    py_pkg = diff["python_packages"]
    if py_pkg["added"] or py_pkg["deleted"] or py_pkg["modified"]:
        print("\n🐍 PYTHON PACKAGE CHANGES:")
        for k, v in py_pkg["added"].items():
            print(f"  [+] {k} (v{v})")
        for k in py_pkg["deleted"]:
            print(f"  [-] {k}")
        for k, v in py_pkg["modified"].items():
            print(f"  [*] {k} upgraded/downgraded: v{v['before']} -> v{v['after']}")
    else:
        print("\n🐍 Python Packages: No changes detected.")

    # 4. OS Programs
    sys_pkg = diff["system_packages"]
    if sys_pkg["added"] or sys_pkg["deleted"] or sys_pkg["modified"]:
        print("\n💻 OS LEVEL PACKAGES / PROGRAMS CHANGES:")
        for k, v in sys_pkg["added"].items():
            print(f"  [+] {k} (v{v})")
        for k in sys_pkg["deleted"]:
            print(f"  [-] {k}")
        for k, v in sys_pkg["modified"].items():
            print(f"  [*] {k} version changed: v{v['before']} -> v{v['after']}")
    else:
        print("\n💻 OS Packages: No changes detected.")

    # 5. Services
    services = diff["services"]
    if services["added"] or services["deleted"] or services["modified"]:
        print("\n⚙️  SYSTEM SERVICES STATUS CHANGES:")
        for k, v in services["added"].items():
            print(f"  [+] {k} (New Service, State: {v})")
        for k in services["deleted"]:
            print(f"  [-] {k} (Service Removed)")
        for k, v in services["modified"].items():
            print(f"  [*] {k} state transitioned: {v['before']} -> {v['after']}")
    else:
        print("\n⚙️  System Services: No changes detected.")
    print("=" * 60)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="What Changed My System? Tracker utility."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Snapshot sub-command
    snap_parser = subparsers.add_parser(
        "snapshot", help="Create a current snapshot of the system state."
    )
    snap_parser.add_argument(
        "-o", "--output", required=True, help="JSON file path to save the snapshot."
    )
    snap_parser.add_argument(
        "-d",
        "--dir",
        action="append",
        default=[],
        help="Directories or files to audit recursively for metadata snapshot.",
    )

    # Diff sub-command
    diff_parser = subparsers.add_parser(
        "diff", help="Compare two snapshot files and display system changelog."
    )
    diff_parser.add_argument(
        "before", help="Snapshot file captured before installation."
    )
    diff_parser.add_argument("after", help="Snapshot file captured after installation.")
    diff_parser.add_argument(
        "-o",
        "--output",
        help="Optional JSON file path to write structural differences report.",
    )

    args = parser.parse_args()

    if args.command == "snapshot":
        print("Gathering system inventory. This may take a moment...")
        snapshot = create_system_snapshot(args.dir)
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            print(f"✅ System snapshot successfully written to: {args.output}")
        except OSError as err:
            print(f"Error saving system snapshot: {err}")
            sys.exit(1)

    elif args.command == "diff":
        before_path = Path(args.before)
        after_path = Path(args.after)

        if not before_path.exists():
            print(f"Error: Base snapshot file '{args.before}' does not exist.")
            sys.exit(1)
        if not after_path.exists():
            print(f"Error: Target snapshot file '{args.after}' does not exist.")
            sys.exit(1)

        try:
            with before_path.open("r", encoding="utf-8") as f:
                before = json.load(f)
            with after_path.open("r", encoding="utf-8") as f:
                after = json.load(f)
        except (OSError, json.JSONDecodeError) as err:
            print(f"Error loading snapshot files: {err}")
            sys.exit(1)

        diff = diff_snapshots(before, after)
        print_diff_dashboard(diff)

        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(diff, f, indent=2)
                print(f"✅ Structural differences report written to: {args.output}")
            except OSError as err:
                print(f"Error writing difference report: {err}")
                sys.exit(1)


if __name__ == "__main__":
    main()
