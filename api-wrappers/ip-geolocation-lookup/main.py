"""IP Geolocation Lookup.

Fetches IP geolocation data (country, city, ISP, lat/lon, timezone) using free IP APIs.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, cast


def fetch_ip_geolocation(ip_address: Optional[str] = None) -> Dict[str, Any]:
    """Fetch geolocation metadata for a given IP address or local public IP.

    Args:
        ip_address: Specific IPv4/IPv6 address to look up. If None or empty,
            queries local public IP.

    Returns:
        Dictionary containing geolocation details.

    Raises:
        ValueError: If API query returns an error status.
        RuntimeError: On HTTP error or network failure.
    """
    target = ip_address.strip() if ip_address else ""
    url = f"http://ip-api.com/json/{target}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "IPGeolocationLookup/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            if response.status == 200:
                raw_data = response.read().decode("utf-8")
                data = json.loads(raw_data)
                if data.get("status") == "fail":
                    raise ValueError(
                        f"API query failed: {data.get('message', 'Unknown error')}"
                    )
                return cast(Dict[str, Any], data)
            raise RuntimeError(f"HTTP Error: Server returned status {response.status}")
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"HTTP Error {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Network error: {err.reason}") from err


def format_summary(data: Dict[str, Any]) -> str:
    """Format geolocation dictionary into a clean terminal summary string.

    Args:
        data: Geolocation dictionary returned by API.

    Returns:
        Formatted summary string.
    """
    country_str = f"{data.get('country', 'N/A')} ({data.get('countryCode', 'N/A')})"
    region_str = f"{data.get('regionName', 'N/A')} ({data.get('region', 'N/A')})"

    lines = [
        "==========================================",
        "          IP GEOLOCATION SUMMARY          ",
        "==========================================",
        f" IP Address  : {data.get('query', 'N/A')}",
        f" Country     : {country_str}",
        f" Region      : {region_str}",
        f" City        : {data.get('city', 'N/A')}",
        f" Zip/Postal  : {data.get('zip', 'N/A')}",
        f" Coordinates : {data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}",
        f" Timezone    : {data.get('timezone', 'N/A')}",
        f" ISP         : {data.get('isp', 'N/A')}",
        f" Organization: {data.get('org', 'N/A')}",
        f" AS Network  : {data.get('as', 'N/A')}",
        "==========================================",
    ]
    return "\n".join(lines)


def main() -> None:
    """CLI entry point for IP Geolocation Lookup."""
    parser = argparse.ArgumentParser(
        description="Fetch IP geolocation data (country, city, ISP, lat/lon, timezone)."
    )
    parser.add_argument(
        "ip",
        nargs="?",
        default="",
        help="Target IP address (e.g. 8.8.8.8). Defaults to local public IP.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to export JSON results.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Output raw JSON instead of formatted summary.",
    )

    args = parser.parse_args()

    try:
        data = fetch_ip_geolocation(args.ip)

        if args.raw:
            print(json.dumps(data, indent=2))
        else:
            print(format_summary(data))

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"\nGeolocation data saved to {args.output}")

    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
