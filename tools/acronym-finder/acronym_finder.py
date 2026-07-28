"""Scan documents and extract acronyms with first-occurrence context.

This module parses text files or streams, identifies potential acronyms and
their expanded forms (if present in context), and records the line number and
sentence context of their first occurrence.
"""

import argparse
import csv
import json
import logging
import re
import sys
from typing import Any, Dict, List, NamedTuple, Optional, Pattern, Set

# Configure module logger
logger = logging.getLogger(__name__)

# Regex pattern for acronyms (e.g., API, HTTP, U.S.A., NASA)
ACRONYM_PATTERN: Pattern[str] = re.compile(r"\b[A-Z]{2,}\b|(?:[A-Z]\.){2,}")

# Pattern to capture acronym expansions like "Application Programming Interface (API)"
EXPANSION_BEFORE_PATTERN: Pattern[str] = re.compile(
    r"\b((?:[A-Z][a-z]+(?:\s+|\-)){2,5})\s*\((?:[A-Z]{2,}|(?:[A-Z]\.){2,})\)"
)

# Pattern to capture "API (Application Programming Interface)"
EXPANSION_AFTER_PATTERN: Pattern[str] = re.compile(
    r"\b([A-Z]{2,}|(?:[A-Z]\.){2,})\s*\(((?:[A-Za-z]+(?:\s+|\-)){2,5})\)"
)


class AcronymMatch(NamedTuple):
    """Container for acronym occurrence metadata."""

    acronym: str
    line_number: int
    context: str
    expansion: Optional[str]


def clean_acronym(raw_acronym: str) -> str:
    """Normalize acronym string (remove internal periods for grouping).

    Args:
        raw_acronym: The matched acronym string.

    Returns:
        Cleaned uppercase acronym string.
    """
    return raw_acronym.replace(".", "")


def find_expansion_in_text(acronym: str, line: str) -> Optional[str]:
    """Find potential expansion definition for an acronym in a line.

    Args:
        acronym: The acronym string.
        line: The text line where the acronym occurred.

    Returns:
        Expanded phrase string if found, otherwise None.
    """
    # Check for "Expanded Name (ACRONYM)"
    for match in EXPANSION_BEFORE_PATTERN.finditer(line):
        full_match = match.group(0)
        if acronym in full_match:
            return match.group(1).strip()

    # Check for "ACRONYM (Expanded Name)"
    for match in EXPANSION_AFTER_PATTERN.finditer(line):
        if match.group(1).replace(".", "") == acronym:
            return match.group(2).strip()

    return None


def scan_acronyms(text: str, min_length: int = 2) -> List[AcronymMatch]:
    """Scan document text for acronyms and record first occurrences.

    Args:
        text: The document text content.
        min_length: Minimum acronym character count (default 2).

    Returns:
        List of AcronymMatch instances ordered by appearance.
    """
    seen: Set[str] = set()
    results: List[AcronymMatch] = []
    lines = text.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        line_clean = line.strip()
        if not line_clean:
            continue

        matches = ACRONYM_PATTERN.findall(line_clean)
        for raw_acronym in matches:
            cleaned = clean_acronym(raw_acronym)
            if len(cleaned) < min_length:
                continue

            if cleaned not in seen:
                seen.add(cleaned)
                expansion = find_expansion_in_text(cleaned, line_clean)
                results.append(
                    AcronymMatch(
                        acronym=cleaned,
                        line_number=line_idx,
                        context=line_clean,
                        expansion=expansion,
                    )
                )

    return results


def format_text_output(matches: List[AcronymMatch]) -> str:
    """Format acronym results as readable plain text summary.

    Args:
        matches: List of AcronymMatch items.

    Returns:
        Formatted summary string.
    """
    if not matches:
        return "No acronyms found."

    output_lines: List[str] = [
        f"Found {len(matches)} acronym(s):\n",
        f"{'ACRONYM':<12} {'LINE':<6} {'EXPANSION':<35} {'CONTEXT'}",
        "-" * 80,
    ]

    for item in matches:
        exp = item.expansion or "N/A"
        context_trunc = (
            item.context[:30] + "..." if len(item.context) > 33 else item.context
        )
        output_lines.append(
            f"{item.acronym:<12} {item.line_number:<6} {exp:<35} {context_trunc}"
        )

    return "\n".join(output_lines)


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Scan documents and list acronyms with first occurrence context."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=argparse.FileType("r", encoding="utf-8"),
        default=sys.stdin,
        help="Input document file path (defaults to stdin).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output report format (default: text).",
    )
    parser.add_argument(
        "-m",
        "--min-length",
        type=int,
        default=2,
        help="Minimum acronym length (default: 2).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def export_csv(matches: List[AcronymMatch]) -> str:
    """Export acronym matches as CSV string.

    Args:
        matches: List of AcronymMatch objects.

    Returns:
        Formatted CSV string.
    """
    import io  # pylint: disable=import-outside-toplevel

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["acronym", "line_number", "expansion", "context"])
    for m in matches:
        writer.writerow([m.acronym, m.line_number, m.expansion or "", m.context])
    return output.getvalue()


def main() -> None:
    """Main CLI execution entry point."""
    parser = setup_cli_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        content = args.file.read()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read input document: %s", exc)
        sys.exit(1)

    matches = scan_acronyms(content, min_length=args.min_length)

    if args.format == "json":
        json_data: List[Dict[str, Any]] = [
            {
                "acronym": m.acronym,
                "line_number": m.line_number,
                "expansion": m.expansion,
                "context": m.context,
            }
            for m in matches
        ]
        print(json.dumps(json_data, indent=2))
    elif args.format == "csv":
        print(export_csv(matches), end="")
    else:
        print(format_text_output(matches))


if __name__ == "__main__":
    main()
