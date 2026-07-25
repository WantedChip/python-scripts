"""Phone Number Formatter CLI Tool.

Standardizes phone numbers in CSV columns to E.164 format (+14155552671)
or custom display formats (national, international, digits-only). Adds format
validation and tags valid/invalid entries in output CSV.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mapping of common country ISO codes / aliases to E.164 country call codes
COUNTRY_CALL_CODES: Dict[str, str] = {
    "US": "1",
    "CA": "1",
    "UK": "44",
    "GB": "44",
    "IN": "91",
    "DE": "49",
    "FR": "33",
    "AU": "61",
    "JP": "81",
    "CN": "86",
    "BR": "55",
    "MX": "52",
    "ES": "34",
    "IT": "39",
    "NL": "31",
    "SE": "46",
    "CH": "41",
    "NZ": "64",
    "SG": "65",
}

# Regex patterns for parsing extensions and digits
EXTENSION_PATTERN = re.compile(r"(?:ext|x|extension|#)\s*\.?\s*(\d+)", re.IGNORECASE)
NON_DIGIT_PLUS_PATTERN = re.compile(r"[^\d+]")


def normalize_country_code(country_input: str) -> str:
    """Normalize input country code or name to numerical call code string.

    Args:
        country_input: Country code string, e.g. "US", "+1", "1", "44", "UK".

    Returns:
        Call code string without leading plus, e.g. "1" or "44".
    """
    cleaned = country_input.strip().upper().lstrip("+")
    if cleaned in COUNTRY_CALL_CODES:
        return COUNTRY_CALL_CODES[cleaned]
    if cleaned.isdigit():
        return cleaned
    return "1"  # Fallback default to 1 (NANP)


def extract_phone_components(
    raw_phone: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Extract digits and optional extension from raw phone input.

    Args:
        raw_phone: Input string containing phone number.

    Returns:
        Tuple of (cleaned_phone_str, extension_str).
    """
    if not raw_phone or not raw_phone.strip():
        return None, None

    text = raw_phone.strip()

    # Extract extension if present
    ext_match = EXTENSION_PATTERN.search(text)
    extension = ext_match.group(1) if ext_match else None
    if ext_match:
        text = text[: ext_match.start()]

    # Strip unwanted characters keeping digits and leading '+'
    has_leading_plus = text.startswith("+") or text.startswith("00")
    if text.startswith("00"):
        text = "+" + text[2:]

    cleaned = NON_DIGIT_PLUS_PATTERN.sub("", text)
    if has_leading_plus and not cleaned.startswith("+"):
        cleaned = "+" + cleaned.lstrip("+")

    return (cleaned if cleaned else None), extension


def validate_and_format_phone(
    raw_phone: str,
    default_country_code: str = "1",
    target_format: str = "e164",
) -> Tuple[str, str, Optional[str]]:
    """Validate and format a single phone number into specified target format.

    Args:
        raw_phone: Raw phone string input.
        default_country_code: Default numerical country code if none found.
        target_format: Format mode: 'e164', 'international', 'national', ...

    Returns:
        Tuple of (formatted_phone, status, extension).
        Status is one of 'VALID', 'INVALID', 'EMPTY'.
    """
    cleaned_phone, extension = extract_phone_components(raw_phone)
    if not cleaned_phone:
        return "", "EMPTY", None

    country_code = normalize_country_code(default_country_code)

    # Determine full phone number with country code
    if cleaned_phone.startswith("+"):
        full_digits = cleaned_phone[1:]
    else:
        # If starts with '0' trunk prefix in local formats (e.g. UK 020 1234 5678)
        local_digits = cleaned_phone
        if local_digits.startswith("0") and country_code != "1":
            local_digits = local_digits[1:]
        full_digits = country_code + local_digits

    # Validate digit count according to E.164 rules (7 to 15 digits total)
    if not full_digits.isdigit() or len(full_digits) < 7 or len(full_digits) > 15:
        return cleaned_phone, "INVALID", extension

    e164_formatted = f"+{full_digits}"

    # Format according to target format
    if target_format == "e164":
        formatted = e164_formatted
    elif target_format == "digits_only":
        formatted = full_digits
    elif target_format == "national":
        if full_digits.startswith("1") and len(full_digits) == 11:
            # NANP standard format (415) 555-2671
            area = full_digits[1:4]
            prefix = full_digits[4:7]
            line = full_digits[7:11]
            formatted = f"({area}) {prefix}-{line}"
        else:
            formatted = full_digits
    elif target_format == "international":
        if full_digits.startswith("1") and len(full_digits) == 11:
            area = full_digits[1:4]
            prefix = full_digits[4:7]
            line = full_digits[7:11]
            formatted = f"+1 {area}-{prefix}-{line}"
        else:
            formatted = e164_formatted
    else:
        formatted = e164_formatted

    return formatted, "VALID", extension


def process_csv_file(
    input_file: Path,
    output_file: Path,
    phone_column: str,
    default_country: str = "US",
    target_format: str = "e164",
    output_column: str = "formatted_phone",
    status_column: str = "phone_status",
) -> Tuple[int, int, int]:
    """Read CSV, standardize phone numbers, and write processed CSV.

    Args:
        input_file: Input CSV filepath.
        output_file: Output CSV filepath.
        phone_column: Name or 0-indexed column index of the phone field.
        default_country: Default country prefix or code.
        target_format: Formatting mode.
        output_column: Column name to store formatted phone numbers.
        status_column: Column name to store validation status.

    Returns:
        Tuple of (valid_count, invalid_count, empty_count).
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file non-existent: {input_file}")

    with input_file.open("r", encoding="utf-8-sig", newline="") as infile:
        reader = csv.reader(infile)
        rows = list(reader)

    if not rows:
        raise ValueError("Input CSV file is empty.")

    header = rows[0]
    col_idx = -1

    if phone_column.isdigit():
        col_idx = int(phone_column)
    elif phone_column in header:
        col_idx = header.index(phone_column)
    else:
        # Try case-insensitive search
        for idx, col in enumerate(header):
            if col.strip().lower() == phone_column.strip().lower():
                col_idx = idx
                break

    if col_idx < 0 or col_idx >= len(header):
        msg = f"Phone column '{phone_column}' not found in CSV header: {header}"
        raise ValueError(msg)

    # Build new header
    new_header = list(header)
    new_header.extend([output_column, status_column])

    valid_count = 0
    invalid_count = 0
    empty_count = 0

    output_rows = [new_header]

    for row in rows[1:]:
        if not row:
            continue
        raw_val = row[col_idx] if col_idx < len(row) else ""
        formatted, status, ext = validate_and_format_phone(
            raw_val,
            default_country_code=default_country,
            target_format=target_format,
        )

        if ext and status == "VALID":
            formatted_with_ext = f"{formatted} ext. {ext}"
        else:
            formatted_with_ext = formatted

        if status == "VALID":
            valid_count += 1
        elif status == "INVALID":
            invalid_count += 1
        else:
            empty_count += 1

        new_row = list(row)
        # Pad row if missing columns
        while len(new_row) < len(header):
            new_row.append("")
        new_row.extend([formatted_with_ext, status])
        output_rows.append(new_row)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(output_rows)

    return valid_count, invalid_count, empty_count


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Standardizes and validates phone numbers in CSV files."
    )
    parser.add_argument(
        "-i",
        "--input-file",
        required=True,
        type=Path,
        help="Path to input CSV file",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        required=True,
        type=Path,
        help="Path to output CSV file",
    )
    parser.add_argument(
        "-c",
        "--column",
        required=True,
        help="Phone column name or 0-indexed position in CSV",
    )
    parser.add_argument(
        "--default-country",
        default="US",
        help="Default country code or ISO (e.g. 'US', 'UK', '+1'). Default: 'US'",
    )
    parser.add_argument(
        "--format",
        choices=["e164", "international", "national", "digits_only"],
        default="e164",
        help="Target display format. Default: 'e164'",
    )
    parser.add_argument(
        "--output-column",
        default="formatted_phone",
        help="Column header name for formatted output.",
    )
    parser.add_argument(
        "--status-column",
        default="phone_status",
        help="Column header name for validation status.",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point for phone-number-formatter."""
    parsed_args = parse_args(args)
    try:
        valid, invalid, empty = process_csv_file(
            input_file=parsed_args.input_file,
            output_file=parsed_args.output_file,
            phone_column=parsed_args.column,
            default_country=parsed_args.default_country,
            target_format=parsed_args.format,
            output_column=parsed_args.output_column,
            status_column=parsed_args.status_column,
        )
        print("Processing complete.")
        print(f"Valid numbers: {valid}")
        print(f"Invalid numbers: {invalid}")
        print(f"Empty entries: {empty}")
        print(f"Output saved to: {parsed_args.output_file}")
    except (OSError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
