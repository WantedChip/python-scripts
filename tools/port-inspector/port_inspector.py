"""Process Port Inspector.

Lists network connections and displays process details for each port.
Supports searching, filtering, and terminating processes safely.
"""

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional
import psutil


def get_process_info(pid: int) -> Dict[str, Any]:
    """Retrieves detailed process info safely.

    Args:
        pid: The process ID.

    Returns:
        Dict of process properties.
    """
    info = {
        "pid": pid,
        "name": "Unknown",
        "path": "Unknown",
        "user": "Unknown",
        "status": "Unknown",
    }
    if pid == 0:
        info["name"] = "System Idle Process"
        return info

    try:
        proc = psutil.Process(pid)
        info["name"] = proc.name()
        try:
            info["path"] = proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            info["path"] = "Access Denied"
        try:
            info["user"] = proc.username()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            info["user"] = "Access Denied"
        info["status"] = proc.status()
    except psutil.NoSuchProcess:
        info["name"] = "No Such Process"
    except psutil.AccessDenied:
        info["name"] = "Access Denied"

    return info


def list_connections(
    port_filter: Optional[int] = None, protocol: str = "all"
) -> List[Dict[str, Any]]:
    """Lists connections with process details.

    Args:
        port_filter: If set, filters connections by this port.
        protocol: Protocol to scan ('tcp', 'udp', 'all').

    Returns:
        List of connection dicts.
    """
    conns = []
    kind_map = {
        "tcp": "tcp",
        "udp": "udp",
        "all": "inet",
    }
    kind = kind_map.get(protocol, "inet")

    try:
        net_conns = psutil.net_connections(kind=kind)
    except (psutil.AccessDenied, PermissionError) as e:
        logging.error("Insufficient privileges to query connections: %s", e)
        return []

    for conn in net_conns:
        # Local port filter
        local_port = conn.laddr.port if conn.laddr else None
        if port_filter is not None and local_port != port_filter:
            continue

        # Process PID
        pid = conn.pid
        proc_info = (
            get_process_info(pid)
            if pid
            else {
                "pid": None,
                "name": "-",
                "path": "-",
                "user": "-",
                "status": "-",
            }
        )

        local_addr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "-"
        remote_addr = "-"
        if conn.raddr:
            remote_addr = f"{conn.raddr.ip}:{conn.raddr.port}"

        conns.append(
            {
                "protocol": conn.type.name,  # SOCK_STREAM (TCP) or SOCK_DGRAM (UDP)
                "local_address": local_addr,
                "local_port": local_port,
                "remote_address": remote_addr,
                "state": conn.status,
                "pid": pid,
                "process_name": proc_info["name"],
                "process_path": proc_info["path"],
                "process_user": proc_info["user"],
            }
        )

    return conns


def terminate_process(pid: int, force: bool = False) -> bool:  # pylint: disable=too-many-return-statements
    """Safely or forcefully terminates a process.

    Args:
        pid: The process ID to terminate.
        force: If True, uses force kill. Otherwise tries soft termination first.

    Returns:
        True if terminated successfully, False otherwise.
    """
    if pid == 0:
        logging.error("Cannot terminate System Idle Process (PID 0).")
        return False

    try:
        proc = psutil.Process(pid)
        if force:
            logging.info("Sending kill (force) signal to PID %d...", pid)
            proc.kill()
        else:
            logging.info("Sending terminate (soft) signal to PID %d...", pid)
            proc.terminate()

        # Wait for termination
        gone, alive = psutil.wait_procs([proc], timeout=3)
        if gone:
            logging.info("Process PID %d terminated successfully.", pid)
            return True

        if alive:
            logging.warning("Process PID %d is still alive.", pid)
            if not force:
                print(f"Soft termination failed. PID {pid} is still running.")
                confirm = input("Would you like to force kill? (y/N): ")
                if confirm.lower() == "y":
                    return terminate_process(pid, force=True)
            return False

    except psutil.NoSuchProcess:
        logging.error("No process found with PID %d.", pid)
        return True
    except psutil.AccessDenied:
        logging.error(
            "Access denied to terminate PID %d. "
            "Run with administrator privileges.",
            pid,
        )
        return False

    return False


def print_table(connections: List[Dict[str, Any]]) -> None:
    """Prints connections in a neat table.

    Args:
        connections: List of connections.
    """
    if not connections:
        print("No matching connections found.")
        return

    # Header format
    header_fmt = "{:<8} {:<24} {:<24} {:<15} {:<8} {:<20} {:<15}"
    row_fmt = "{:<8} {:<24} {:<24} {:<15} {:<8} {:<20} {:<15}"

    print("-" * 120)
    print(
        header_fmt.format(
            "Proto",
            "Local Address",
            "Remote Address",
            "State",
            "PID",
            "Process Name",
            "Owner",
        )
    )
    print("-" * 120)

    for conn in connections:
        # Map socket types to user-friendly strings
        proto = "TCP" if "STREAM" in conn["protocol"] else "UDP"
        pid_str = str(conn["pid"]) if conn["pid"] else "-"
        print(
            row_fmt.format(
                proto,
                conn["local_address"],
                conn["remote_address"],
                conn["state"],
                pid_str,
                conn["process_name"][:20],
                conn["process_user"][:15],
            )
        )
    print("-" * 120)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Process Port Inspector: Inspect which process owns which port "
            "and terminate it."
        )
    )
    parser.add_argument(
        "-p", "--port", type=int, help="Filter connections by local port number"
    )
    parser.add_argument(
        "--proto",
        choices=["tcp", "udp", "all"],
        default="all",
        help="Filter connections by protocol (default: all)",
    )
    parser.add_argument(
        "-k",
        "--kill",
        action="store_true",
        help="Kill process owning the specified local port (requires -p/--port)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force kill the process without confirmation prompt",
    )
    parser.add_argument(
        "-j", "--json-output", action="store_true", help="Output results in JSON format"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    if args.kill and args.port is None:
        print(
            "Error: --kill requires specifying a local port with --port or -p.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Fetch connections
    conns = list_connections(port_filter=args.port, protocol=args.proto)

    if args.kill:
        # Find owning PIDs
        pids = {c["pid"] for c in conns if c["pid"] is not None}
        if not pids:
            print(f"No active process found listening on port {args.port}.")
            sys.exit(1)

        print(f"Found process(es) on port {args.port}: {list(pids)}")
        success = True
        for pid in pids:
            proc_info = get_process_info(pid)
            print(
                f"Process Details: PID={pid}, "
                f"Name={proc_info['name']}, "
                f"Executable={proc_info['path']}"
            )

            if not args.force:
                confirm = input(
                    f"Are you sure you want to terminate process {pid}? (y/N): "
                )
                if confirm.lower() != "y":
                    print(f"Skipping PID {pid}.")
                    success = False
                    continue

            if not terminate_process(pid, force=args.force):
                success = False

        sys.exit(0 if success else 1)

    if args.json_output:
        print(json.dumps(conns, indent=2))
    else:
        print_table(conns)


if __name__ == "__main__":
    main()
