"""Text Diff Tool.

Compares two text files line-by-line and generates unified or side-by-side
diff reports with change summary metrics.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Dict, List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=too-many-nested-blocks


def calculate_diff_metrics(text1: str, text2: str) -> Dict[str, int]:
    """Calculate summary metrics for differences between two texts.

    Args:
        text1: Original text content.
        text2: Modified text content.

    Returns:
        Dictionary containing counts for additions, deletions, modifications.
    """
    lines1 = text1.splitlines()
    lines2 = text2.splitlines()

    matcher = difflib.SequenceMatcher(None, lines1, lines2)
    additions = 0
    deletions = 0
    modifications = 0
    unchanged = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        elif tag == "replace":
            len1 = i2 - i1
            len2 = j2 - j1
            modifications += min(len1, len2)
            if len1 > len2:
                deletions += len1 - len2
            elif len2 > len1:
                additions += len2 - len1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "insert":
            additions += j2 - j1

    return {
        "additions": additions,
        "deletions": deletions,
        "modifications": modifications,
        "unchanged": unchanged,
    }


def generate_unified_diff(
    text1: str,
    text2: str,
    from_file: str = "file1",
    to_file: str = "file2",
    color: bool = False,
) -> str:
    """Generate a unified diff report between two texts.

    Args:
        text1: Original text.
        text2: Modified text.
        from_file: Label for original text source.
        to_file: Label for modified text source.
        color: Whether to include ANSI color escape codes.

    Returns:
        Unified diff as a string.
    """
    lines1 = text1.splitlines(keepends=True)
    lines2 = text2.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            lines1, lines2, fromfile=from_file, tofile=to_file, lineterm=""
        )
    )

    if not color:
        return "\n".join(diff_lines)

    colored_lines = []
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            colored_lines.append(f"\033[1m{line}\033[0m")
        elif line.startswith("@@"):
            colored_lines.append(f"\033[36m{line}\033[0m")
        elif line.startswith("+"):
            colored_lines.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            colored_lines.append(f"\033[31m{line}\033[0m")
        else:
            colored_lines.append(line)

    return "\n".join(colored_lines)


def generate_side_by_side_diff(
    text1: str, text2: str, width: int = 80, color: bool = False
) -> str:
    """Generate a side-by-side diff report between two texts with line numbers.

    Args:
        text1: Original text.
        text2: Modified text.
        width: Total width of the side-by-side output.
        color: Whether to include ANSI color escape codes.

    Returns:
        Side-by-side diff formatted as a string.
    """
    lines1 = text1.splitlines()
    lines2 = text2.splitlines()

    col_width = (width - 7) // 2
    matcher = difflib.SequenceMatcher(None, lines1, lines2)

    output = []
    orig_lbl = f"{'ORIGINAL':<{col_width}}"
    mod_lbl = f"{'MODIFIED':<{col_width}}"
    header = f"{'LINE':<5} {orig_lbl} | {'LINE':<5} {mod_lbl}"
    separator = "-" * len(header)
    output.append(header)
    output.append(separator)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                l1 = lines1[i][:col_width]
                l2 = lines2[j][:col_width]
                output.append(
                    f"{i+1:<5} {l1:<{col_width}} | {j+1:<5} {l2:<{col_width}}"
                )
        elif tag == "replace":
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                idx1 = i1 + k if k < (i2 - i1) else None
                idx2 = j1 + k if k < (j2 - j1) else None
                l1 = lines1[idx1][:col_width] if idx1 is not None else ""
                l2 = lines2[idx2][:col_width] if idx2 is not None else ""
                n1 = str(idx1 + 1) if idx1 is not None else ""
                n2 = str(idx2 + 1) if idx2 is not None else ""

                row = f"{n1:<5} {l1:<{col_width}} | {n2:<5} {l2:<{col_width}}"
                if color:
                    row = f"\033[33m{row}\033[0m"
                output.append(row)
        elif tag == "delete":
            for i in range(i1, i2):
                l1 = lines1[i][:col_width]
                row = f"{i+1:<5} {l1:<{col_width}} | {'':<5} {'':<{col_width}}"
                if color:
                    row = f"\033[31m{row}\033[0m"
                output.append(row)
        elif tag == "insert":
            for j in range(j1, j2):
                l2 = lines2[j][:col_width]
                row = f"{'':<5} {'':<{col_width}} | {j+1:<5} {l2:<{col_width}}"
                if color:
                    row = f"\033[32m{row}\033[0m"
                output.append(row)

    return "\n".join(output)


def format_summary_metrics(metrics: Dict[str, int]) -> str:
    """Format metrics dictionary into a readable summary string."""
    return (
        f"--- Diff Summary Metrics ---\n"
        f"Additions    : {metrics['additions']}\n"
        f"Deletions    : {metrics['deletions']}\n"
        f"Modifications: {metrics['modifications']}\n"
        f"Unchanged    : {metrics['unchanged']}\n"
        f"Total Lines  : {sum(metrics.values())}"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Compare two text files line-by-line with unified or side-by-side" + " diffs."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("file1", type=Path, help="Path to original text file")
    parser.add_argument("file2", type=Path, help="Path to modified text file")
    parser.add_argument(
        "--format",
        choices=["unified", "side-by-side"],
        default="unified",
        help="Diff output format (default: unified)",
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="Enable colored ANSI output",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=80,
        help="Column width for side-by-side diff (default: 80)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Text Diff Tool."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.file1.exists() or not parsed.file2.exists():
        sys.stderr.write("Error: One or both input files do not exist.\n")
        return 1

    content1 = parsed.file1.read_text(encoding="utf-8")
    content2 = parsed.file2.read_text(encoding="utf-8")

    metrics = calculate_diff_metrics(content1, content2)

    if parsed.format == "unified":
        report = generate_unified_diff(
            content1,
            content2,
            from_file=str(parsed.file1),
            to_file=str(parsed.file2),
            color=parsed.color,
        )
    else:
        report = generate_side_by_side_diff(
            content1, content2, width=parsed.width, color=parsed.color
        )

    print(report)
    print("\n" + format_summary_metrics(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
