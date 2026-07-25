# IP Geolocation Lookup

Looks up IP geolocation details (country, city, ISP, coordinates, timezone) using free IP APIs (ip-api.com).

## Features

- Lookup any target IPv4/IPv6 address or local public IP.
- Retrieves country, city, coordinates, ISP, timezone, and AS network info.
- Clean terminal summary formatting.
- Export results to JSON.

## Usage

```bash
# Look up local IP geolocation
python main.py

# Look up specific IP address
python main.py 8.8.8.8

# Save output to JSON file
python main.py 1.1.1.1 -o ip_info.json

# Print raw API JSON
python main.py 8.8.8.8 --raw
```

## Requirements

Python 3.8+ (Standard Library only).
