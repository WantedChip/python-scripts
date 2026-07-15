"""port-story: Audits ports and reveals the complete story of owner processes.

Queries PID, name, parent process, working directory, command line, start time,
environment variables, and maps heuristic classifications (Docker, DB, server).
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

psutil: Any = None
try:
    import psutil as ps_lib

    psutil = ps_lib
except ImportError:
    pass

SENSITIVE_KEYWORDS = {
    "KEY",
    "PASS",
    "SECRET",
    "TOKEN",
    "AUTH",
    "PWD",
    "SIGNATURE",
    "CERT",
    "CREDENTIAL",
    "DATABASE",
    "CONN",
}


def sanitize_env_vars(env: Dict[str, str]) -> Dict[str, str]:
    """Mask values of sensitive process environment variables.

    Args:
        env: Raw process environment dictionary.

    Returns:
        Sanitized environment dictionary.
    """
    sanitized = {}
    for k, v in env.items():
        k_upper = k.upper()
        if any(kw in k_upper for kw in SENSITIVE_KEYWORDS):
            sanitized[k] = "[SANITIZED]"
        else:
            sanitized[k] = v
    return sanitized


def get_docker_heuristics(proc: Any) -> bool:
    """Detect if a process is running inside or managed by Docker.

    Args:
        proc: The psutil.Process instance.

    Returns:
        True if Docker association detected, False otherwise.
    """
    try:
        cmdline = " ".join(proc.cmdline()).lower()
        if "docker-proxy" in cmdline or "docker" in proc.name().lower():
            return True

        # Check parent ancestry
        parent = proc.parent()
        if parent and "docker" in parent.name().lower():
            return True

        # Linux cgroup checks
        cgroup_path = f"/proc/{proc.pid}/cgroup"
        if os.path.exists(cgroup_path):
            with open(cgroup_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if "/docker/" in content or "/docker-" in content:
                    return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        pass
    return False


def get_dev_server_heuristics(proc: Any) -> bool:
    """Detect if a process is a local development web server.

    Args:
        proc: The psutil.Process instance.

    Returns:
        True if development server detected, False otherwise.
    """
    try:
        cmdline = " ".join(proc.cmdline()).lower()
        exe = proc.exe().lower() if proc.exe() else ""

        dev_keywords = {
            "webpack",
            "vite",
            "next-dev",
            "next-server",
            "nodemon",
            "live-server",
            "django-admin",
            "manage.py",
            "flask",
            "uvicorn",
            "gunicorn",
            "webpack-dev-server",
            "yarn dev",
            "npm run",
            "pnpm run",
            "react-scripts",
        }
        if any(kw in cmdline for kw in dev_keywords):
            return True

        # Check binary execution locations (local node_modules or venv)
        if any(p in exe for p in ("node_modules", ".bin", "venv", ".venv")):
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


def get_database_heuristics(proc: Any) -> bool:
    """Detect if a process is a known database server.

    Args:
        proc: The psutil.Process instance.

    Returns:
        True if database server detected, False otherwise.
    """
    try:
        name = proc.name().lower()
        cmdline = " ".join(proc.cmdline()).lower()

        db_keywords = {
            "postgres",
            "postgres.exe",
            "mysqld",
            "mysql",
            "redis-server",
            "redis-server.exe",
            "mongod",
            "mongodb",
            "mssql",
            "sqlservr",
            "sqlite",
        }
        if name in db_keywords or any(kw in cmdline for kw in db_keywords):
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


def get_system_service_heuristics(proc: Any) -> bool:
    """Detect if a process is running as a core system daemon or service.

    Args:
        proc: The psutil.Process instance.

    Returns:
        True if system service detected, False otherwise.
    """
    try:
        # Check system accounts
        user = proc.username()
        if user in ("root", "SYSTEM", "NT AUTHORITY\\SYSTEM"):
            return True

        # Check parent PID (init / systemd / launchd)
        parent = proc.parent()
        if parent:
            if parent.pid == 1 or parent.name().lower() in (
                "systemd",
                "init",
                "launchd",
            ):
                return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


def get_process_story(proc: Any, verbose: bool = False) -> Dict[str, Any]:
    # pylint: disable=too-many-branches
    """Retrieve full diagnostic metadata and heuristics for a process.

    Args:
        proc: The psutil.Process instance.
        verbose: True to extract and sanitize environment variables.

    Returns:
        A dictionary of process diagnostics.
    """
    story: Dict[str, Any] = {
        "pid": proc.pid,
        "name": "",
        "exe": "",
        "cwd": "",
        "username": "",
        "start_time": "",
        "cmdline": [],
        "parent": None,
        "tags": [],
        "environment": {},
    }

    try:
        story["name"] = proc.name()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        story["name"] = "Unknown"

    try:
        story["exe"] = proc.exe()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    try:
        story["cwd"] = proc.cwd()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    try:
        story["username"] = proc.username()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    try:
        story["cmdline"] = proc.cmdline()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    try:
        start_ts = proc.create_time()
        story["start_time"] = datetime.fromtimestamp(start_ts).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    try:
        parent = proc.parent()
        if parent:
            story["parent"] = {"pid": parent.pid, "name": parent.name()}
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    # Evaluate Heuristics
    tags = []
    if get_docker_heuristics(proc):
        tags.append("Docker")
    if get_dev_server_heuristics(proc):
        tags.append("Dev Server")
    if get_database_heuristics(proc):
        tags.append("Database")
    if get_system_service_heuristics(proc):
        tags.append("System Service")
    story["tags"] = tags

    # Extract env vars if verbose
    if verbose:
        try:
            env = proc.environ()
            story["environment"] = sanitize_env_vars(env)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            story["environment"] = {
                "error": "Access Denied reading environment variables."
            }

    return story


class PortStory:
    # pylint: disable=too-few-public-methods
    """Scans and analyzes port connections and compiles process histories."""

    def __init__(self, ports: Optional[List[int]] = None) -> None:
        """Initialize the scanner.

        Args:
            ports: Target list of ports to scan.
        """
        self.ports = ports

    def scan(self, verbose: bool = False) -> List[Dict[str, Any]]:
        """Map active internet connections to process details.

        Args:
            verbose: Include environment variables.

        Returns:
            List of dictionaries representing each port story.
        """
        results: List[Dict[str, Any]] = []
        if not psutil:
            return results

        try:
            # Query active TCP/UDP connections
            # pylint: disable=no-member
            conns = psutil.net_connections(kind="inet")
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error querying connections: {str(e)}")
            return results

        # Track unique (port, pid) pairings to avoid duplicating connection records
        seen: Set[tuple[int, Optional[int]]] = set()

        for conn in conns:
            port = conn.laddr.port
            if self.ports and port not in self.ports:
                continue

            # In auto mode, only query listening ports
            if not self.ports and conn.status != "LISTEN":
                continue

            pid = conn.pid
            pair = (port, pid)
            if pair in seen:
                continue
            seen.add(pair)

            port_data = {
                "port": port,
                "status": conn.status,
                "local_address": f"{conn.laddr.ip}:{conn.laddr.port}",
                "remote_address": (
                    f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A"
                ),
                "process": None,
            }

            if pid:
                try:
                    proc = psutil.Process(pid)
                    port_data["process"] = get_process_story(proc, verbose)
                except psutil.NoSuchProcess:
                    pass

            results.append(port_data)

        return sorted(results, key=lambda x: int(x["port"]))


def render_report(stories: List[Dict[str, Any]]) -> None:
    """Print the port stories in a readable CLI dashboard format.

    Args:
        stories: List of collected port story dictionaries.
    """
    print("\n" + "=" * 65)
    print("                      PORT STORY REPORT")
    print("=" * 65)

    if not stories:
        print("No active ports matched the target scan.")
        print("=" * 65)
        return

    for idx, s in enumerate(stories, 1):
        print(f"\n{idx}. Port {s['port']} [{s['status']}]")
        print(f"   Local Address : {s['local_address']}")
        print(f"   Remote Address: {s['remote_address']}")

        p = s["process"]
        if not p:
            print("   Process       : Unknown (System / Orphaned Connection)")
            continue

        print(f"   Process Name  : {p['name']} (PID: {p['pid']})")
        if p["exe"]:
            print(f"   Executable    : {p['exe']}")
        if p["cwd"]:
            print(f"   Working Dir   : {p['cwd']}")
        if p["username"]:
            print(f"   User Owner    : {p['username']}")
        if p["start_time"]:
            print(f"   Start Time    : {p['start_time']}")
        if p["cmdline"]:
            print(f"   Command Line  : {' '.join(p['cmdline'])}")
        if p["parent"]:
            print(
                f"   Parent Process: {p['parent']['name']} (PID: {p['parent']['pid']})"
            )

        tags = p.get("tags", [])
        if tags:
            print(f"   Tags / Types  : {', '.join(tags)}")

        env = p.get("environment", {})
        if env:
            print("   Environment Variables:")
            for k, v in sorted(env.items()):
                print(f"     - {k}: {v}")

    print("\n" + "=" * 65)


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Show full process diagnostic history for active ports."
    )
    parser.add_argument(
        "ports",
        type=int,
        nargs="*",
        help="Optional port numbers to scan. Audits all LISTEN ports if omitted.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output reports in JSON structure."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include sanitized environment variables.",
    )

    args = parser.parse_args()

    if not psutil:
        print("Error: The 'psutil' package is required to scan ports.")
        sys.exit(1)

    scanner = PortStory(ports=args.ports if args.ports else None)
    results = scanner.scan(verbose=args.verbose)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        render_report(results)


if __name__ == "__main__":
    main()
