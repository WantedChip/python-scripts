"""Whitespace Cleaner Utility.

Trims leading, trailing, and excessive internal whitespace from text or
CSV/TSV cells. Supports newline normalization, tab-to-space conversion,
and in-place file modifications.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import List, Optional, Union

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught,no-else-return


def clean_cell_whitespace(
    text: str,
    collapse_internal: bool = True,
    convert_tabs: bool = False,
    tab_width: int = 4,
) -> str:
    """Cleans whitespace for a single string or table cell value.

    Args:
        text: Target text string to clean.
        collapse_internal: Collapse consecutive internal spaces.
        convert_tabs: Convert tab characters to spaces.
        tab_width: Number of spaces for tab expansion.

    Returns:
        Cleaned text string.
    """
    if not text:
        return ""

    if convert_tabs:
        text = text.expandtabs(tab_width)

    if collapse_internal:
        # Strip leading/trailing whitespace and collapse internal spaces
        return re.sub(r"[ \t]+", " ", text).strip()
    return text.strip()


def clean_text_content(
    content: str,
    collapse_internal: bool = True,
    normalize_newlines: bool = True,
    convert_tabs: bool = False,
    tab_width: int = 4,
) -> str:
    """Cleans whitespace in line-by-line raw text content.

    Args:
        content: Raw text string.
        collapse_internal: Collapse multiple spaces per line.
        normalize_newlines: Standardize CRLF (\r\n) to LF (\n).
        convert_tabs: Expand tabs to spaces.
        tab_width: Tab width in spaces.

    Returns:
        Cleaned text content.
    """
    if normalize_newlines:
        content = content.replace("\r\n", "\n").replace("\r", "\n")

    lines = content.split("\n")
    cleaned_lines = [
        clean_cell_whitespace(
            line,
            collapse_internal=collapse_internal,
            convert_tabs=convert_tabs,
            tab_width=tab_width,
        )
        for line in lines
    ]

    return "\n".join(cleaned_lines)


def clean_csv_file(
    input_path: Path,
    output_path: Path,
    delimiter: str = ",",
    collapse_internal: bool = True,
    convert_tabs: bool = False,
    tab_width: int = 4,
) -> None:
    """Cleans all cell values in a CSV/TSV file.

    Args:
        input_path: Path to input CSV/TSV file.
        output_path: Path to output CSV/TSV file.
        delimiter: CSV/TSV field delimiter.
        collapse_internal: Collapse consecutive spaces within cell text.
        convert_tabs: Convert tab characters inside cells.
        tab_width: Width for tab conversion.
    """
    with open(input_path, "r", encoding="utf-8", newline="") as infile:
        reader = csv.reader(infile, delimiter=delimiter)
        rows = list(reader)

    cleaned_rows = []
    for row in rows:
        cleaned_row = [
            clean_cell_whitespace(
                cell,
                collapse_internal=collapse_internal,
                convert_tabs=convert_tabs,
                tab_width=tab_width,
            )
            for cell in row
        ]
        cleaned_rows.append(cleaned_row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile, delimiter=delimiter)
        writer.writerows(cleaned_rows)


def clean_whitespace(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    mode: str = "auto",
    in_place: bool = False,
    collapse_internal: bool = True,
    normalize_newlines: bool = True,
    convert_tabs: bool = False,
    tab_width: int = 4,
) -> None:
    """Main clean function supporting CSV/TSV and text modes.

    Args:
        input_path: Path to input file.
        output_path: Path for output file. Required if in_place is False.
        mode: Processing mode ('auto', 'csv', 'tsv', 'text').
        in_place: Overwrite the input file directly.
        collapse_internal: Collapse consecutive spaces.
        normalize_newlines: Standardize CRLF to LF.
        convert_tabs: Convert tabs to spaces.
        tab_width: Number of spaces per tab.
    """
    inp_p = Path(input_path)
    if in_place:
        target_output = inp_p
    elif output_path:
        target_output = Path(output_path)
    else:
        raise ValueError("Must specify output path or --in-place flag.")

    if mode == "auto":
        suffix = inp_p.suffix.lower()
        if suffix == ".tsv":
            effective_mode = "tsv"
        elif suffix == ".csv":
            effective_mode = "csv"
        else:
            effective_mode = "text"
    else:
        effective_mode = mode

    if effective_mode in ("csv", "tsv"):
        delimiter = "\t" if effective_mode == "tsv" else ","
        clean_csv_file(
            input_path=inp_p,
            output_path=target_output,
            delimiter=delimiter,
            collapse_internal=collapse_internal,
            convert_tabs=convert_tabs,
            tab_width=tab_width,
        )
    else:
        with open(inp_p, "r", encoding="utf-8") as f:
            content = f.read()

        cleaned = clean_text_content(
            content=content,
            collapse_internal=collapse_internal,
            normalize_newlines=normalize_newlines,
            convert_tabs=convert_tabs,
            tab_width=tab_width,
        )

        target_output.parent.mkdir(parents=True, exist_ok=True)
        with open(target_output, "w", encoding="utf-8") as f:
            f.write(cleaned)


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    desc = "Whitespace Cleaner Utility for text and CSV/TSV files."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("input", help="Path to input file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Path to output file (optional if --in-place is set)",
    )
    parser.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="Overwrite the input file directly",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["auto", "csv", "tsv", "text"],
        default="auto",
        help="File processing mode (default: auto)",
    )
    parser.add_argument(
        "--no-collapse",
        action="store_true",
        help="Do not collapse consecutive internal spaces into a single space",
    )
    parser.add_argument(
        "--convert-tabs",
        action="store_true",
        help="Convert tab characters to spaces",
    )
    parser.add_argument(
        "--tab-width",
        type=int,
        default=4,
        help="Tab conversion width in spaces (default: 4)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.in_place and not parsed.output:
        parser.error(
            "Output file path is required unless --in-place (-i) is specified."
        )

    try:
        clean_whitespace(
            input_path=parsed.input,
            output_path=parsed.output,
            mode=parsed.mode,
            in_place=parsed.in_place,
            collapse_internal=not parsed.no_collapse,
            convert_tabs=parsed.convert_tabs,
            tab_width=parsed.tab_width,
        )
        dest = parsed.input if parsed.in_place else parsed.output
        print(f"Successfully cleaned whitespace in '{dest}'.")
        return 0
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
