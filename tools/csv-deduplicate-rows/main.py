"""CSV Deduplicate Rows Tool.

Removes duplicate rows from CSV files based on specified key columns,
retaining the first or last occurrence. Supports case-insensitivity,
fuzzy string matching, and outputs deduplication statistics.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import csv
import sys
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, TextIO, Tuple


def get_row_key(
    row: Dict[str, str], key_cols: List[str], ignore_case: bool = False
) -> Tuple[str, ...]:
    """Extracts the key tuple for a CSV row based on target columns.

    :param row: Row dict from csv.DictReader.
    :param key_cols: Target column names to form key.
    :param ignore_case: If True, convert string key values to lower-case.
    :return: Tuple of key values.
    """
    if not key_cols:
        keys = tuple(row.values())
    else:
        keys = tuple(row.get(col, "") for col in key_cols)

    if ignore_case:
        keys = tuple(k.strip().lower() if isinstance(k, str) else k for k in keys)
    else:
        keys = tuple(k.strip() if isinstance(k, str) else k for k in keys)

    return keys


def is_fuzzy_match(key_str: str, seen_key_strings: List[str], threshold: float) -> bool:
    """Checks if a key string fuzzy matches any previously seen key string.

    :param key_str: Key string of current row.
    :param seen_key_strings: List of seen key strings.
    :param threshold: Similarity ratio threshold (0.0 to 1.0).
    :return: True if fuzzy match found, False otherwise.
    """
    for seen in seen_key_strings:
        ratio = SequenceMatcher(None, key_str, seen).ratio()
        if ratio >= threshold:
            return True
    return False


def deduplicate_csv(
    input_file: str,
    output_file: Optional[str],
    key_cols: Optional[List[str]] = None,
    keep: str = "first",
    ignore_case: bool = False,
    fuzzy_threshold: Optional[float] = None,
    delimiter: str = ",",
) -> Dict[str, Any]:
    """Deduplicates rows in a CSV file.

    :param input_file: Path to input CSV file.
    :param output_file: Path to output CSV file (or stdout if None).
    :param key_cols: List of column header names to group by for uniqueness.
    :param keep: Retention strategy ('first' or 'last').
    :param ignore_case: Ignore case during string comparison.
    :param fuzzy_threshold: Float threshold for fuzzy string matching.
    :param delimiter: CSV delimiter.
    :return: Statistics dictionary (total_rows, retained_rows, removed_rows).
    """
    if key_cols is None:
        key_cols = []

    with open(input_file, mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    total_rows = len(rows)
    if total_rows == 0:
        return {"total_rows": 0, "retained_rows": 0, "removed_rows": 0}

    # Validate key columns exist
    if key_cols:
        for k in key_cols:
            if k not in fieldnames:
                err = (
                    f"Specified key column '{k}' not found in CSV headers: "
                    f"{fieldnames}"
                )
                raise ValueError(err)

    retained_rows: List[Dict[str, str]] = []

    if keep == "first":
        seen_exact_keys: Set[Tuple[str, ...]] = set()
        seen_fuzzy_strings: List[str] = []

        for row in rows:
            key_tuple = get_row_key(row, key_cols, ignore_case=ignore_case)

            if fuzzy_threshold is not None and fuzzy_threshold < 1.0:
                composite_key = " | ".join(str(k) for k in key_tuple)
                if is_fuzzy_match(composite_key, seen_fuzzy_strings, fuzzy_threshold):
                    continue
                seen_fuzzy_strings.append(composite_key)
                retained_rows.append(row)
            else:
                if key_tuple in seen_exact_keys:
                    continue
                seen_exact_keys.add(key_tuple)
                retained_rows.append(row)

    elif keep == "last":
        # Process in reverse to retain last occurrence, then preserve order
        seen_exact_keys_last: Set[Tuple[str, ...]] = set()
        seen_fuzzy_strings_last: List[str] = []
        temp_retained = []

        for row in reversed(rows):
            key_tuple = get_row_key(row, key_cols, ignore_case=ignore_case)

            if fuzzy_threshold is not None and fuzzy_threshold < 1.0:
                composite_key = " | ".join(str(k) for k in key_tuple)
                if is_fuzzy_match(
                    composite_key, seen_fuzzy_strings_last, fuzzy_threshold
                ):
                    continue
                seen_fuzzy_strings_last.append(composite_key)
                temp_retained.append(row)
            else:
                if key_tuple in seen_exact_keys_last:
                    continue
                seen_exact_keys_last.add(key_tuple)
                temp_retained.append(row)

        retained_rows = list(reversed(temp_retained))

    else:
        err = f"Invalid keep option '{keep}'. Must be 'first' or 'last'."
        raise ValueError(err)

    # Output writing
    def write_output(out_stream: TextIO) -> None:
        writer = csv.DictWriter(out_stream, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(retained_rows)

    if output_file:
        with open(output_file, mode="w", newline="", encoding="utf-8") as f_out:
            write_output(f_out)
    else:
        write_output(sys.stdout)

    removed_count = total_rows - len(retained_rows)
    return {
        "total_rows": total_rows,
        "retained_rows": len(retained_rows),
        "removed_rows": removed_count,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Deduplicate CSV rows based on key columns."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--input", "-i", required=True, help="Input CSV file path")
    parser.add_argument(
        "--output",
        "-o",
        help="Output CSV file path (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--keys",
        "-k",
        help="Comma-separated key columns (default: all columns)",
    )
    parser.add_argument(
        "--keep",
        choices=["first", "last"],
        default="first",
        help="Which occurrence to retain (default: first)",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Perform case-insensitive deduplication",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        help="Similarity threshold for fuzzy matching (0.0 to 1.0)",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="CSV field delimiter (default: ',')",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for csv-deduplicate-rows."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.keys:
        key_cols = [k.strip() for k in parsed.keys.split(",") if k.strip()]
    else:
        key_cols = []

    try:
        stats = deduplicate_csv(
            input_file=parsed.input,
            output_file=parsed.output,
            key_cols=key_cols,
            keep=parsed.keep,
            ignore_case=parsed.ignore_case,
            fuzzy_threshold=parsed.fuzzy_threshold,
            delimiter=parsed.delimiter,
        )
        if parsed.output:
            print(f"Deduplication Summary for '{parsed.input}':")
            print(f"  Total input rows  : {stats['total_rows']}")
            print(f"  Retained rows     : {stats['retained_rows']}")
            print(f"  Removed duplicates: {stats['removed_rows']}")
            print(f"Output saved to {parsed.output}")
    except (OSError, ValueError, csv.Error) as e:
        print(f"Error deduplicating CSV: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
