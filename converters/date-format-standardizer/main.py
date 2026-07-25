"""Date Format Standardizer Tool.

Detects inconsistent date/time strings in CSV columns (e.g. "MM/DD/YYYY",
"DD-MM-YYYY", "Jan 5 2024") and standardizes them to ISO 8601 (YYYY-MM-DD).
Supports timezone normalization and configurable fallback strategies for
unparseable dates.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-return-statements

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TextIO

COMMON_DATE_FORMATS = [
    # ISO Formats
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    # Year-first slashes
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    # Written month formats
    "%b %d %Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%d %b, %Y",
    "%B %d %Y",
    "%B %d, %Y",
    "%d %B %Y",
    "%d %B, %Y",
    # Slash / Dash formats
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%Y%m%d",
]


def clean_ordinal_suffixes(val_str: str) -> str:
    """Removes 1st, 2nd, 3rd, 4th ordinal suffixes from date strings."""
    return re.sub(r"(\d+)(st|nd|rd|th)", r"\1", val_str)


def parse_date_string(
    date_str: str,
    day_first: bool = False,
    to_utc: bool = False,
    include_time: bool = False,
) -> Optional[str]:
    """Attempts to parse a date string using multiple standard formats.

    :param date_str: Raw input date string.
    :param day_first: If True, prioritize DD/MM/YYYY over MM/DD/YYYY.
    :param to_utc: Convert offset aware datetimes to UTC.
    :param include_time: Format output as YYYY-MM-DDTHH:MM:SSZ if available.
    :return: ISO formatted date string (YYYY-MM-DD), or None if unparseable.
    """
    if not date_str or not date_str.strip():
        return None

    cleaned = date_str.strip()
    cleaned = clean_ordinal_suffixes(cleaned)

    # Check for Unix Timestamp (10 digits seconds, 13 digits millis)
    if re.match(r"^\d{10}$", cleaned):
        try:
            dt = datetime.fromtimestamp(int(cleaned), tz=timezone.utc)
            fmt = "%Y-%m-%dT%H:%M:%SZ" if include_time else "%Y-%m-%d"
            return dt.strftime(fmt)
        except (ValueError, OverflowError):
            pass
    elif re.match(r"^\d{13}$", cleaned):
        try:
            dt = datetime.fromtimestamp(int(cleaned) / 1000.0, tz=timezone.utc)
            fmt = "%Y-%m-%dT%H:%M:%SZ" if include_time else "%Y-%m-%d"
            return dt.strftime(fmt)
        except (ValueError, OverflowError):
            pass

    formats = list(COMMON_DATE_FORMATS)
    if day_first:
        # Move %d/%m/%Y before %m/%d/%Y
        if "%d/%m/%Y" in formats and "%m/%d/%Y" in formats:
            formats.remove("%d/%m/%Y")
            formats.insert(formats.index("%m/%d/%Y"), "%d/%m/%Y")

    parsed_dt = None
    for fmt in formats:
        try:
            parsed_dt = datetime.strptime(cleaned, fmt)
            break
        except ValueError:
            continue

    if not parsed_dt:
        return None

    if to_utc and parsed_dt.tzinfo is not None:
        parsed_dt = parsed_dt.astimezone(timezone.utc)

    has_time = parsed_dt.hour != 0 or parsed_dt.minute != 0 or parsed_dt.second != 0
    if include_time or has_time:
        if parsed_dt.tzinfo is not None:
            return parsed_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return parsed_dt.strftime("%Y-%m-%d %H:%M:%S")

    return parsed_dt.strftime("%Y-%m-%d")


def standardize_csv_dates(
    input_file: str,
    output_file: Optional[str],
    target_columns: List[str],
    day_first: bool = False,
    to_utc: bool = False,
    include_time: bool = False,
    fallback_strategy: str = "keep",
    custom_fallback: str = "",
    delimiter: str = ",",
) -> Dict[str, Any]:
    """Reads a CSV file and standardizes dates in the targeted columns.

    :param input_file: Input CSV file path.
    :param output_file: Output CSV path (or stdout if None).
    :param target_columns: List of header names containing date values.
    :param day_first: Ambiguity priority flag.
    :param to_utc: Normalize to UTC.
    :param include_time: Standardize to date-time format if available.
    :param fallback_strategy: Strategy ('keep', 'null', 'custom').
    :param custom_fallback: Text value to use when strategy is 'custom'.
    :param delimiter: CSV delimiter.
    :return: Summary stats dictionary.
    """
    with open(input_file, mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    # Validate target columns
    missing_cols = [c for c in target_columns if c not in fieldnames]
    if missing_cols:
        raise ValueError(f"Target column(s) not found in CSV: {missing_cols}")

    total_dates_processed = 0
    successfully_parsed = 0
    failed_parses = 0

    output_rows = []
    for row in rows:
        new_row = dict(row)
        for col in target_columns:
            raw_val = row.get(col, "")
            if raw_val:
                total_dates_processed += 1
                parsed = parse_date_string(
                    raw_val,
                    day_first=day_first,
                    to_utc=to_utc,
                    include_time=include_time,
                )
                if parsed is not None:
                    new_row[col] = parsed
                    successfully_parsed += 1
                else:
                    failed_parses += 1
                    if fallback_strategy == "null":
                        new_row[col] = ""
                    elif fallback_strategy == "custom":
                        new_row[col] = custom_fallback
                    else:  # 'keep'
                        new_row[col] = raw_val

        output_rows.append(new_row)

    def write_csv(out_stream: TextIO) -> None:
        writer = csv.DictWriter(out_stream, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(output_rows)

    if output_file:
        with open(output_file, mode="w", newline="", encoding="utf-8") as f_out:
            write_csv(f_out)
    else:
        write_csv(sys.stdout)

    return {
        "total_rows": len(rows),
        "total_dates_processed": total_dates_processed,
        "successfully_parsed": successfully_parsed,
        "failed_parses": failed_parses,
    }


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    desc = "Standardize CSV date columns to ISO 8601 (YYYY-MM-DD)."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--input", "-i", required=True, help="Input CSV file path")
    parser.add_argument(
        "--output",
        "-o",
        help="Output CSV file path (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--columns",
        "-c",
        required=True,
        help="Comma-separated list of target date columns",
    )
    parser.add_argument(
        "--day-first",
        action="store_true",
        help="Prioritize DD/MM/YYYY over MM/DD/YYYY for ambiguous dates",
    )
    parser.add_argument(
        "--to-utc",
        action="store_true",
        help="Convert offset datetimes to UTC timezone",
    )
    parser.add_argument(
        "--include-time",
        action="store_true",
        help="Format with full timestamp if time components exist",
    )
    parser.add_argument(
        "--fallback",
        choices=["keep", "null", "custom"],
        default="keep",
        help="Fallback strategy for unparseable dates (default: keep)",
    )
    parser.add_argument(
        "--custom-fallback",
        default="",
        help="Custom fallback string when --fallback custom is set",
    )
    parser.add_argument(
        "--delimiter", default=",", help="CSV field delimiter (default: ',')"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for date-format-standardizer."""
    parsed = parse_args(args)

    target_cols = [c.strip() for c in parsed.columns.split(",") if c.strip()]

    try:
        stats = standardize_csv_dates(
            input_file=parsed.input,
            output_file=parsed.output,
            target_columns=target_cols,
            day_first=parsed.day_first,
            to_utc=parsed.to_utc,
            include_time=parsed.include_time,
            fallback_strategy=parsed.fallback,
            custom_fallback=parsed.custom_fallback,
            delimiter=parsed.delimiter,
        )
        if parsed.output:
            print(f"Date Standardization Report for '{parsed.input}':")
            print(f"  Total rows           : {stats['total_rows']}")
            print(f"  Dates processed      : {stats['total_dates_processed']}")
            print(f"  Successfully parsed  : {stats['successfully_parsed']}")
            print(f"  Failed / Unparseable : {stats['failed_parses']}")
            print(f"Standardized CSV written to {parsed.output}")
    except (OSError, ValueError, csv.Error) as e:
        print(f"Error standardizing CSV dates: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
