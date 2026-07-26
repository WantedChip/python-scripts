# Network Interface Reporter

A Python command-line utility to inspect local network interfaces, displaying status, IP addresses (IPv4 & IPv6), netmasks, broadcast addresses, and MAC addresses in human-readable console tables or structured JSON output.

## Features

- **Detailed Interface Stats**: Displays interface name, UP/DOWN status, speed, IPv4/IPv6 addresses, netmask, and MAC address.
- **Output Formats**: Supports clean console tables and structured JSON export.
- **Active Interface Filter**: Optionally filter report to include only active (`UP`) network interfaces.

## Usage

```bash
# Print formatted text table report
python main.py

# Print active interfaces in JSON format
python main.py --json --active-only
```

## Running Tests

```bash
python -m unittest discover -s tests
```
