"""Port Availability Checker.

Scans single ports or port ranges across TCP/UDP protocols for local
or remote hosts with custom timeout configuration and structured tabular/JSON reporting.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import concurrent.futures
import json
import socket
import sys
from typing import Any, Dict, List, Optional


def parse_port_specs(port_str: str) -> List[int]:
    """Parse port string spec '80,443,8000-8005' into unique sorted port integers."""
    ports: set[int] = set()
    parts = port_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start, end = int(start_str), int(end_str)
            if start > end or start < 1 or end > 65535:
                raise ValueError(f"Invalid port range: {part}")
            ports.update(range(start, end + 1))
        else:
            p = int(part)
            if p < 1 or p > 65535:
                raise ValueError(f"Port out of range: {p}")
            ports.add(p)
    return sorted(list(ports))


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
    """Test TCP port availability using socket connection attempt."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((host, port))
            is_open = result == 0
            return {
                "host": host,
                "port": port,
                "protocol": "TCP",
                "status": "OPEN" if is_open else "CLOSED",
                "open": is_open,
                "error": None if is_open else f"socket code {result}",
            }
        except (socket.error, OSError) as exc:
            return {
                "host": host,
                "port": port,
                "protocol": "TCP",
                "status": "CLOSED",
                "open": False,
                "error": str(exc),
            }


def check_udp_port(host: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
    """Test UDP port availability by sending standard probe ping."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(b"", (host, port))
            try:
                _data, _addr = sock.recvfrom(1024)
                return {
                    "host": host,
                    "port": port,
                    "protocol": "UDP",
                    "status": "OPEN",
                    "open": True,
                    "error": None,
                }
            except socket.timeout:
                # UDP timeout usually indicates open or filtered
                return {
                    "host": host,
                    "port": port,
                    "protocol": "UDP",
                    "status": "OPEN|FILTERED",
                    "open": True,
                    "error": "No response (timeout)",
                }
        except (socket.error, OSError) as exc:
            return {
                "host": host,
                "port": port,
                "protocol": "UDP",
                "status": "CLOSED",
                "open": False,
                "error": str(exc),
            }


def scan_ports(
    host: str,
    ports: List[int],
    protocol: str = "TCP",
    timeout: float = 2.0,
    max_threads: int = 20,
) -> List[Dict[str, Any]]:
    """Scans multiple ports concurrently."""
    check_fn = check_tcp_port if protocol.upper() == "TCP" else check_udp_port
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_map = {
            executor.submit(check_fn, host, port, timeout): port for port in ports
        }
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())

    return sorted(results, key=lambda x: int(x["port"]))


def format_summary_table(results: List[Dict[str, Any]]) -> str:
    """Format port scan results into ASCII summary table."""
    headers = ["Host", "Port", "Protocol", "Status"]
    rows = []
    for r in results:
        rows.append([r["host"], str(r["port"]), r["protocol"], r["status"]])

    col_widths = [
        max(len(h), max(len(r[i]) for r in rows)) if rows else len(h)
        for i, h in enumerate(headers)
    ]

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(row[i].ljust(col_widths[i]) for i in range(len(headers)))
        for row in rows
    ]

    return "\n".join([header_line, separator] + row_lines)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Port Availability Checker")
    parser.add_argument("host", help="Target hostname or IP address")
    parser.add_argument(
        "-p",
        "--ports",
        default="80,443,22,8080",
        help="Port spec (e.g. '80,443' or '8000-8010')",
    )
    parser.add_argument(
        "--protocol",
        choices=["TCP", "UDP"],
        default="TCP",
        help="Protocol to scan (TCP or UDP)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=2.0,
        help="Socket connection timeout in seconds",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for port-availability-checker."""
    parsed = parse_args(args)

    try:
        port_list = parse_port_specs(parsed.ports)
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    results = scan_ports(
        parsed.host,
        port_list,
        protocol=parsed.protocol,
        timeout=parsed.timeout,
    )

    if parsed.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_summary_table(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
