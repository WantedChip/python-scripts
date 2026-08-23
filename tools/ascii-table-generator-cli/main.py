"""ASCII Table Generator CLI.

Converts CSV or TSV data into formatted ASCII tables for terminal display.
Supports border styles: grid, simple, markdown, fancy.
Supports alignment: left, right, center.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import csv
import io
import sys
from typing import List, Optional

BORDER_STYLES = {
    "grid": {
        "top_left": "+",
        "top_mid": "+",
        "top_right": "+",
        "top_line": "-",
        "mid_left": "+",
        "mid_mid": "+",
        "mid_right": "+",
        "mid_line": "-",
        "bot_left": "+",
        "bot_mid": "+",
        "bot_right": "+",
        "bot_line": "-",
        "v_line": "|",
        "header_line": "-",
    },
    "simple": {
        "top_left": "",
        "top_mid": "",
        "top_right": "",
        "top_line": "",
        "mid_left": "",
        "mid_mid": "",
        "mid_right": "",
        "mid_line": "-",
        "bot_left": "",
        "bot_mid": "",
        "bot_right": "",
        "bot_line": "",
        "v_line": " ",
        "header_line": "-",
    },
    "markdown": {
        "top_left": "|",
        "top_mid": "|",
        "top_right": "|",
        "top_line": "",
        "mid_left": "|",
        "mid_mid": "|",
        "mid_right": "|",
        "mid_line": "-",
        "bot_left": "|",
        "bot_mid": "|",
        "bot_right": "|",
        "bot_line": "",
        "v_line": "|",
        "header_line": "-",
    },
    "fancy": {
        "top_left": "┌",
        "top_mid": "┬",
        "top_right": "┐",
        "top_line": "─",
        "mid_left": "├",
        "mid_mid": "┼",
        "mid_right": "┤",
        "mid_line": "─",
        "bot_left": "└",
        "bot_mid": "┴",
        "bot_right": "┘",
        "bot_line": "─",
        "v_line": "│",
        "header_line": "═",
    },
}


def parse_data(content: str, delimiter: Optional[str] = None) -> List[List[str]]:
    """Parse CSV or TSV raw string into a 2D matrix of strings.

    Args:
        content: Raw input string.
        delimiter: Column delimiter (e.g. ',' or '\t'). Autodetected if None.

    Returns:
        List of rows, where each row is a list of string cell values.
    """
    if not content.strip():
        return []

    if delimiter is None:
        delimiter = "\t" if "\t" in content else ","

    reader = csv.reader(io.StringIO(content.strip()), delimiter=delimiter)
    return [row for row in reader if row]


def calculate_column_widths(rows: List[List[str]]) -> List[int]:
    """Calculate maximum width required for each column.

    Args:
        rows: Matrix of cell strings.

    Returns:
        List of max width integers corresponding to each column index.
    """
    if not rows:
        return []

    num_cols = max(len(row) for row in rows)
    widths = [0] * num_cols

    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    return widths


def format_cell(text: str, width: int, align: str = "left") -> str:
    """Format and align text inside a cell of given width.

    Args:
        text: Cell string content.
        width: Column width.
        align: Alignment mode ('left', 'right', 'center').

    Returns:
        Aligned and padded cell string.
    """
    if align == "right":
        return text.rjust(width)
    if align == "center":
        pad = max(width - len(text), 0)
        left = pad // 2
        return " " * left + text + " " * (pad - left)
    return text.ljust(width)


def render_table(
    rows: List[List[str]],
    style_name: str = "grid",
    align: str = "left",
    has_header: bool = True,
) -> str:
    """Render rows into a formatted ASCII table string.

    Args:
        rows: Matrix of string rows.
        style_name: Border style ('grid', 'simple', 'markdown', 'fancy').
        align: Text alignment ('left', 'right', 'center').
        has_header: Treat the first row as a header if True.

    Returns:
        Formatted ASCII table string.
    """
    if not rows:
        return ""

    style = BORDER_STYLES.get(style_name, BORDER_STYLES["grid"])
    widths = calculate_column_widths(rows)
    output_lines = []

    def make_divider(left: str, mid: str, right: str, char: str) -> str:
        if not char:
            return ""
        segments = [char * (w + 2) for w in widths]
        return left + mid.join(segments) + right

    # Top border
    if style["top_line"]:
        div = make_divider(
            style["top_left"],
            style["top_mid"],
            style["top_right"],
            style["top_line"],
        )
        output_lines.append(div)

    v = style["v_line"]

    for row_idx, row in enumerate(rows):
        # Normalize row length
        padded_row = row + [""] * (len(widths) - len(row))
        cells = [
            format_cell(cell, widths[i], align) for i, cell in enumerate(padded_row)
        ]

        if style_name == "simple":
            line = (" " + v + " ").join(cells)
        else:
            line = v + " " + (" | ").join(cells) + " " + v

        output_lines.append(line)

        # Header separator
        if has_header and row_idx == 0:
            if style_name == "markdown":
                align_chars = []
                for w in widths:
                    if align == "right":
                        align_chars.append("-" * (w + 1) + ":")
                    elif align == "center":
                        align_chars.append(":" + "-" * w + ":")
                    else:
                        align_chars.append("-" * (w + 2))
                output_lines.append("|" + "|".join(align_chars) + "|")
            elif style["mid_line"]:
                div = make_divider(
                    style["mid_left"],
                    style["mid_mid"],
                    style["mid_right"],
                    style["header_line"],
                )
                output_lines.append(div)
        elif (
            not (has_header and row_idx == 0)
            and row_idx < len(rows) - 1
            and style_name == "grid"
        ):
            div = make_divider(
                style["mid_left"],
                style["mid_mid"],
                style["mid_right"],
                style["mid_line"],
            )
            output_lines.append(div)

    # Bottom border
    if style["bot_line"]:
        div = make_divider(
            style["bot_left"],
            style["bot_mid"],
            style["bot_right"],
            style["bot_line"],
        )
        output_lines.append(div)

    return "\n".join(output_lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Convert CSV/TSV data into formatted ASCII tables."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-i",
        "--input",
        help="Path to input CSV/TSV file (reads stdin if omitted)",
    )
    parser.add_argument(
        "-d",
        "--delimiter",
        help="Delimiter character (autodetected if omitted)",
    )
    parser.add_argument(
        "-s",
        "--style",
        choices=["grid", "simple", "markdown", "fancy"],
        default="grid",
        help="Border style",
    )
    parser.add_argument(
        "-a",
        "--align",
        choices=["left", "right", "center"],
        default="left",
        help="Cell text alignment",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not treat first row as header",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for ASCII table generator."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.input:
        with open(parsed.input, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    rows = parse_data(content, delimiter=parsed.delimiter)
    if not rows:
        print("No data to display.", file=sys.stderr)
        return 0

    table = render_table(
        rows,
        style_name=parsed.style,
        align=parsed.align,
        has_header=not parsed.no_header,
    )
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
