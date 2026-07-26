"""Network Interface Reporter.

Displays IP addresses, MAC addresses, netmasks, and statuses of all local
network interfaces in clean console tables or structured JSON output.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import socket
import sys
from typing import Any, Dict, List, Optional

try:
    import psutil
except ImportError:
    psutil = None


def get_address_family_name(family: int) -> str:
    """Helper to convert socket family constants into human readable string."""
    if family == socket.AF_INET:
        return "IPv4"
    if family == socket.AF_INET6:
        return "IPv6"
    if hasattr(psutil, "AF_LINK") and family == getattr(psutil, "AF_LINK", None):
        return "MAC"
    if hasattr(socket, "AF_LINK") and family == getattr(socket, "AF_LINK", None):
        return "MAC"
    af_packet = getattr(socket, "AF_PACKET", None)
    if af_packet is not None and family == af_packet:
        return "MAC"
    return str(family)


def collect_network_interfaces(
    addrs_data: Optional[Dict[str, List[Any]]] = None,
    stats_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Collects network interface information into a structured list of dicts.

    Args:
        addrs_data: Optional override of psutil.net_if_addrs() for testing.
        stats_data: Optional override of psutil.net_if_stats() for testing.

    Returns:
        List of dictionaries containing interface properties.
    """
    if addrs_data is None:
        if psutil is None:
            err_msg = "psutil package is required to collect network interfaces."
            raise RuntimeError(err_msg)
        addrs_data = psutil.net_if_addrs()

    if stats_data is None:
        if psutil is not None:
            stats_data = psutil.net_if_stats()
        else:
            stats_data = {}

    interfaces: List[Dict[str, Any]] = []

    for iface_name, addrs in addrs_data.items():
        iface_stats = stats_data.get(iface_name)
        is_up = getattr(iface_stats, "isup", True)
        speed_mbps = getattr(iface_stats, "speed", 0)

        ipv4_addrs: List[Dict[str, str]] = []
        ipv6_addrs: List[Dict[str, str]] = []
        mac_addr: Optional[str] = None

        for addr in addrs:
            fam_str = get_address_family_name(addr.family)
            if fam_str == "IPv4":
                ipv4_addrs.append(
                    {
                        "address": addr.address,
                        "netmask": addr.netmask or "",
                        "broadcast": addr.broadcast or "",
                    }
                )
            elif fam_str == "IPv6":
                ipv6_addrs.append(
                    {
                        "address": addr.address,
                        "netmask": addr.netmask or "",
                    }
                )
            elif fam_str == "MAC" or ":" in addr.address or "-" in addr.address:
                # Basic heuristic for MAC address if family identifier varies
                if not mac_addr and addr.address:
                    mac_addr = addr.address

        interfaces.append(
            {
                "name": iface_name,
                "is_up": is_up,
                "status": "UP" if is_up else "DOWN",
                "speed_mbps": speed_mbps,
                "mac_address": mac_addr or "N/A",
                "ipv4": ipv4_addrs,
                "ipv6": ipv6_addrs,
            }
        )

    return interfaces


def format_console_report(interfaces: List[Dict[str, Any]]) -> str:
    """Formats interface information into a clean console report table."""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"{'NETWORK INTERFACE REPORT':^80}")
    lines.append("=" * 80)

    if not interfaces:
        lines.append("No network interfaces found.")
        return "\n".join(lines)

    for iface in interfaces:
        status_str = f"[{iface['status']}]"
        lines.append(f"\nInterface: {iface['name']} {status_str}")
        lines.append(f"  MAC Address:  {iface['mac_address']}")
        lines.append(f"  Speed (Mbps): {iface['speed_mbps']}")

        if iface["ipv4"]:
            lines.append("  IPv4 Addresses:")
            for ip in iface["ipv4"]:
                mask = ip["netmask"]
                netmask_info = f" (Netmask: {mask})" if mask else ""
                lines.append(f"    - {ip['address']}{netmask_info}")
        else:
            lines.append("  IPv4 Addresses: None")

        if iface["ipv6"]:
            lines.append("  IPv6 Addresses:")
            for ip in iface["ipv6"]:
                lines.append(f"    - {ip['address']}")

        lines.append("-" * 40)

    return "\n".join(lines)


def format_json_report(interfaces: List[Dict[str, Any]]) -> str:
    """Formats interface information as formatted JSON string."""
    return json.dumps({"interfaces": interfaces}, indent=2)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Network Interface Reporter")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report in JSON format",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only display active (UP) interfaces",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parsed = parse_args(args)

    try:
        interfaces = collect_network_interfaces()
    except (RuntimeError, OSError) as e:
        print(f"Error inspecting network interfaces: {e}", file=sys.stderr)
        return 1

    if parsed.active_only:
        interfaces = [i for i in interfaces if i["is_up"]]

    if parsed.json:
        print(format_json_report(interfaces))
    else:
        print(format_console_report(interfaces))

    return 0


if __name__ == "__main__":
    sys.exit(main())
