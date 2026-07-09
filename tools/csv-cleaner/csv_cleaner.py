#!/usr/bin/env python3
"""CSV Cleaner.

Analyzes a CSV file to detect encoding, delimiter, duplicate rows,
malformed dates, empty/null columns, inconsistent headers, and type
mismatches. Generates a cleaned output CSV based on CLI configuration.
"""

# pylint: disable=import-error,too-many-instance-attributes,too-many-return-statements
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
# pylint: disable=too-many-arguments,too-many-positional-arguments
import argparse
import csv
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import chardet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # YYYY-MM-DD
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),  # DD/MM/YYYY or MM/DD/YYYY
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),  # DD-MM-YYYY
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),  # YYYY/MM/DD
    re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),  # ISO 8601 with time
]
NULL_VALUES: Set[str] = {"", "null", "none", "na", "n/a", "nan", "#n/a", "-"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ColumnStats:
    """Statistics for a single column.

    Attributes:
        name: Column header name.
        total: Total number of rows.
        null_count: Number of null/empty values.
        unique_count: Number of unique non-null values.
        detected_type: Inferred dominant type ('int', 'float', 'date',
            'bool', 'string').
        type_inconsistencies: Rows with values not matching the detected type.
    """

    name: str
    total: int = 0
    null_count: int = 0
    unique_count: int = 0
    detected_type: str = "string"
    type_inconsistencies: List[int] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """Full analysis report for a CSV file.

    Attributes:
        file_path: Input file path.
        encoding: Detected file encoding.
        delimiter: Detected delimiter character.
        total_rows: Total data rows (excluding header).
        header: Detected header row.
        duplicate_rows: Row indices of exact duplicates.
        empty_columns: Column names that are entirely empty.
        header_issues: Problems found in the header (e.g., blank names, duplicates).
        column_stats: Per-column statistics.
    """

    file_path: str
    encoding: str
    delimiter: str
    total_rows: int
    header: List[str]
    duplicate_rows: List[int] = field(default_factory=list)
    empty_columns: List[str] = field(default_factory=list)
    header_issues: List[str] = field(default_factory=list)
    column_stats: List[ColumnStats] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def detect_encoding(path: str) -> str:
    """Detect the character encoding of a file.

    Args:
        path: File path to inspect.

    Returns:
        Encoding name (e.g., 'utf-8', 'windows-1252').
    """
    with open(path, "rb") as fh:
        raw = fh.read(65536)
    result = chardet.detect(raw)
    return result.get("encoding") or "utf-8"


def detect_delimiter(sample: str) -> str:
    """Detect the most likely CSV delimiter from a text sample.

    Args:
        sample: First few lines of the CSV as a string.

    Returns:
        The delimiter character.
    """
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;:")
        return dialect.delimiter
    except csv.Error:
        return ","  # Default to comma


def is_null(value: str) -> bool:
    """Check if a cell value represents a null/empty value.

    Args:
        value: Raw cell string.

    Returns:
        True if the value is considered null.
    """
    return value.strip().lower() in NULL_VALUES


def infer_type(values: List[str]) -> str:
    """Infer the dominant type of a column from its non-null values.

    Args:
        values: List of non-null string values.

    Returns:
        Type string: 'int', 'float', 'date', 'bool', or 'string'.
    """
    if not values:
        return "string"

    bool_vals = {"true", "false", "yes", "no", "1", "0"}
    int_count = float_count = date_count = bool_count = 0

    for v in values:
        stripped = v.strip()
        if stripped.lower() in bool_vals:
            bool_count += 1
        try:
            int(stripped)
            int_count += 1
            continue
        except ValueError:
            pass
        try:
            float(stripped.replace(",", "."))
            float_count += 1
            continue
        except ValueError:
            pass
        if any(p.match(stripped) for p in DATE_PATTERNS):
            date_count += 1

    total = len(values)
    threshold = total * 0.8  # 80% majority

    if int_count >= threshold:
        return "int"
    if float_count >= threshold:
        return "float"
    if date_count >= threshold:
        return "date"
    if bool_count >= threshold:
        return "bool"
    return "string"


def matches_type(value: str, detected_type: str) -> bool:
    """Check if a value matches the detected column type.

    Args:
        value: Raw cell string.
        detected_type: Expected type.

    Returns:
        True if the value matches.
    """
    v = value.strip()
    if detected_type == "int":
        try:
            int(v)
            return True
        except ValueError:
            return False
    if detected_type == "float":
        try:
            float(v.replace(",", "."))
            return True
        except ValueError:
            return False
    if detected_type == "date":
        return any(p.match(v) for p in DATE_PATTERNS)
    if detected_type == "bool":
        return v.lower() in {"true", "false", "yes", "no", "1", "0"}
    return True  # string accepts anything


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_csv(path: str) -> Tuple[AnalysisReport, List[List[str]]]:
    """Analyze a CSV file and return a report and the parsed rows.

    Args:
        path: Path to the input CSV file.

    Returns:
        Tuple of (AnalysisReport, list of data rows).
    """
    encoding = detect_encoding(path)
    logger.info("Detected encoding: %s", encoding)

    with open(path, encoding=encoding, errors="replace", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delimiter = detect_delimiter(sample)
        logger.info("Detected delimiter: %r", delimiter)
        reader = csv.reader(fh, delimiter=delimiter)
        all_rows = list(reader)

    if not all_rows:
        logger.error("CSV file is empty.")
        sys.exit(1)

    header = all_rows[0]
    data_rows = all_rows[1:]

    report = AnalysisReport(
        file_path=path,
        encoding=encoding,
        delimiter=delimiter,
        total_rows=len(data_rows),
        header=header,
    )

    # Header analysis
    seen_headers: Dict[str, int] = {}
    for i, h in enumerate(header):
        stripped = h.strip()
        if not stripped:
            report.header_issues.append(f"Column {i}: blank header name")
        elif stripped in seen_headers:
            report.header_issues.append(
                f"Column {i}: duplicate header '{stripped}' "
                f"(also at index {seen_headers[stripped]})"
            )
        else:
            seen_headers[stripped] = i

    # Duplicate row detection (by full row fingerprint)
    row_fingerprints: Dict[Tuple[str, ...], List[int]] = {}
    for idx, row in enumerate(data_rows, start=2):  # 1-indexed, row 1 = header
        fp = tuple(row)
        row_fingerprints.setdefault(fp, []).append(idx)

    for fp, indices in row_fingerprints.items():
        if len(indices) > 1:
            report.duplicate_rows.extend(indices[1:])  # keep first, flag rest

    report.duplicate_rows.sort()

    # Per-column stats
    for col_idx, col_name in enumerate(header):
        stats = ColumnStats(
            name=col_name.strip() or f"col_{col_idx}", total=len(data_rows)
        )
        col_values: List[str] = []

        for row_idx, row in enumerate(data_rows, start=2):
            if col_idx >= len(row):
                stats.null_count += 1
                continue
            cell = row[col_idx]
            if is_null(cell):
                stats.null_count += 1
            else:
                col_values.append(cell)

        stats.unique_count = len(set(col_values))
        stats.detected_type = infer_type(col_values)

        # Type inconsistency check
        for row_idx, row in enumerate(data_rows, start=2):
            if col_idx >= len(row):
                continue
            cell = row[col_idx].strip()
            if not is_null(cell) and not matches_type(cell, stats.detected_type):
                stats.type_inconsistencies.append(row_idx)

        if stats.null_count == len(data_rows):
            report.empty_columns.append(stats.name)

        report.column_stats.append(stats)

    return report, data_rows


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(report: AnalysisReport) -> None:
    """Print a human-readable analysis report to stdout.

    Args:
        report: AnalysisReport to display.
    """
    print(f"\n{'=' * 65}")
    print("  CSV Cleaner — Analysis Report")
    print(f"  File      : {report.file_path}")
    print(f"  Encoding  : {report.encoding}")
    print(f"  Delimiter : {report.delimiter!r}")
    print(f"  Rows      : {report.total_rows}")
    print(f"  Columns   : {len(report.header)}")
    print(f"{'=' * 65}\n")

    # Header issues
    print("── Header Issues ─────────────────────────────────────────")
    if report.header_issues:
        for issue in report.header_issues:
            print(f"  ⚠  {issue}")
    else:
        print("  ✅ No header issues.")
    print()

    # Duplicates
    print("── Duplicate Rows ────────────────────────────────────────")
    if report.duplicate_rows:
        shown = report.duplicate_rows[:20]
        print(f"  ⚠  {len(report.duplicate_rows)} duplicate rows found.")
        print(f"     Row numbers (1-indexed, first 20): {shown}")
    else:
        print("  ✅ No duplicate rows.")
    print()

    # Empty columns
    print("── Empty Columns ─────────────────────────────────────────")
    if report.empty_columns:
        for col in report.empty_columns:
            print(f"  ⚠  '{col}' is entirely empty/null")
    else:
        print("  ✅ No fully empty columns.")
    print()

    # Column type analysis
    print("── Column Statistics ─────────────────────────────────────")
    header_fmt = (
        f"  {'Column':<25} {'Type':<8} {'Nulls':>6} {'Unique':>7} {'Type Issues':>11}"
    )
    print(header_fmt)
    print("  " + "-" * 62)
    for stats in report.column_stats:
        null_pct = f"{stats.null_count}/{stats.total}"
        issues = len(stats.type_inconsistencies)
        issue_str = f"{issues} rows" if issues else "✅"
        print(
            f"  {stats.name:<25} {stats.detected_type:<8} {null_pct:>6} "
            f"{stats.unique_count:>7} {issue_str:>11}"
        )
    print()


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


def clean_csv(
    report: AnalysisReport,
    data_rows: List[List[str]],
    output_path: str,
    drop_duplicates: bool,
    drop_empty_cols: bool,
    strip_whitespace: bool,
    normalize_nulls: bool,
) -> None:
    """Write a cleaned version of the CSV to disk.

    Args:
        report: AnalysisReport with analysis metadata.
        data_rows: Raw parsed data rows.
        output_path: Destination file path.
        drop_duplicates: Remove duplicate rows.
        drop_empty_cols: Remove fully empty columns.
        strip_whitespace: Strip leading/trailing whitespace from all cells.
        normalize_nulls: Replace all null variants with empty string.
    """
    header = report.header
    empty_col_indices: Set[int] = set()

    if drop_empty_cols:
        for i, col_name in enumerate(header):
            if (
                col_name.strip() in report.empty_columns
                or col_name in report.empty_columns
            ):
                empty_col_indices.add(i)

    dup_set: Set[int] = set(report.duplicate_rows) if drop_duplicates else set()

    clean_header = [h for i, h in enumerate(header) if i not in empty_col_indices]

    clean_rows: List[List[str]] = []

    for row_idx, row in enumerate(data_rows, start=2):
        if row_idx in dup_set:
            continue

        cleaned = []
        for col_idx, cell in enumerate(row):
            if col_idx in empty_col_indices:
                continue
            v = cell.strip() if strip_whitespace else cell
            if normalize_nulls and is_null(v):
                v = ""
            cleaned.append(v)

        clean_rows.append(cleaned)

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(clean_header)
        writer.writerows(clean_rows)

    print(
        f"✅ Cleaned CSV saved to '{output_path}' ({len(clean_rows)} rows, "
        f"{len(clean_header)} columns)."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="CSV Cleaner — analyze and clean CSV files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a CSV file
  python csv_cleaner.py --input data.csv

  # Analyze and write a cleaned version
  python csv_cleaner.py --input data.csv --output clean.csv

  # Drop duplicates and empty columns, strip whitespace
  python csv_cleaner.py --input data.csv --output clean.csv \\
                        --drop-duplicates --drop-empty-cols --strip

  # Normalize null values and fix encoding
  python csv_cleaner.py --input data.csv --output clean.csv --normalize-nulls
""",
    )
    parser.add_argument(
        "--input", required=True, metavar="FILE", help="Input CSV file path."
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Output cleaned CSV file (analysis-only if omitted).",
    )
    parser.add_argument(
        "--drop-duplicates",
        action="store_true",
        help="Remove duplicate rows from output.",
    )
    parser.add_argument(
        "--drop-empty-cols",
        action="store_true",
        help="Remove entirely empty/null columns from output.",
    )
    parser.add_argument(
        "--strip",
        action="store_true",
        help="Strip leading/trailing whitespace from all cell values.",
    )
    parser.add_argument(
        "--normalize-nulls",
        action="store_true",
        help="Normalize all null variants (null, NA, N/A, etc.) to empty string.",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit code 1 if any data quality issues are found.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    report, data_rows = analyze_csv(input_path)
    print_report(report)

    if args.output:
        output_path = os.path.abspath(args.output)
        clean_csv(
            report=report,
            data_rows=data_rows,
            output_path=output_path,
            drop_duplicates=args.drop_duplicates,
            drop_empty_cols=args.drop_empty_cols,
            strip_whitespace=args.strip,
            normalize_nulls=args.normalize_nulls,
        )

    if args.fail_on_issues:
        total_issues = (
            len(report.header_issues)
            + len(report.duplicate_rows)
            + len(report.empty_columns)
            + sum(len(s.type_inconsistencies) for s in report.column_stats)
        )
        if total_issues > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
