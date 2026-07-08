# Local Network Device Monitor

Track known devices joining or leaving your local network and maintain a history log.

## Usage

```bash
python device_monitor.py [options]
```

### Examples

```bash
# Auto-detect local IP and scan the local /24 subnet (runs a ping sweep + ARP check)
python device_monitor.py

# Scan a specific subnet
python device_monitor.py -s 192.168.1

# Save tracking state to a custom file
python device_monitor.py --state-file C:\temp\network_state.json

# Read local ARP table directly without running a ping sweep first
python device_monitor.py --no-sweep

# Output the tracked devices state as JSON
python device_monitor.py -j
```

## Requirements

None. This script runs entirely on Python's standard library.

## Notes

* To populate the system ARP cache quickly, this script performs a highly concurrent multi-threaded ping sweep (50 parallel workers) across the target /24 network.
* The host IP to MAC mapping is parsed from the system's local ARP table command (`arp -a` on Windows, `arp -an` on Linux/Mac).
* The script matches discovered MAC addresses against a local offline OUI vendor prefixes list to display manufacturer names (e.g. Apple, Synology, TP-Link).
* Device statuses ("online", "offline"), IP address migrations, and first/last seen timestamps are stored in `devices_state.json`.
