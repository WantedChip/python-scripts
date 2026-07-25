"""Public Holiday Fetcher.

Retrieves public holidays for a given country code and year via the Nager.Date API,
supports filtering upcoming holidays, and formats results as tables or JSON.
"""

import argparse
import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, cast


def fetch_public_holidays(year: int, country_code: str) -> List[Dict[str, Any]]:
    """Fetch public holidays from Nager.Date API.

    Args:
        year: Target year (e.g. 2026).
        country_code: Two-letter ISO country code (e.g. 'US', 'GB', 'DE', 'IN').

    Returns:
        List of parsed holiday records.

    Raises:
        ValueError: If country code or year is invalid.
        RuntimeError: If API request fails.
    """
    code = country_code.strip().upper()
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{code}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "PublicHolidayFetcher/1.0 (Python)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            if response.status == 200:
                raw = response.read().decode("utf-8")
                return cast(List[Dict[str, Any]], json.loads(raw))
            raise RuntimeError(f"API Error {response.status}")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise ValueError(
                f"Country code '{code}' or year '{year}' not found."
            ) from err
        raise RuntimeError(f"HTTP Error {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Network connection error: {err.reason}") from err


def filter_upcoming_holidays(
    holidays: List[Dict[str, Any]], reference_date: Optional[datetime.date] = None
) -> List[Dict[str, Any]]:
    """Filter list to only include holidays on or after the reference date.

    Args:
        holidays: List of holiday records.
        reference_date: Cutoff date (defaults to today).

    Returns:
        Filtered list of upcoming holidays.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    upcoming = []
    for h in holidays:
        date_str = h.get("date", "")
        try:
            h_date = datetime.date.fromisoformat(date_str)
            if h_date >= reference_date:
                upcoming.append(h)
        except ValueError:
            continue
    return upcoming


def format_holiday_table(
    holidays: List[Dict[str, Any]], country_code: str, year: int
) -> str:
    """Format holiday list into a plain text table.

    Args:
        holidays: List of holiday dicts.
        country_code: Country code string.
        year: Target year.

    Returns:
        Formatted tabular string.
    """
    if not holidays:
        return f"No holidays found for {country_code} ({year})."

    header = (
        f"Public Holidays for {country_code.upper()} ({year}) - Total: {len(holidays)}"
    )
    lines = [
        header,
        "=" * len(header),
        f"{'Date':<12} | {'Local Name':<30} | {'English Name':<30} | {'Types'}",
        "-" * 85,
    ]

    for h in holidays:
        types_str = ", ".join(h.get("types", [])) if h.get("types") else "Public"
        lines.append(
            f"{h.get('date', 'N/A'):<12} | {h.get('localName', '')[:29]:<30} | "
            f"{h.get('name', '')[:29]:<30} | {types_str}"
        )

    return "\n".join(lines)


def main() -> None:
    """CLI entry point for Public Holiday Fetcher."""
    current_year = datetime.date.today().year

    parser = argparse.ArgumentParser(
        description=(
            "Retrieve public holidays for a country and year via Nager.Date API."
        )
    )
    parser.add_argument(
        "-c",
        "--country",
        default="US",
        help="Two-letter ISO country code (e.g. US, GB, DE, IN, FR). Default: US.",
    )
    parser.add_argument(
        "-y",
        "--year",
        type=int,
        default=current_year,
        help=f"Target year (default: {current_year}).",
    )
    parser.add_argument(
        "--upcoming",
        action="store_true",
        help="Filter to show only upcoming holidays from today.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output display format: table or json (default: table).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Save holiday output to specified JSON or TXT file.",
    )

    args = parser.parse_args()

    try:
        holidays = fetch_public_holidays(year=args.year, country_code=args.country)

        if args.upcoming:
            holidays = filter_upcoming_holidays(holidays)

        if args.format == "json":
            output_str = json.dumps(holidays, indent=2)
        else:
            output_str = format_holiday_table(
                holidays, country_code=args.country, year=args.year
            )

        print(output_str)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                if args.output.suffix.lower() == ".json":
                    json.dump(holidays, f, indent=2)
                else:
                    f.write(output_str)
            print(f"\nHolidays saved to {args.output}")

    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
