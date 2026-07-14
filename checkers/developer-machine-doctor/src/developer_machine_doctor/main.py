"""Developer Machine Doctor — local system diagnostic check utility."""

import argparse
import ctypes
import json
import logging
import os
import platform
import shutil
import socket
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# psutil may not be installed in all lint environments
# pylint: disable=import-error
try:
    import psutil
except ImportError:
    psutil = None


def check_path_env() -> Dict[str, Any]:
    """Audit the system PATH environment variable.

    Returns:
        A dictionary containing warnings, duplicate entries, invalid directories,
        and count of paths.
    """
    path_sep = ";" if platform.system() == "Windows" else ":"
    raw_path = os.environ.get("PATH", "")
    paths = raw_path.split(path_sep)

    seen = set()
    duplicates = []
    invalid_dirs = []

    for p in paths:
        if not p.strip():
            continue
        cleaned_path = os.path.expandvars(p)
        if cleaned_path in seen:
            duplicates.append(cleaned_path)
        else:
            seen.add(cleaned_path)

        path_obj = Path(cleaned_path)
        if not path_obj.exists() or not path_obj.is_dir():
            invalid_dirs.append(cleaned_path)

    warnings: List[str] = []
    if duplicates:
        warnings.append(f"Found {len(duplicates)} duplicate PATH entries.")
    if invalid_dirs:
        warnings.append(f"Found {len(invalid_dirs)} non-existent directories in PATH.")

    return {
        "total_count": len(paths),
        "duplicates": duplicates,
        "invalid_dirs": invalid_dirs,
        "warnings": warnings,
    }


def get_program_version(binary_name: str, args: List[str]) -> Optional[str]:
    """Execute a binary with version arguments to parse its version string.

    Args:
        binary_name: The command or binary path to run.
        args: Arguments to retrieve the version (e.g. ['--version']).

    Returns:
        The version string or None if the binary could not be run.
    """
    binary_path = shutil.which(binary_name)
    if not binary_path:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [binary_path] + args,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if output:
            # Return the first non-empty line
            for line in output.splitlines():
                if line.strip():
                    return line.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return "Installed (Version unknown)"


def check_python_env() -> Dict[str, Any]:
    """Audit the active Python interpreter environment.

    Returns:
        A dictionary describing python interpreter details, virtualenv, and tools.
    """
    # Detect virtualenv status
    in_venv = False
    if sys.prefix != sys.base_prefix:
        in_venv = True
    elif "VIRTUAL_ENV" in os.environ:
        in_venv = True

    # Detect package managers and tools
    managers = ["pip", "uv", "poetry", "conda", "pipenv"]
    detected_managers = {}
    for manager in managers:
        ver = get_program_version(manager, ["--version"])
        if ver:
            detected_managers[manager] = ver

    return {
        "python_version": platform.python_version(),
        "interpreter": sys.executable,
        "in_virtualenv": in_venv,
        "virtualenv_path": os.environ.get("VIRTUAL_ENV", ""),
        "package_managers": detected_managers,
    }


def check_system_dependencies() -> Dict[str, Any]:
    """Check for standard developer command line dependencies.

    Returns:
        A dictionary containing present and missing dependencies.
    """
    deps = ["git", "curl", "docker", "node", "npm", "gcc", "make", "ssh"]
    present = {}
    missing = []

    for dep in deps:
        binary_path = shutil.which(dep)
        if binary_path:
            # Attempt to fetch version
            ver = get_program_version(dep, ["--version"] if dep != "make" else ["-v"])
            present[dep] = {
                "path": binary_path,
                "version": ver or "Unknown",
            }
        else:
            missing.append(dep)

    return {
        "present": present,
        "missing": missing,
    }


def check_port_conflicts(ports_to_check: List[int]) -> Dict[int, Any]:
    """Identify conflicts on standard development ports.

    Args:
        ports_to_check: List of integer ports to scan.

    Returns:
        A dictionary of conflicting ports with process information.
    """
    conflicts: Dict[int, Dict[str, Any]] = {}

    # Method 1: Check using sockets (always available)
    bound_ports = []
    for port in ports_to_check:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                # Attempt to bind, if it fails, the port is occupied
                s.bind(("127.0.0.1", port))
        except OSError:
            bound_ports.append(port)

    # Method 2: Map to process using psutil if available
    if psutil is not None and bound_ports:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if not conn.laddr or conn.laddr.port not in bound_ports:
                    continue
                port = conn.laddr.port
                pid = conn.pid
                if not pid:
                    continue
                try:
                    proc = psutil.Process(pid)
                    conflicts[port] = {
                        "pid": pid,
                        "name": proc.name(),
                        "command": " ".join(proc.cmdline()),
                        "username": proc.username(),
                        "status": conn.status,
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    conflicts[port] = {
                        "pid": pid,
                        "name": "Unknown (Access Denied)",
                        "command": "",
                        "username": "",
                        "status": conn.status,
                    }
        except (OSError, psutil.AccessDenied):
            # Fallback when net_connections requires admin access
            pass

    # Fill in any missing ports that were bound but not captured by psutil scan
    for port in bound_ports:
        if port not in conflicts:
            conflicts[port] = {
                "pid": -1,
                "name": "Occupied (Details unavailable)",
                "command": "",
                "username": "",
                "status": "LISTEN",
            }

    return conflicts


def check_disk_space() -> Dict[str, Any]:
    """Check storage disk utilization of current directory.

    Returns:
        A dictionary containing total, used, free space and usage percentage.
    """
    curr_path = Path.cwd()
    try:
        usage = shutil.disk_usage(curr_path)
        percent_used = (usage.used / usage.total) * 100
        return {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "usage_percent": round(percent_used, 2),
            "error": None,
        }
    except OSError as e:
        return {
            "total_gb": 0.0,
            "used_gb": 0.0,
            "free_gb": 0.0,
            "usage_percent": 0.0,
            "error": str(e),
        }


def check_permissions() -> Dict[str, Any]:
    """Determine administrative privileges and write permissions.

    Returns:
        A dictionary describing user privileges and write checks.
    """
    # pylint: disable=not-callable
    is_admin = False
    try:
        if platform.system() == "Windows":
            windll = getattr(ctypes, "windll", None)
            if windll is not None:
                is_admin = windll.shell32.IsUserAnAdmin() != 0
        else:
            getuid = getattr(os, "getuid", None)
            is_admin = getuid is not None and getuid() == 0
    except Exception:  # pylint: disable=broad-exception-caught
        is_admin = False

    # Check write access to temp and cwd
    temp_writable = False
    temp_dir = tempfile.gettempdir()
    temp_test_file = Path(temp_dir) / ".doctor_write_test"
    try:
        with open(temp_test_file, "w", encoding="utf-8") as f:
            f.write("test")
        temp_test_file.unlink()
        temp_writable = True
    except OSError:
        pass

    cwd_writable = False
    cwd_test_file = Path.cwd() / ".doctor_write_test"
    try:
        with open(cwd_test_file, "w", encoding="utf-8") as f:
            f.write("test")
        cwd_test_file.unlink()
        cwd_writable = True
    except OSError:
        pass

    return {
        "is_admin": is_admin,
        "temp_writable": temp_writable,
        "workspace_writable": cwd_writable,
    }


def _print_path_report(path_data: Dict[str, Any]) -> None:
    print("\n[1] PATH Environment Variable:")
    print(f"  - Total entries: {path_data['total_count']}")
    if path_data["duplicates"]:
        print("  - WARNING: Duplicate directories found:")
        for dup in path_data["duplicates"]:
            print(f"      * {dup}")
    if path_data["invalid_dirs"]:
        print("  - WARNING: Non-existent directories in PATH:")
        for inv in path_data["invalid_dirs"]:
            print(f"      * {inv}")
    if not path_data["duplicates"] and not path_data["invalid_dirs"]:
        print("  - Status: Healthy (No duplicates or missing directories)")


def _print_python_report(py_data: Dict[str, Any]) -> None:
    print("\n[2] Python Environment:")
    print(f"  - Active Version: {py_data['python_version']}")
    print(f"  - Interpreter Path: {py_data['interpreter']}")
    print(f"  - Virtualenv Active: {py_data['in_virtualenv']}")
    if py_data["in_virtualenv"]:
        print(f"    * Path: {py_data['virtualenv_path']}")
    print("  - Package Managers:")
    for manager, ver in py_data["package_managers"].items():
        print(f"    * {manager}: {ver}")


def _print_dep_report(dep_data: Dict[str, Any]) -> None:
    print("\n[3] System Dependencies:")
    print("  - Present:")
    for dep, info in dep_data["present"].items():
        print(f"    * {dep}: {info['version']} ({info['path']})")
    if dep_data["missing"]:
        print("  - Missing:")
        for dep in dep_data["missing"]:
            print(f"    * {dep} (Not found in PATH)")


def _print_port_report(port_data: Dict[int, Dict[str, Any]]) -> None:
    print("\n[4] Port Conflicts:")
    if not port_data:
        print("  - Status: Healthy (No common developer ports occupied)")
    else:
        for port, info in port_data.items():
            print(f"  - Port {port} is occupied:")
            if info["pid"] != -1:
                print(f"    * Process Name: {info['name']}")
                print(f"    * PID: {info['pid']}")
                print(f"    * Command: {info['command']}")
                print(f"    * Owner: {info['username']}")
            else:
                print(f"    * {info['name']}")


def _print_disk_report(disk_data: Dict[str, Any]) -> None:
    print("\n[5] Disk Space (Current Volume):")
    if disk_data["error"]:
        print(f"  - Error checking disk space: {disk_data['error']}")
    else:
        print(f"  - Total Size: {disk_data['total_gb']} GB")
        print(f"  - Used: {disk_data['used_gb']} GB ({disk_data['usage_percent']}%)")
        print(f"  - Free: {disk_data['free_gb']} GB")
        if disk_data["usage_percent"] > 90:
            print("  - WARNING: High disk utilization (>90%)!")


def _print_perm_report(perm_data: Dict[str, Any]) -> None:
    print("\n[6] Process Permissions:")
    print(f"  - Elevated Privileges (Admin/Root): {perm_data['is_admin']}")
    print(f"  - Write Access to Temp Directory: {perm_data['temp_writable']}")
    print(f"  - Write Access to Current Workspace: {perm_data['workspace_writable']}")


def print_report(report: Dict[str, Any]) -> None:
    """Print formatted diagnostic report to terminal.

    Args:
        report: The compiled diagnostic dictionary.
    """
    print("=" * 60)
    print("          DEVELOPER MACHINE DIAGNOSTIC REPORT          ")
    print("=" * 60)

    _print_path_report(report["path"])
    _print_python_report(report["python"])
    _print_dep_report(report["dependencies"])
    _print_port_report(report["ports"])
    _print_disk_report(report["disk"])
    _print_perm_report(report["permissions"])
    print("=" * 60)


def main() -> None:
    """CLI execution entrypoint."""
    parser = argparse.ArgumentParser(
        description="Developer Machine Doctor — Diagnose developer environment status."
    )
    parser.add_argument(
        "--json", action="store_true", help="Output diagnostic results in JSON format."
    )
    parser.add_argument(
        "--ports",
        type=str,
        default="80,443,3000,5000,8000,8080",
        help="Comma-separated ports list to check.",
    )

    args = parser.parse_args()

    # Parse port inputs
    try:
        port_list = [int(p.strip()) for p in args.ports.split(",") if p.strip()]
    except ValueError:
        logger_name = "developer_machine_doctor"
        logging.getLogger(logger_name).error(
            "Invalid ports list parameter: %s", args.ports
        )
        sys.exit(1)

    # Compile diagnostics report
    report = {
        "path": check_path_env(),
        "python": check_python_env(),
        "dependencies": check_system_dependencies(),
        "ports": check_port_conflicts(port_list),
        "disk": check_disk_space(),
        "permissions": check_permissions(),
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    else:
        print_report(report)


if __name__ == "__main__":
    main()
