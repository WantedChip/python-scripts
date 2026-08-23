#!/usr/bin/env python3
"""University Search Fetcher script.

Searches universities by country name or title via Hipolabs Universities API
(`universities.hipolabs.com`). Extracts domains, web page URLs, and exports
matching results to JSON/CSV files.
"""

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, cast

HIPOLABS_API_URL = "http://universities.hipolabs.com/search"


def fetch_json(url: str, timeout: int = 10) -> Optional[Any]:
    """Fetch JSON data from a URL using urllib.

    Args:
        url: Direct API request URL.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON output (list or dict) or None on failure.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "UniversitySearchFetcher/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error requesting {url}: {err}", file=sys.stderr)
    return None


def search_universities(
    country: Optional[str] = None, name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search universities using Hipolabs API.

    Args:
        country: Optional country filter string.
        name: Optional university name / keyword filter string.

    Returns:
        List of raw university search result dictionaries.
    """
    params: Dict[str, str] = {}
    if country and country.strip():
        params["country"] = country.strip()
    if name and name.strip():
        params["name"] = name.strip()

    query_str = urllib.parse.urlencode(params)
    url = f"{HIPOLABS_API_URL}?{query_str}"

    data = fetch_json(url)
    if data is None:
        raise RuntimeError(f"Network error: failed to fetch data from {url}")
    return cast(List[Dict[str, Any]], data)


def extract_university_details(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract clean standardized details from raw API record.

    Args:
        record: Raw university record dict.

    Returns:
        Dict with keys: 'name', 'country', 'country_code', 'state_province',
        'domains', 'web_pages', 'primary_website', 'primary_domain'.
    """
    web_pages = record.get("web_pages", [])
    domains = record.get("domains", [])
    primary_website = web_pages[0] if web_pages else "N/A"
    primary_domain = domains[0] if domains else "N/A"
    return {
        "name": record.get("name", "Unknown"),
        "country": record.get("country", "Unknown"),
        "country_code": record.get("alpha_two_code", ""),
        "state_province": record.get("state-province") or "",
        "domains": ", ".join(domains),
        "web_pages": ", ".join(web_pages),
        "primary_website": primary_website,
        "primary_domain": primary_domain,
    }


def format_university_table(records: List[Dict[str, Any]], limit: int = 10) -> str:
    """Format matching university records into a terminal ASCII table.

    Args:
        records: List of parsed university records.
        limit: Maximum number of rows to print in terminal table.

    Returns:
        Formatted ASCII table string.
    """
    display_records = records[:limit]
    if not display_records:
        return "No results to display."

    line_sep = "=" * 80
    count_str = f"Showing {len(display_records)} of {len(records)}"
    lines = [
        line_sep,
        f"  UNIVERSITY SEARCH RESULTS ({count_str})",
        line_sep,
        f"{'Name':<40} | {'Country':<15} | {'Website':<40}",
        "-" * 80,
    ]

    for r in display_records:
        name = r["name"][:38] + ".." if len(r["name"]) > 40 else r["name"]
        country = r["country"][:15]
        website = r["primary_website"][:40]
        lines.append(f"{name:<40} | {country:<15} | {website:<40}")

    lines.append(line_sep)
    return "\n".join(lines)


def export_json(records: List[Dict[str, Any]], filepath: str) -> bool:
    """Export university search records to a JSON file.

    Args:
        records: List of parsed university dictionaries.
        filepath: Target output file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        return True
    except OSError as err:
        print(f"Error exporting JSON to {filepath}: {err}", file=sys.stderr)
        return False


def export_csv(records: List[Dict[str, Any]], filepath: str) -> bool:
    """Export university search records to a CSV file.

    Args:
        records: List of parsed university dictionaries.
        filepath: Target output file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    if not records:
        return False

    fieldnames = list(records[0].keys())

    try:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
        return True
    except OSError as err:
        print(f"Error exporting CSV to {filepath}: {err}", file=sys.stderr)
        return False


def main() -> None:
    """Main CLI entrypoint for University Search Fetcher."""
    parser = argparse.ArgumentParser(
        description=(
            "Search universities by country name or title via Hipolabs "
            "Universities API."
        )
    )
    parser.add_argument(
        "--country", "-c", help="Filter by country name (e.g. Canada, Germany)"
    )
    parser.add_argument(
        "--name", "-n", help="Filter by university title or keyword (e.g. Oxford, Tech)"
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=10,
        help="Max results to display in terminal (default: 10)",
    )
    parser.add_argument("--json", "-j", help="Output filepath for JSON export")
    parser.add_argument("--csv", help="Output filepath for CSV export")

    args = parser.parse_args()

    if not args.country and not args.name:
        parser.error(
            "At least one search filter (--country or --name) must be provided."
        )

    cntry_label = args.country or "Any"
    name_label = args.name or "Any"
    print(f"Searching universities (Country: '{cntry_label}', Name: '{name_label}')...")
    raw_results = search_universities(args.country, args.name)

    if not raw_results:
        print("No matching universities found.", file=sys.stderr)
        sys.exit(1)

    parsed_records = [extract_university_details(item) for item in raw_results]

    print(format_university_table(parsed_records, limit=args.limit))

    if args.json:
        if export_json(parsed_records, args.json):
            print(f"Exported {len(parsed_records)} records to JSON: {args.json}")

    if args.csv:
        if export_csv(parsed_records, args.csv):
            print(f"Exported {len(parsed_records)} records to CSV: {args.csv}")


if __name__ == "__main__":
    main()
