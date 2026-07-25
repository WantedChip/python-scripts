"""CSV Forensics CLI Tool.

Performs deep structural and forensic inspection of CSV files to detect
encoding defects, control characters, broken quoting, header issues, and
Excel-induced data corruptions.
"""

# pylint: disable=too-many-branches,too-many-locals,too-many-statements
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Regex patterns for forensic analysis
SCIENTIFIC_NOTATION_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?[eE][+-]?\d+$")
EXCEL_ERROR_PATTERN = re.compile(
    r"^#(?:VALUE|REF|N/A|NAME\?|NUM!|DIV/0!|NULL!)$", re.IGNORECASE
)

INVISIBLE_CHARS = {
    "\u200b": "Zero-width space (U+200B)",
    "\ufeff": "Byte Order Mark / Zero-width no-break space (U+FEFF)",
    "\u200c": "Zero-width non-joiner (U+200C)",
    "\u200d": "Zero-width joiner (U+200D)",
    "\u00a0": "Non-breaking space (U+00A0)",
    "\u00ad": "Soft hyphen (U+00AD)",
    "\x00": "Null byte (U+0000)",
}


@dataclass
class ForensicIssue:
    """Structure representing a single diagnostic issue found in CSV."""

    category: str
    severity: str  # ERROR, WARNING, INFO
    line_number: Optional[int]
    column: Optional[Union[int, str]]
    message: str
    sample_value: Optional[str] = None


def detect_encoding_and_bom(
    raw_bytes: bytes,
) -> Tuple[str, Optional[str], List[ForensicIssue]]:
    """Detect encoding, Byte-Order Mark (BOM), and encoding defects.

    Args:
        raw_bytes: Raw binary content of the CSV file.

    Returns:
        Tuple of (detected_encoding, bom_type, list_of_issues).
    """
    issues: List[ForensicIssue] = []
    bom = None
    encoding = "utf-8"

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        bom = "UTF-8-BOM"
        encoding = "utf-8-sig"
        issues.append(
            ForensicIssue(
                category="ENCODING",
                severity="INFO",
                line_number=1,
                column=1,
                message="UTF-8 Byte Order Mark (BOM) detected.",
            )
        )
    elif raw_bytes.startswith(b"\xfe\xff"):
        bom = "UTF-16-BE"
        encoding = "utf-16-be"
        issues.append(
            ForensicIssue(
                category="ENCODING",
                severity="WARNING",
                line_number=1,
                column=1,
                message="UTF-16 Big-Endian BOM detected.",
            )
        )
    elif raw_bytes.startswith(b"\xff\xfe"):
        bom = "UTF-16-LE"
        encoding = "utf-16-le"
        issues.append(
            ForensicIssue(
                category="ENCODING",
                severity="WARNING",
                line_number=1,
                column=1,
                message="UTF-16 Little-Endian BOM detected.",
            )
        )

    # Test UTF-8 decoding
    try:
        raw_bytes.decode(encoding)
    except UnicodeDecodeError as err:
        issues.append(
            ForensicIssue(
                category="ENCODING",
                severity="ERROR",
                line_number=None,
                column=None,
                message=(
                    f"File contains non-{encoding.upper()} invalid byte "
                    f"sequences: {err}"
                ),
            )
        )
        encoding = "latin-1"  # Fallback decode for safe inspection

    return encoding, bom, issues


def detect_delimiter(sample_text: str) -> Tuple[str, List[ForensicIssue]]:
    """Auto-detect CSV column delimiter using python csv.Sniffer or fallback.

    Args:
        sample_text: Text snippet from start of CSV file.

    Returns:
        Tuple of (delimiter_char, list_of_issues).
    """
    issues: List[ForensicIssue] = []
    delimiters = [",", "\t", ";", "|"]

    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample_text, delimiters=",\t;|")
        return dialect.delimiter, issues
    except Exception:  # pylint: disable=broad-exception-caught
        counts: Dict[str, int] = {d: sample_text.count(d) for d in delimiters}
        has_vals = any(counts.values())
        best_delim = max(counts, key=lambda k: counts[k]) if has_vals else ","
        issues.append(
            ForensicIssue(
                category="DELIMITER",
                severity="WARNING",
                line_number=None,
                column=None,
                message=(
                    f"Auto-detection heuristic selected '{best_delim}' "
                    "(Sniffer failed)."
                ),
            )
        )
        return best_delim, issues


def check_invisible_and_control_chars(text: str) -> List[ForensicIssue]:
    """Scan text lines for invisible, zero-width, or control characters.

    Args:
        text: Entire CSV content string.

    Returns:
        List of ForensicIssue objects.
    """
    issues: List[ForensicIssue] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, 1):
        for char_idx, char in enumerate(line, 1):
            if char in INVISIBLE_CHARS:
                issues.append(
                    ForensicIssue(
                        category="CONTROL_CHARS",
                        severity="WARNING",
                        line_number=idx,
                        column=char_idx,
                        message=f"Invisible character found: {INVISIBLE_CHARS[char]}",
                        sample_value=repr(char),
                    )
                )
            elif ord(char) < 32 and char not in ("\t", "\n", "\r"):
                issues.append(
                    ForensicIssue(
                        category="CONTROL_CHARS",
                        severity="ERROR",
                        line_number=idx,
                        column=char_idx,
                        message=f"Control character found: ASCII {ord(char)}",
                        sample_value=repr(char),
                    )
                )

    return issues


def check_headers(headers: List[str]) -> List[ForensicIssue]:
    """Inspect CSV header fields for duplicates, trailing spaces, or empty names.

    Args:
        headers: List of header strings.

    Returns:
        List of ForensicIssue objects.
    """
    issues: List[ForensicIssue] = []
    seen: Dict[str, int] = {}

    for idx, raw_header in enumerate(headers, 1):
        stripped = raw_header.strip()

        if not raw_header:
            issues.append(
                ForensicIssue(
                    category="HEADER",
                    severity="ERROR",
                    line_number=1,
                    column=idx,
                    message="Empty header column name.",
                )
            )
        elif raw_header != stripped:
            issues.append(
                ForensicIssue(
                    category="HEADER",
                    severity="WARNING",
                    line_number=1,
                    column=idx,
                    message="Header has leading or trailing whitespace.",
                    sample_value=repr(raw_header),
                )
            )

        key = stripped.lower()
        if key in seen:
            issues.append(
                ForensicIssue(
                    category="HEADER",
                    severity="ERROR",
                    line_number=1,
                    column=idx,
                    message=(
                        f"Duplicate header name '{stripped}' (first seen at "
                        f"column {seen[key]})."
                    ),
                    sample_value=stripped,
                )
            )
        else:
            seen[key] = idx

    return issues


def check_excel_corruption(
    headers: List[str], rows: List[List[str]]
) -> List[ForensicIssue]:
    """Scan rows for Excel-specific data corruptions.

    Args:
        headers: List of header names.
        rows: List of CSV row values.

    Returns:
        List of ForensicIssue objects.
    """
    issues: List[ForensicIssue] = []
    id_kws = ("id", "code", "account", "num", "zip", "phone", "sku")

    for row_idx, row in enumerate(rows, 2):  # Line 2 is first data row
        for col_idx, val in enumerate(row):
            if not val:
                continue

            h_name = headers[col_idx] if col_idx < len(headers) else f"Col_{col_idx+1}"

            # Check Excel Formula Error strings
            if EXCEL_ERROR_PATTERN.match(val.strip()):
                issues.append(
                    ForensicIssue(
                        category="EXCEL_CORRUPTION",
                        severity="ERROR",
                        line_number=row_idx,
                        column=h_name,
                        message=f"Excel error value detected: '{val}'",
                        sample_value=val,
                    )
                )

            # Check Scientific Notation on non-float ID fields
            if SCIENTIFIC_NOTATION_PATTERN.match(val.strip()):
                if any(kw in h_name.lower() for kw in id_kws):
                    issues.append(
                        ForensicIssue(
                            category="EXCEL_CORRUPTION",
                            severity="WARNING",
                            line_number=row_idx,
                            column=h_name,
                            message=(
                                "Possible Excel scientific notation corruption "
                                f"on identifier field '{h_name}'."
                            ),
                            sample_value=val,
                        )
                    )

            # Check suspicious leading zero loss (e.g. 4-digit ZIP code)
            is_zip_kw = any(kw in h_name.lower() for kw in ("zip", "postal", "code"))
            if val.isdigit() and len(val) == 4 and is_zip_kw:
                issues.append(
                    ForensicIssue(
                        category="EXCEL_CORRUPTION",
                        severity="INFO",
                        line_number=row_idx,
                        column=h_name,
                        message=(
                            "Potential truncated leading zero in ZIP/postal "
                            f"code field '{h_name}'."
                        ),
                        sample_value=val,
                    )
                )

    return issues


def analyze_csv(
    file_path: Path,
    delimiter: Optional[str] = None,
    encoding_override: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute complete CSV forensic analysis on target file.

    Args:
        file_path: Path to target CSV file.
        delimiter: Optional explicit delimiter.
        encoding_override: Optional explicit encoding.
        max_rows: Maximum rows to analyze.

    Returns:
        Dictionary report containing summary statistics and list of issues.
    """
    raw_bytes = file_path.read_bytes()

    detected_encoding, bom_type, issues = detect_encoding_and_bom(raw_bytes)
    used_encoding = encoding_override or detected_encoding

    text_content = raw_bytes.decode(used_encoding, errors="replace")

    # Check control & invisible characters
    issues.extend(check_invisible_and_control_chars(text_content))

    # Detect delimiter if not provided
    sample_text = text_content[:4096]
    used_delimiter = delimiter
    if not used_delimiter:
        used_delimiter, delim_issues = detect_delimiter(sample_text)
        issues.extend(delim_issues)

    # Parse rows using csv.reader
    reader = csv.reader(io.StringIO(text_content), delimiter=used_delimiter)

    all_rows: List[List[str]] = []
    headers: List[str] = []
    line_count = 0

    try:
        for row in reader:
            line_count += 1
            if line_count == 1:
                headers = row
            else:
                all_rows.append(row)

            if max_rows and len(all_rows) >= max_rows:
                break
    except csv.Error as err:
        issues.append(
            ForensicIssue(
                category="QUOTING",
                severity="ERROR",
                line_number=line_count + 1,
                column=None,
                message=f"CSV parsing failure (broken quoting/delimiter): {err}",
            )
        )

    # Analyze headers
    if headers:
        issues.extend(check_headers(headers))

    # Structural row integrity (field count check)
    expected_count = len(headers)
    for idx, row in enumerate(all_rows, 2):
        if len(row) != expected_count:
            issues.append(
                ForensicIssue(
                    category="ROW_MALFORMED",
                    severity="ERROR",
                    line_number=idx,
                    column=None,
                    message=(
                        f"Row field count ({len(row)}) does not match header "
                        f"count ({expected_count})."
                    ),
                    sample_value=f"Fields: {len(row)}",
                )
            )

    # Excel corruption checks
    if headers and all_rows:
        issues.extend(check_excel_corruption(headers, all_rows))

    summary = {
        "file_name": file_path.name,
        "file_size_bytes": len(raw_bytes),
        "encoding_used": used_encoding,
        "bom_type": bom_type,
        "delimiter_used": repr(used_delimiter),
        "total_lines_read": line_count,
        "total_data_rows": len(all_rows),
        "header_count": len(headers),
        "total_issues_found": len(issues),
        "issue_counts_by_severity": {
            "ERROR": sum(1 for i in issues if i.severity == "ERROR"),
            "WARNING": sum(1 for i in issues if i.severity == "WARNING"),
            "INFO": sum(1 for i in issues if i.severity == "INFO"),
        },
    }

    return {"summary": summary, "issues": [asdict(i) for i in issues]}


def format_text_report(report_data: Dict[str, Any]) -> str:
    """Format diagnostic findings into terminal text output.

    Args:
        report_data: Result dictionary from analyze_csv.

    Returns:
        Formatted summary report string.
    """
    summary = report_data["summary"]
    issues = report_data["issues"]

    size_b = summary["file_size_bytes"]
    bom_str = summary["bom_type"] or "None"
    rows_cnt = summary["total_data_rows"]
    cols_cnt = summary["header_count"]

    lines = [
        "============================================================",
        " CSV FORENSICS AUDIT REPORT",
        "============================================================",
        f" Target File  : {summary['file_name']} ({size_b} bytes)",
        f" Encoding Used: {summary['encoding_used']} (BOM: {bom_str})",
        f" Delimiter    : {summary['delimiter_used']}",
        f" Total Rows   : {rows_cnt} data rows ({cols_cnt} columns)",
        "------------------------------------------------------------",
        f" Total Diagnostics Found: {summary['total_issues_found']}",
        f"   - Errors   : {summary['issue_counts_by_severity']['ERROR']}",
        f"   - Warnings : {summary['issue_counts_by_severity']['WARNING']}",
        f"   - Info     : {summary['issue_counts_by_severity']['INFO']}",
        "============================================================",
    ]

    if not issues:
        lines.append(" SUCCESS: No forensic issues or corruption detected.")
        return "\n".join(lines)

    lines.append("\nDetailed Diagnostic Issues:")
    for idx, iss in enumerate(issues, 1):
        loc = f"Line {iss['line_number']}" if iss["line_number"] else "Global"
        if iss["column"] is not None:
            loc += f", Col {iss['column']}"

        lines.extend(
            [
                f"[{idx:02d}] [{iss['severity']:7s}] [{iss['category']:16s}] ({loc})",
                f"     Message: {iss['message']}",
            ]
        )
        if iss["sample_value"] is not None:
            lines.append(f"     Sample : {iss['sample_value']}")
        lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point for CSV Forensics tool."""
    parser = argparse.ArgumentParser(
        description=(
            "Deep forensic audit tool for CSV file integrity and corruption "
            "detection."
        )
    )
    parser.add_argument("file_path", help="Path to CSV file to inspect.")
    parser.add_argument(
        "-d",
        "--delimiter",
        help="Force specific column delimiter (e.g., ',' or ';').",
    )
    parser.add_argument(
        "-e", "--encoding", help="Force specific encoding for reading file."
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output report file path (defaults to stdout).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output report format.",
    )
    parser.add_argument(
        "--max-rows", type=int, help="Maximum number of rows to inspect."
    )

    args = parser.parse_args(argv)
    csv_file = Path(args.file_path)

    if not csv_file.is_file():
        print(
            f"Error: Target CSV file not found: {args.file_path}",
            file=sys.stderr,
        )
        return 1

    report_data = analyze_csv(
        csv_file,
        delimiter=args.delimiter,
        encoding_override=args.encoding,
        max_rows=args.max_rows,
    )

    if args.format == "json":
        output_content = json.dumps(report_data, indent=2)
    else:
        output_content = format_text_report(report_data)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_content, encoding="utf-8")
        print(f"Forensic report written to: {args.output}")
    else:
        print(output_content)

    errs = report_data["summary"]["issue_counts_by_severity"]["ERROR"]
    has_errors = errs > 0
    return 2 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
