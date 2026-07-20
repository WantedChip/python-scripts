#!/usr/bin/env python3
"""CSV Autopsy.

Scans and diagnoses broken or structurally malformed CSV files.
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple


def sniff_encoding_details(file_path: str) -> Tuple[str, List[str]]:
    """Sniff file encoding and check for decode errors/mixed encodings."""
    encodings_to_test = [
        ("utf-8-sig", "UTF-8 with BOM"),
        ("utf-8", "UTF-8"),
        ("windows-1252", "Windows-1252 / Western Europe"),
        ("utf-16", "UTF-16"),
        ("latin-1", "Latin-1"),
    ]

    issues: List[str] = []

    # Try reading as binary first
    try:
        with open(file_path, "rb") as f:
            raw_bytes = f.read(50000)  # Read initial chunk
    except OSError as e:
        return "unknown", [f"OS error reading file: {e}"]

    # Detect BOMs manually
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", ["Info: Detected UTF-8 BOM signature"]
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", ["Info: Detected UTF-16 BOM signature"]

    # Sniff encoding by testing full decode
    valid_encoding = None
    for enc, _ in encodings_to_test:
        try:
            with open(file_path, "r", encoding=enc) as f:
                # Read entire file or iterate to trigger any decode errors
                for _ in f:
                    pass
            valid_encoding = enc
            break
        except UnicodeDecodeError:
            continue

    if valid_encoding is None:
        # File has mixed encoding/corrupted bytes
        valid_encoding = "latin-1"  # Latin-1 decodes any byte stream
        issues.append(
            "Warning: Mixed encodings or corrupted binary data detected. "
            "File could not be parsed as clean UTF-8."
        )

        # Locate non-UTF-8 bytes
        try:
            with open(file_path, "rb") as f:
                for idx, line in enumerate(f, 1):
                    try:
                        line.decode("utf-8")
                    except UnicodeDecodeError as ue:
                        bad_slice = line[ue.start : ue.end]  # noqa: E203
                        issues.append(
                            f"Row {idx}: Invalid UTF-8 bytes found at position "
                            f"{ue.start}-{ue.end}: {bad_slice!r}"
                        )
        except OSError:
            pass
    else:
        issues.append(f"Success: Decoded successfully as clean {valid_encoding}")

    return valid_encoding, issues


# pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks  # noqa: E501
def scan_csv_structure(
    file_path: str, encoding: str
) -> Tuple[List[str], Dict[str, Any]]:
    """Scan CSV row-by-row and analyze columns, quotes, and control chars."""
    issues: List[str] = []
    header: List[str] = []
    rows_count = 0
    column_counts: List[int] = []
    row_details: List[List[str]] = []

    # Pre-check for raw delimiter sniffing
    delimiter = ","
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            sample = f.read(4096)
            if sample:
                # Sniff delimiter
                counts = {
                    ",": sample.count(","),
                    ";": sample.count(";"),
                    "\t": sample.count("\t"),
                    "|": sample.count("|"),
                }
                best_delim = max(counts, key=lambda k: counts[k])
                if counts[best_delim] > 0:
                    delimiter = best_delim
    except OSError:
        pass

    # Read line-by-line character audit for quoting anomalies
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            in_quote = False
            quote_char = '"'
            for line_num, line in enumerate(f, 1):
                # Count invisible characters
                for col_num, char in enumerate(line, 1):
                    # Zero width space, null bytes, control characters
                    if char == "\x00":
                        issues.append(
                            f"Row {line_num}, Column {col_num}: Null byte character "
                            "(\\x00) detected."
                        )
                    elif char == "\u200b":
                        issues.append(
                            f"Row {line_num}, Column {col_num}: Zero-width space "
                            "character (\\u200b) detected."
                        )
                    elif ord(char) < 32 and char not in ("\t", "\r", "\n"):
                        issues.append(
                            f"Row {line_num}, Column {col_num}: Invisible control "
                            f"character (ASCII {ord(char)}) detected."
                        )

                # Quoting audit
                for idx, char in enumerate(line):
                    if char == quote_char:
                        if not in_quote:
                            # Quote opens. Check if it is preceded by delimiter/newline
                            if idx > 0 and line[idx - 1] not in (
                                delimiter,
                                " ",
                                "\t",
                                "\r",
                                "\n",
                            ):
                                issues.append(
                                    f"Row {line_num}, Char {idx+1}: Quoting error. "
                                    "Double quote found in middle of unquoted field."
                                )
                            in_quote = True
                        else:
                            # Quote closes or is escaped
                            if idx + 1 < len(line) and line[idx + 1] == quote_char:
                                # Escaped quote inside string, skip next quote
                                in_quote = True
                            else:
                                in_quote = False
                                # Quote closed. Check if followed by delimiter/newline
                                if idx + 1 < len(line) and line[idx + 1] not in (
                                    delimiter,
                                    " ",
                                    "\t",
                                    "\r",
                                    "\n",
                                    "\x00",
                                ):
                                    issues.append(
                                        f"Row {line_num}, Char {idx+2}: Quoting "
                                        "error. Double quote closed but not "
                                        "followed by delimiter."
                                    )

            if in_quote:
                issues.append(
                    "Warning: Unclosed double-quotes detected at the end of the file."
                )
    except OSError as e:
        issues.append(f"OS error reading file during character scan: {e}")

    # Read using standard CSV reader to analyze columns consistency
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)

            # Read header
            try:
                header = next(reader)
                rows_count += 1
            except StopIteration:
                issues.append("Error: CSV file is empty.")
                return issues, {}
            except csv.Error as ce:
                issues.append(f"Header parsing failed: {ce}")
                return issues, {}

            # Audit duplicate headers
            if header:
                seen_headers: Set[str] = set()
                dups = []
                for h in header:
                    h_clean = h.strip()
                    if h_clean in seen_headers:
                        dups.append(h_clean)
                    seen_headers.add(h_clean)
                if dups:
                    dup_names = ", ".join(set(dups))
                    issues.append(
                        f"Row 1 (Header): Duplicate columns names found: {dup_names}"
                    )

            expected_cols = len(header)

            for line_num, row in enumerate(reader, 2):
                rows_count += 1
                column_counts.append(len(row))

                # Column consistency
                if len(row) != expected_cols:
                    issues.append(
                        f"Row {line_num}: Inconsistent column count. Expected "
                        f"{expected_cols} fields but got {len(row)} fields."
                    )

                row_details.append(row)

    except csv.Error as ce:
        issues.append(f"CSV structural reader error: {ce}")
    except OSError as e:
        issues.append(f"OS error reading file: {e}")

    # Analyze field data formats (dates & numbers)
    date_columns: List[int] = []
    numeric_columns: List[int] = []

    if header:
        # Sniff date/numeric column positions based on header naming
        date_indicators = ("date", "time", "created", "updated", "timestamp", "dt")
        num_indicators = (
            "amount",
            "price",
            "count",
            "id",
            "qty",
            "quantity",
            "cost",
            "total",
            "sum",
        )

        for idx, col in enumerate(header):
            col_lower = col.lower()
            if any(ind in col_lower for ind in date_indicators):
                date_columns.append(idx)
            if any(ind in col_lower for ind in num_indicators):
                numeric_columns.append(idx)

        # Audit Date formats in sniffed date columns
        for col_idx in date_columns:
            col_name = header[col_idx]
            formats = [
                "%Y-%m-%d",
                "%m/%d/%Y",
                "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d",
                "%d-%m-%Y",
                "%d.%m.%Y",
                "%I:%M:%S %p",
            ]
            format_counts: Counter[str] = Counter()
            unparseable_rows: List[Tuple[int, str]] = []

            for row_idx, row in enumerate(row_details, 2):
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    if not val:
                        continue  # Skip empty fields

                    matched_format = None
                    for fmt in formats:
                        try:
                            datetime.strptime(val, fmt)
                            matched_format = fmt
                            break
                        except ValueError:
                            continue

                    if matched_format:
                        format_counts[matched_format] += 1
                    else:
                        unparseable_rows.append((row_idx, val))

            # If there's more than one format in use, report schema drift
            if len(format_counts) > 1:
                formats_used = ", ".join(
                    f"'{f}' ({c} rows)" for f, c in format_counts.items()
                )
                issues.append(
                    f"Warning in column '{col_name}' (index {col_idx}): "
                    f"Inconsistent date formats. Multiple formats detected: "
                    f"{formats_used}."
                )

            # Report unparseable dates
            if unparseable_rows:
                # Limit print to top 5
                bad_vals = ", ".join(f"Row {r}: '{v}'" for r, v in unparseable_rows[:5])
                suffix = " ..." if len(unparseable_rows) > 5 else ""
                issues.append(
                    f"Warning in column '{col_name}': {len(unparseable_rows)} fields "
                    f"could not be parsed as date: {bad_vals}{suffix}"
                )

        # Audit Numeric formats in sniffed numeric columns
        for col_idx in numeric_columns:
            col_name = header[col_idx]
            bad_numeric_rows = []

            for row_idx, row in enumerate(row_details, 2):
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    if not val:
                        continue
                    # Check if numeric
                    val_clean = (
                        val.replace("$", "")
                        .replace("€", "")
                        .replace(",", "")
                        .replace("%", "")
                        .strip()
                    )
                    try:
                        float(val_clean)
                    except ValueError:
                        bad_numeric_rows.append((row_idx, val))

            if bad_numeric_rows:
                bad_vals = ", ".join(f"Row {r}: '{v}'" for r, v in bad_numeric_rows[:5])
                suffix = " ..." if len(bad_numeric_rows) > 5 else ""
                issues.append(
                    f"Warning in column '{col_name}' (index {col_idx}): "
                    f"Non-numeric values found in expected numeric column: "
                    f"{bad_vals}{suffix}"
                )

    metrics = {
        "rows_processed": rows_count,
        "columns_count": len(header) if header else 0,
        "delimiter": delimiter,
    }

    return issues, metrics


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Explain why a CSV file is broken, highlighting encoding, quoting, "
            "headers, column count, and formats."
        )
    )
    parser.add_argument("csv_file", help="Path to the CSV file to inspect.")

    args = parser.parse_args()

    # Step 1: Encoding autopsy
    encoding, encoding_issues = sniff_encoding_details(args.csv_file)

    # Step 2: Structure and content autopsy
    structure_issues, metrics = scan_csv_structure(args.csv_file, encoding)

    all_issues = encoding_issues + structure_issues

    # Print results
    print("========================================================================")
    print(f"CSV AUTOPSY REPORT: {args.csv_file}")
    print("========================================================================")
    print(f"Rows scanned:  {metrics.get('rows_processed', 0)}")
    print(f"Columns count: {metrics.get('columns_count', 0)}")
    print(f"Delimiter:     '{metrics.get('delimiter', ',')}'")
    print(f"Encoding:      {encoding}")
    print("------------------------------------------------------------------------")

    errors_found = 0
    warnings_found = 0

    for issue in all_issues:
        if "Success:" in issue or "Info:" in issue:
            print(f"[+] {issue}")
        elif "Warning:" in issue or "Warning in" in issue:
            print(f"[!] {issue}")
            warnings_found += 1
        else:
            print(f"[-] {issue}")
            errors_found += 1

    print("------------------------------------------------------------------------")
    print(f"Autopsy Summary: {errors_found} errors, {warnings_found} warnings.")

    if errors_found > 0:
        print("[FAIL] CSV is broken or structurally malformed.")
        sys.exit(1)
    else:
        print("[PASS] CSV structure is healthy.")
        sys.exit(0)


if __name__ == "__main__":
    main()
