"""Currency Normalizer CLI Tool.

Normalizes mixed currency strings (e.g., "$1,234.50", "€1.234,50", "¥5000",
"1234.5 USD", "(£500.25)", "-$50.00") into standardized decimal float numbers
and ISO 4217 currency codes.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mapping from currency symbols to ISO 4217 currency codes
SYMBOL_TO_ISO: Dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "C$": "CAD",
    "A$": "AUD",
    "R$": "BRL",
    "kr": "SEK",
    "zł": "PLN",
    "Fr": "CHF",
    "₩": "KRW",
    "₱": "PHP",
    "฿": "THB",
    "₫": "VND",
    "Ξ": "ETH",
    "₿": "BTC",
}

# Regex to match 3-letter ISO currency codes
ISO_CODE_REGEX = re.compile(r"\b([A-Z]{3})\b")


def extract_currency_code(text: str, default_currency: str = "USD") -> Tuple[str, str]:
    """Extract currency code or symbol from string and strip code/symbol.

    Args:
        text: Raw currency string input.
        default_currency: Fallback ISO code if no symbol or code found.

    Returns:
        Tuple of (clean_text_without_currency_code, ISO_code).
    """
    cleaned_text = text.strip()
    detected_code = None

    # Check multi-char symbols first (e.g., C$, A$, R$)
    sorted_symbols = sorted(
        SYMBOL_TO_ISO.items(), key=lambda x: len(x[0]), reverse=True
    )
    for symbol, code in sorted_symbols:
        if symbol in cleaned_text:
            detected_code = code
            cleaned_text = cleaned_text.replace(symbol, "")
            break

    # Check 3-letter ISO code if not found via symbol
    if not detected_code:
        iso_match = ISO_CODE_REGEX.search(cleaned_text.upper())
        if iso_match:
            detected_code = iso_match.group(1)
            pat = r"\b" + detected_code + r"\b"
            cleaned_text = re.sub(pat, "", cleaned_text, flags=re.IGNORECASE)

    if not detected_code:
        detected_code = default_currency.upper()

    return cleaned_text.strip(), detected_code


def parse_currency_amount(raw_val: str) -> Optional[float]:
    """Parse numeric currency amount from string, handling separators.

    Args:
        raw_val: Numeric portion of currency string (without symbol/code).

    Returns:
        Parsed float value or None if invalid.
    """
    if not raw_val:
        return None

    text = raw_val.strip()

    # Check negative in parentheses, e.g. (1,234.50) -> -1,234.50
    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1].strip()
    elif text.startswith("-") or text.startswith("–") or text.startswith("—"):
        is_negative = True
        text = text.lstrip("-–—").strip()

    # Remove whitespace / non-breaking space used as thousands separator
    text = re.sub(r"\s+", "", text)

    # Determine decimal vs thousands separators
    if "." in text and "," in text:
        dot_idx = text.find(".")
        comma_idx = text.find(",")
        if dot_idx < comma_idx:
            # European format: 1.234,50 -> dot is thousands, comma is decimal
            text = text.replace(".", "").replace(",", ".")
        else:
            # Standard format: 1,234.50 -> comma is thousands, dot is decimal
            text = text.replace(",", "")
    elif "," in text and "." not in text:
        comma_idx = text.rfind(",")
        digits_after_comma = len(text) - comma_idx - 1
        if digits_after_comma in (1, 2):
            # Comma as decimal separator: 1234,50 -> 1234.50
            text = text.replace(",", ".")
        else:
            # Comma as thousands separator: 1,234 -> 1234
            text = text.replace(",", "")

    # Extract clean number string (digits, sign, single dot)
    num_match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not num_match:
        return None

    try:
        val = float(num_match.group(0))
        return -val if is_negative else val
    except ValueError:
        return None


def normalize_currency_entry(
    raw_entry: str, default_currency: str = "USD"
) -> Tuple[Optional[float], str, str]:
    """Normalize a single currency string entry.

    Args:
        raw_entry: Raw currency string.
        default_currency: Default ISO currency code.

    Returns:
        Tuple of (normalized_float_amount, currency_code, status).
        Status is one of 'SUCCESS', 'EMPTY', 'FAILED'.
    """
    if not raw_entry or not raw_entry.strip():
        return None, default_currency.upper(), "EMPTY"

    numeric_part, currency_code = extract_currency_code(raw_entry, default_currency)
    amount = parse_currency_amount(numeric_part)

    if amount is None:
        return None, currency_code, "FAILED"

    return amount, currency_code, "SUCCESS"


def process_currency_csv(
    input_file: Path,
    output_file: Path,
    currency_column: str,
    default_currency: str = "USD",
    output_amount_col: str = "normalized_amount",
    output_code_col: str = "currency_code",
    output_status_col: str = "normalization_status",
) -> Tuple[int, int, int]:
    """Process CSV file normalizing currency column values.

    Args:
        input_file: Input CSV filepath.
        output_file: Output CSV filepath.
        currency_column: Name or 0-indexed position of currency column.
        default_currency: Fallback ISO currency code.
        output_amount_col: Name for normalized amount column.
        output_code_col: Name for currency ISO code column.
        output_status_col: Name for normalization status column.

    Returns:
        Tuple of (success_count, failed_count, empty_count).
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

    if currency_column.isdigit():
        col_idx = int(currency_column)
    elif currency_column in header:
        col_idx = header.index(currency_column)
    else:
        for idx, col in enumerate(header):
            if col.strip().lower() == currency_column.strip().lower():
                col_idx = idx
                break

    if col_idx < 0 or col_idx >= len(header):
        err = f"Currency column '{currency_column}' not found in " f"header: {header}"
        raise ValueError(err)

    new_header = list(header)
    new_header.extend([output_amount_col, output_code_col, output_status_col])

    success_count = 0
    failed_count = 0
    empty_count = 0

    output_rows = [new_header]

    for row in rows[1:]:
        if not row:
            continue
        raw_val = row[col_idx] if col_idx < len(row) else ""
        amount, code, status = normalize_currency_entry(raw_val, default_currency)

        if status == "SUCCESS":
            success_count += 1
            amount_str = f"{amount:.2f}"
        elif status == "FAILED":
            failed_count += 1
            amount_str = ""
        else:
            empty_count += 1
            amount_str = ""

        new_row = list(row)
        while len(new_row) < len(header):
            new_row.append("")
        new_row.extend([amount_str, code, status])
        output_rows.append(new_row)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(output_rows)

    return success_count, failed_count, empty_count


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    desc = "Normalizes mixed currency strings into standardized decimal numbers."
    parser = argparse.ArgumentParser(description=desc)
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
        help="Currency column header name or 0-indexed position",
    )
    parser.add_argument(
        "--default-currency",
        default="USD",
        help="Fallback ISO currency code if symbol missing. Default: 'USD'",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint for currency-normalizer."""
    parsed = parse_args(args)
    try:
        success, failed, empty = process_currency_csv(
            input_file=parsed.input_file,
            output_file=parsed.output_file,
            currency_column=parsed.column,
            default_currency=parsed.default_currency,
        )
        print("Currency normalization complete.")
        print(f"  Successfully normalized: {success}")
        print(f"  Failed entries: {failed}")
        print(f"  Empty entries: {empty}")
        print(f"Output written to: {parsed.output_file}")
    except (OSError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
