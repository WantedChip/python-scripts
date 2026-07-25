"""Zipcode Info Fetcher.

Looks up city, state, country, and coordinates for a postal code via Zippopotam.us API.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, cast


def fetch_zipcode_info(
    zipcode: str, country_code: str = "us"
) -> Optional[Dict[str, Any]]:
    """Fetch postal code details from Zippopotam.us API.

    Args:
        zipcode: Postal code to look up (e.g., '90210' or '90001').
        country_code: Two-letter ISO country code (e.g., 'us', 'ca', 'gb').

    Returns:
        Dictionary containing parsed response, or None if lookup failed.
    """
    url = f"http://api.zippopotam.us/{country_code.strip().lower()}/{zipcode.strip()}"
    req = urllib.request.Request(url, headers={"User-Agent": "ZipcodeInfoFetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            if response.status == 200:
                data = response.read().decode("utf-8")
                return cast(Dict[str, Any], json.loads(data))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            print(
                f"Error: Postal code '{zipcode}' not found for country "
                f"'{country_code}'.",
                file=sys.stderr,
            )
        else:
            print(f"HTTP Error {err.code}: {err.reason}", file=sys.stderr)
    except urllib.error.URLError as err:
        print(f"Network error: {err.reason}", file=sys.stderr)
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Unexpected error: {err}", file=sys.stderr)

    return None


def parse_place_details(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse raw Zippopotam.us API dictionary into a structured result.

    Args:
        raw_data: Raw JSON dict from API response.

    Returns:
        Structured data with country, post_code, places list.
    """
    places = []
    for place in raw_data.get("places", []):
        places.append(
            {
                "place_name": place.get("place name", ""),
                "state": place.get("state", ""),
                "state_abbreviation": place.get("state abbreviation", ""),
                "latitude": place.get("latitude", ""),
                "longitude": place.get("longitude", ""),
            }
        )

    return {
        "post_code": raw_data.get("post code", ""),
        "country": raw_data.get("country", ""),
        "country_abbreviation": raw_data.get("country abbreviation", ""),
        "places": places,
    }


def print_terminal_card(info: Dict[str, Any]) -> None:
    """Print clean terminal card displaying zipcode information.

    Args:
        info: Structured zipcode dictionary.
    """
    country = info.get("country", "N/A")
    country_abbr = info.get("country_abbreviation", "")
    post_code = info.get("post_code", "N/A")
    places = info.get("places", [])

    print("=" * 50)
    print(f"  POSTAL CODE INFORMATION: {post_code} ({country_abbr.upper()})")
    print("=" * 50)
    print(f"Country: {country}")
    print(f"Postal Code: {post_code}")
    print("-" * 50)

    if not places:
        print("No place data available.")
        return

    for idx, place in enumerate(places, 1):
        print(f"Place #{idx}:")
        print(f"  City/Place: {place.get('place_name')}")
        print(
            f"  State/Region: {place.get('state')} ({place.get('state_abbreviation')})"
        )
        print(
            f"  Coordinates: Lat {place.get('latitude')}, Lon {place.get('longitude')}"
        )
        if idx < len(places):
            print("  " + "-" * 30)
    print("=" * 50)


def export_to_json(info: Dict[str, Any], filepath: str) -> None:
    """Export structured information to a JSON file.

    Args:
        info: Structured zipcode dictionary.
        filepath: Destination file path.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"Exported data to '{filepath}' successfully.")


def main() -> None:
    """CLI entry point for zipcode info fetcher."""
    parser = argparse.ArgumentParser(
        description="Look up place information for a postal code."
    )
    parser.add_argument("zipcode", type=str, help="Postal/Zip code (e.g. 90210)")
    parser.add_argument(
        "-c",
        "--country",
        type=str,
        default="us",
        help="Two-letter country code (default: us)",
    )
    parser.add_argument(
        "-o", "--output", type=str, help="Path to export result as JSON file"
    )

    args = parser.parse_args()

    raw_data = fetch_zipcode_info(args.zipcode, args.country)
    if not raw_data:
        sys.exit(1)

    parsed = parse_place_details(raw_data)
    print_terminal_card(parsed)

    if args.output:
        export_to_json(parsed, args.output)


if __name__ == "__main__":
    main()
