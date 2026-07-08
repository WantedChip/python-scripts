"""Local Network Device Monitor.

Tracks known and unknown devices on the local network.
Performs a multi-threaded ping sweep to refresh the ARP cache,
then parses the system ARP table to detect joins, leaves, and IP changes.
"""

import argparse
import concurrent.futures
import datetime
import json
import logging
import os
import re
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

# Simple offline MAC OUI prefix lookup database of common vendors
MAC_VENDORS = {
    "00:11:32": "Synology",
    "00:17:88": "Philips Hue",
    "00:25:00": "Apple",
    "00:e0:4c": "Realtek",
    "04:18:d6": "Ubiquiti",
    "08:00:27": "VirtualBox",
    "18:b4:30": "Nest",
    "28:cf:e9": "Apple",
    "3c:d9:2b": "Hewlett Packard",
    "40:b4:cd": "Amazon",
    "50:78:b3": "Sony",
    "70:ee:50": "Netgear",
    "7c:2d:12": "Apple",
    "84:3d:c6": "Huawei",
    "b8:27:eb": "Raspberry Pi Foundation",
    "b8:da:19": "Intel",
    "c0:56:27": "Belkin",
    "c8:d7:19": "Cisco",
    "d0:73:d5": "Samsung",
    "d8:07:b6": "Apple",
    "dc:a6:32": "Raspberry Pi Foundation",
    "e4:95:6e": "TP-Link",
    "f0:18:98": "Apple",
    "f4:f2:6d": "Google",
}


def get_oui(mac: str) -> str:
    """Extracts OUI vendor from MAC address.

    Args:
        mac: MAC address string.

    Returns:
        Vendor name or 'Unknown'.
    """
    clean_mac = mac.replace("-", ":").lower()
    prefix = ":".join(clean_mac.split(":")[:3])
    for key, val in MAC_VENDORS.items():
        if key.lower() == prefix:
            return val
    return "Unknown"


def get_local_ip() -> Optional[str]:
    """Gets the active local IP address by opening a dummy connection.

    Returns:
        Local IP address string or None.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not send actual packets
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:  # pylint: disable=broad-except
        local_ip = None
    finally:
        s.close()
    return local_ip


def get_subnet_ips(subnet_prefix: Optional[str] = None) -> List[str]:
    """Generates all host IPs in the /24 subnet.

    Args:
        subnet_prefix: Subnet prefix e.g., '192.168.1'. If None, auto-detects.

    Returns:
        List of IP strings.
    """
    if not subnet_prefix:
        local_ip = get_local_ip()
        if not local_ip:
            logging.error("Could not auto-detect local IP. Please specify subnet.")
            return []
        parts = local_ip.split(".")
        if len(parts) == 4:
            subnet_prefix = ".".join(parts[:3])
        else:
            return []

    return [f"{subnet_prefix}.{i}" for i in range(1, 255)]


def ping_host(ip: str) -> bool:
    """Pings a single host to refresh the ARP table.

    Args:
        ip: IP address.

    Returns:
        True if host responded, False otherwise.
    """
    # Windows ping args: -n 1 (1 packet), -w 150 (150ms timeout)
    # Posix ping args: -c 1, -W 1 (1 second timeout)
    if sys.platform.startswith("win"):
        cmd = ["ping", "-n", "1", "-w", "150", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]

    try:
        # Hide stdout/stderr to avoid clutter
        res = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        return res.returncode == 0
    except Exception:  # pylint: disable=broad-except
        return False


def ping_sweep(ips: List[str]) -> None:
    """Performs thread-pool ping sweep.

    Args:
        ips: List of IPs to sweep.
    """
    logging.info("Starting ping sweep of %d IPs...", len(ips))
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        executor.map(ping_host, ips)
    logging.info("Ping sweep complete.")


def parse_arp_table() -> List[Tuple[str, str]]:
    """Runs and parses system ARP command output.

    Returns:
        List of tuples: (IP, MAC).
    """
    devices = []
    try:
        # Run system arp command
        # On Windows, 'arp -a' lists all interfaces and addresses
        # On POSIX, 'arp -an' lists numerically
        if sys.platform.startswith("win"):
            cmd = ["arp", "-a"]
        else:
            cmd = ["arp", "-an"]

        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        output = res.stdout

        # Regex to match IP and MAC address patterns
        # MAC format can be 00-11-22-33-44-55 or 00:11:22:33:44:55
        ip_mac_pattern = re.compile(
            r"([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})\s+"
            r"([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:]"
            r"[0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})"
        )

        for line in output.splitlines():
            match = ip_mac_pattern.search(line)
            if match:
                ip, mac = match.groups()
                # Normalize MAC to lowercase colon-separated
                mac = mac.replace("-", ":").lower()
                # Exclude broadcast/multicast MACs
                is_broadcast = mac in (
                    "ff:ff:ff:ff:ff:ff",
                    "00:00:00:00:00:00",
                )
                if not is_broadcast and not mac.startswith("01:00:5e"):
                    devices.append((ip, mac))

    except Exception as e:  # pylint: disable=broad-except
        logging.error("Failed to run or parse arp: %s", e)

    return devices


def load_state(state_file: str) -> Dict[str, Any]:
    """Loads state file JSON.

    Args:
        state_file: Path to state file.

    Returns:
        Dict state object.
    """
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:  # pylint: disable=broad-except
            logging.error("Error reading state file: %s", e)

    return {"devices": {}, "history": []}


def save_state(state_file: str, state: Dict[str, Any]) -> None:
    """Saves state file JSON.

    Args:
        state_file: Path to state file.
        state: State dictionary to save.
    """
    try:
        # Create parent directory if needed
        parent = os.path.dirname(state_file)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Error writing state file: %s", e)


def update_monitor(
    state: Dict[str, Any],
    active_devices: List[Tuple[str, str]],
    history_limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Compares active devices against previous state and updates records.

    Args:
        state: State dictionary loaded from file.
        active_devices: List of (IP, MAC) tuples currently online.
        history_limit: Maximum history logs to retain.

    Returns:
        List of changed events.
    """
    now_iso = datetime.datetime.now().isoformat()
    changes = []

    # Map current active MACs
    active_map = {mac: ip for ip, mac in active_devices}
    stored_devices = state.setdefault("devices", {})
    history = state.setdefault("history", [])

    # Process active devices
    for mac, ip in active_map.items():
        vendor = get_oui(mac)
        if mac not in stored_devices:
            # Device Joined (New device)
            stored_devices[mac] = {
                "ip": ip,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "name": f"Device {ip.split('.')[-1]}",
                "vendor": vendor,
                "status": "online",
            }
            event = {
                "timestamp": now_iso,
                "event": "joined",
                "mac": mac,
                "ip": ip,
                "vendor": vendor,
            }
            history.append(event)
            changes.append(event)
        else:
            dev = stored_devices[mac]
            # Device was offline, now online
            if dev.get("status") == "offline":
                dev["status"] = "online"
                dev["ip"] = ip  # Update possibly changed IP
                dev["last_seen"] = now_iso
                event = {
                    "timestamp": now_iso,
                    "event": "joined",
                    "mac": mac,
                    "ip": ip,
                    "vendor": dev.get("vendor"),
                }
                history.append(event)
                changes.append(event)
            else:
                # Still online, check for IP change
                if dev.get("ip") != ip:
                    old_ip = dev.get("ip")
                    dev["ip"] = ip
                    event = {
                        "timestamp": now_iso,
                        "event": "ip_changed",
                        "mac": mac,
                        "old_ip": old_ip,
                        "new_ip": ip,
                    }
                    history.append(event)
                    changes.append(event)
                dev["last_seen"] = now_iso

    # Process missing devices (Left)
    for mac, dev in stored_devices.items():
        if dev.get("status") == "online" and mac not in active_map:
            dev["status"] = "offline"
            event = {
                "timestamp": now_iso,
                "event": "left",
                "mac": mac,
                "ip": dev.get("ip"),
                "vendor": dev.get("vendor"),
            }
            history.append(event)
            changes.append(event)

    # Prune history if it exceeds limit
    if len(history) > history_limit:
        state["history"] = history[-history_limit:]

    return changes


def print_report(state: Dict[str, Any], changes: List[Dict[str, Any]]) -> None:
    """Prints scan report to stdout.

    Args:
        state: State dictionary.
        changes: List of events that occurred in this run.
    """
    devices = state["devices"]
    online_devices = [d for d in devices.values() if d["status"] == "online"]

    print("=" * 60)
    print("LOCAL NETWORK MONITOR REPORT")
    print("=" * 60)
    print(f"Total Configured Devices: {len(devices)}")
    print(f"Current Online Devices:   {len(online_devices)}")
    print("=" * 60)

    print("\nONLINE DEVICES:")
    if not online_devices:
        print("  No online devices discovered.")
    else:
        # Header
        print(f"{'IP Address':<16} {'MAC Address':<20} {'Vendor':<15} {'Name':<15}")
        print("-" * 66)

        def ip_key(item: Tuple[str, Dict[str, Any]]) -> bytes:
            return socket.inet_aton(item[1]["ip"])

        online_list = [
            (mac, dev) for mac, dev in devices.items()
            if dev["status"] == "online"
        ]
        for mac, dev in sorted(online_list, key=ip_key):
            print(
                f"{dev['ip']:<16} {mac:<20} "
                f"{dev['vendor']:<15} {dev['name']:<15}"
            )

    print("\n" + "=" * 60)
    print("EVENTS IN THIS SCAN:")
    if not changes:
        print("  No joins or leaves detected.")
    else:
        for c in changes:
            evt = c["event"].upper()
            if evt == "JOINED":
                print(f"  [+] JOINED: {c['ip']} ({c['mac']}) - {c['vendor']}")
            elif evt == "LEFT":
                print(f"  [-] LEFT:   {c['ip']} ({c['mac']}) - {c['vendor']}")
            elif evt == "IP_CHANGED":
                print(
                    f"  [*] IP CHG: {c['mac']} moved "
                    f"from {c['old_ip']} to {c['new_ip']}"
                )
    print("=" * 60)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Local Network Device Monitor: Track devices joining and "
            "leaving your local subnet."
        )
    )
    parser.add_argument(
        "-s",
        "--subnet",
        help="Subnet prefix to scan (e.g. '192.168.1'). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--state-file",
        default="devices_state.json",
        help="Path to JSON state tracking file (default: devices_state.json)",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=1000,
        help="Max scan history logs to keep (default: 1000)",
    )
    parser.add_argument(
        "-n",
        "--no-sweep",
        action="store_true",
        help="Skip ping sweep; read ARP table directly",
    )
    parser.add_argument(
        "-j", "--json-output", action="store_true", help="Print state JSON to stdout"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logs"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Subnet IPs
    ips = get_subnet_ips(args.subnet)

    # Ping sweep unless disabled
    if not args.no_sweep and ips:
        ping_sweep(ips)

    # Read ARP table
    active_devices = parse_arp_table()

    # Load state
    state = load_state(args.state_file)

    # Process updates
    changes = update_monitor(state, active_devices, args.history_limit)

    # Save state
    save_state(args.state_file, state)

    if args.json_output:
        print(json.dumps(state, indent=2))
    else:
        print_report(state, changes)


if __name__ == "__main__":
    main()
