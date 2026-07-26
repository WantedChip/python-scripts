"""CSV Merge Utility.

Merges multiple CSV files with matching or overlapping headers into a single
unified CSV file with header alignment, missing column default values,
optional source file tagging, and row deduplication.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import csv
import glob
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple, Union


def resolve_input_files(file_patterns: List[str]) -> List[Path]:
    """Resolves glob patterns or file paths into a list of existing Path objects.

    Args:
        file_patterns: File paths or glob patterns.

    Returns:
        List of resolved Path objects.
    """
    resolved = []
    for pattern in file_patterns:
        matches = glob.glob(pattern)
        if matches:
            for match in sorted(matches):
                p = Path(match)
                if p.is_file() and p not in resolved:
                    resolved.append(p)
        else:
            p = Path(pattern)
            if p.is_file() and p not in resolved:
                resolved.append(p)

    return resolved


def merge_csvs(
    input_files: Sequence[Union[str, Path]],
    output_file: Union[str, Path],
    tag_source_col: Optional[str] = None,
    default_value: str = "",
    dedupe: bool = False,
) -> int:
    """Merges multiple CSV files into a unified CSV file.

    Args:
        input_files: List of paths to input CSV files.
        output_file: Path to destination merged CSV file.
        tag_source_col: Name of output column to tag source filename.
        default_value: Default string to use when a record lacks a column.
        dedupe: If True, duplicate rows will be omitted.

    Returns:
        Total number of rows written to output file.
    """
    paths = [Path(p) for p in input_files]
    if not paths:
        raise ValueError("No input files provided for merging.")

    # 1. Collect ordered union of fieldnames from all files
    fieldnames: List[str] = []
    for path in paths:
        with open(path, "r", encoding="utf-8", newline="") as f:
            raw_reader = csv.reader(f)
            try:
                headers = next(raw_reader)
            except StopIteration:
                continue
            for h in headers:
                if h not in fieldnames:
                    fieldnames.append(h)

    if not fieldnames:
        raise ValueError("No valid headers found across input CSV files.")

    if tag_source_col and tag_source_col not in fieldnames:
        fieldnames.insert(0, tag_source_col)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows_written = 0
    seen_rows: Set[Tuple[Tuple[str, str], ...]] = set()

    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for path in paths:
            with open(path, "r", encoding="utf-8", newline="") as infile:
                dict_reader = csv.DictReader(infile)
                for row in dict_reader:
                    merged_row = {field: default_value for field in fieldnames}
                    for k, v in row.items():
                        if k in merged_row and v is not None:
                            merged_row[k] = v

                    if tag_source_col:
                        merged_row[tag_source_col] = path.name

                    if dedupe:
                        # Convert dict to tuple for deduplication tracking
                        row_key = tuple(sorted(merged_row.items()))
                        if row_key in seen_rows:
                            continue
                        seen_rows.add(row_key)

                    writer.writerow(merged_row)
                    rows_written += 1

    return rows_written


def build_parser() -> argparse.ArgumentParser:
    """Build command-line interface parser."""
    desc = "Merge multiple CSV files with header alignment."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input CSV files or glob patterns (e.g. data/*.csv)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output merged CSV file path",
    )
    parser.add_argument(
        "--tag-source",
        "-t",
        help="Add a column with specified name containing source filename",
    )
    parser.add_argument(
        "--default-val",
        "-d",
        default="",
        help="Default fill value for missing columns (default: empty string)",
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Remove duplicate rows across merged files",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    files = resolve_input_files(parsed.inputs)
    if not files:
        print("Error: No matching input files found.", file=sys.stderr)
        return 1

    try:
        count = merge_csvs(
            input_files=files,
            output_file=parsed.output,
            tag_source_col=parsed.tag_source,
            default_value=parsed.default_val,
            dedupe=parsed.dedupe,
        )
        msg = (
            f"Successfully merged {len(files)} files into "
            f"'{parsed.output}' ({count} rows)."
        )
        print(msg)
    except (OSError, ValueError, csv.Error) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
