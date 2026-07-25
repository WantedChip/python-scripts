#!/usr/bin/env python3
"""Country Info Fetcher script.

Retrieves country data (capital, population, region, flag URL, currency,
languages) from REST Countries API.
"""

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, cast

REST_COUNTRIES_BASE = "https://restcountries.com/v3.1"


def fetch_json(url: str, timeout: int = 10) -> Optional[Any]:
    """Fetch JSON payload from REST Countries endpoint.

    Args:
        url: Request URL string.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON output (list or dict) or None on failure.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "CountryInfoFetcher/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            print(f"Error 404: Country not found for query URL {url}", file=sys.stderr)
        else:
            print(f"HTTP Error {err.code}: {err.reason}", file=sys.stderr)
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Network error accessing {url}: {err}", file=sys.stderr)
    return None


def fetch_country_info(country_name: str) -> List[Dict[str, Any]]:
    """Fetch country data by name using REST Countries API.

    Args:
        country_name: Country name or substring.

    Returns:
        List of country raw payload dictionaries.
    """
    query = urllib.parse.quote(country_name.strip())
    url = f"{REST_COUNTRIES_BASE}/name/{query}"
    res = fetch_json(url)
    return res if isinstance(res, list) else []


def parse_country_data(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Parse raw REST Countries payload into structured clean country record.

    Args:
        raw: Single raw country dictionary from API.

    Returns:
        Parsed dictionary with standard country attributes.
    """
    # pylint: disable=too-many-locals
    name_dict = raw.get("name", {})
    common_name = name_dict.get("common", "Unknown")
    official_name = name_dict.get("official", "Unknown")

    capitals = raw.get("capital", [])
    capital_str = ", ".join(capitals) if isinstance(capitals, list) else "N/A"

    population = raw.get("population", 0)
    region = raw.get("region", "N/A")
    subregion = raw.get("subregion", "N/A")
    area = raw.get("area", 0.0)

    # Currencies
    currencies_raw = raw.get("currencies", {})
    curr_list = []
    if isinstance(currencies_raw, dict):
        for code, details in currencies_raw.items():
            c_name = details.get("name", code)
            c_symbol = details.get("symbol", "")
            curr_list.append(f"{c_name} ({c_symbol})" if c_symbol else c_name)
    currencies_str = ", ".join(curr_list) if curr_list else "N/A"

    # Languages
    languages_raw = raw.get("languages", {})
    lang_list = list(languages_raw.values()) if isinstance(languages_raw, dict) else []
    languages_str = ", ".join(lang_list) if lang_list else "N/A"

    # Flags & Maps
    flag_png = raw.get("flags", {}).get("png", "N/A")
    flag_emoji = raw.get("flag", "")
    google_maps = raw.get("maps", {}).get("googleMaps", "N/A")
    cca2 = raw.get("cca2", "N/A")

    return {
        "common_name": common_name,
        "official_name": official_name,
        "country_code": cca2,
        "capital": capital_str,
        "population": population,
        "region": region,
        "subregion": subregion,
        "area_sq_km": area,
        "currencies": currencies_str,
        "languages": languages_str,
        "flag_url": flag_png,
        "flag_emoji": flag_emoji,
        "google_maps": google_maps,
    }


def format_country_card(country: Dict[str, Any]) -> str:
    """Format parsed country details into a terminal facts card.

    Args:
        country: Parsed country dictionary.

    Returns:
        Formatted ASCII string facts card.
    """
    flag = country.get("flag_emoji", "")
    title = f"{country.get('common_name', 'COUNTRY')} {flag}".strip()

    lines = [
        "==================================================",
        f"  COUNTRY FACTS: {title.upper()}",
        "==================================================",
        f"  Common Name   : {country.get('common_name')}",
        f"  Official Name : {country.get('official_name')}",
        f"  Country Code  : {country.get('country_code')}",
        f"  Capital       : {country.get('capital')}",
        f"  Population    : {country.get('population'):,}",
        f"  Region        : {country.get('region')} ({country.get('subregion')})",
        f"  Area          : {country.get('area_sq_km'):,} sq km",
        "--------------------------------------------------",
        f"  Currencies    : {country.get('currencies')}",
        f"  Languages     : {country.get('languages')}",
        "--------------------------------------------------",
        f"  Flag Image    : {country.get('flag_url')}",
        f"  Google Maps   : {country.get('google_maps')}",
        "==================================================",
    ]
    return "\n".join(lines)


def export_json(countries: List[Dict[str, Any]], filepath: str) -> bool:
    """Export parsed country data list to a JSON file.

    Args:
        countries: List of parsed country dictionaries.
        filepath: Target output file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(countries, f, indent=2)
        return True
    except OSError as err:
        print(f"Error exporting JSON to {filepath}: {err}", file=sys.stderr)
        return False


def export_csv(countries: List[Dict[str, Any]], filepath: str) -> bool:
    """Export parsed country data list to a CSV file.

    Args:
        countries: List of parsed country dictionaries.
        filepath: Target output file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    if not countries:
        return False

    fieldnames = list(countries[0].keys())

    try:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(countries)
        return True
    except OSError as err:
        print(f"Error exporting CSV to {filepath}: {err}", file=sys.stderr)
        return False


def main() -> None:
    """Main CLI entrypoint for Country Info Fetcher."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch country information, facts, and stats from REST Countries API."
        )
    )
    parser.add_argument(
        "country", help="Country name or search string (e.g. Japan, Canada)"
    )
    parser.add_argument("--json", "-j", help="Output filepath for JSON export")
    parser.add_argument("--csv", "-c", help="Output filepath for CSV export")

    args = parser.parse_args()

    print(f"Fetching country data for '{args.country}'...")
    raw_results = fetch_country_info(args.country)
    if not raw_results:
        print(f"No results found for country '{args.country}'.", file=sys.stderr)
        sys.exit(1)

    parsed_countries = [parse_country_data(item) for item in raw_results]

    print(format_country_card(parsed_countries[0]))

    if len(parsed_countries) > 1:
        print(f"\nOther matching countries ({len(parsed_countries) - 1}):")
        for c in parsed_countries[1:]:
            print(
                f"  • {c['common_name']} ({c['official_name']}) - "
                f"Capital: {c['capital']}"
            )

    if args.json:
        if export_json(parsed_countries, args.json):
            print(f"Exported JSON data to {args.json}")

    if args.csv:
        if export_csv(parsed_countries, args.csv):
            print(f"Exported CSV data to {args.csv}")


if __name__ == "__main__":
    main()
