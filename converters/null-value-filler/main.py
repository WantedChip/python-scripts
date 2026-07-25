"""CSV Null Value Filler Utility.

Fills missing/null/empty values in CSV columns using specified strategies:
- constant: fill with a constant value
- mean: fill numeric columns with column mean
- median: fill numeric columns with column median
- mode: fill with column mode (most frequent value)
- ffill: forward fill missing values
- bfill: backward fill missing values
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import List, Optional, Set, Union

DEFAULT_MISSING_TOKENS = {
    "",
    "N/A",
    "n/a",
    "null",
    "NULL",
    "None",
    "NONE",
    "NA",
    "na",
    "NaN",
    "nan",
}


def is_missing(val: Optional[str], missing_tokens: Set[str]) -> bool:
    """Check if a cell value should be treated as missing."""
    if val is None:
        return True
    return val.strip() in missing_tokens


def fill_null_values(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    strategy: str = "constant",
    columns: Optional[List[str]] = None,
    constant_value: str = "",
    missing_tokens: Optional[Set[str]] = None,
) -> None:
    """Fills missing values in a CSV file according to the specified strategy.

    Args:
        input_path: Path to the input CSV file.
        output_path: Path where output CSV will be saved.
        strategy: Filling strategy ('constant', 'mean', 'median', 'mode', ...).
        columns: Target column names to fill. If None, applies to all columns.
        constant_value: Value to use when strategy is 'constant'.
        missing_tokens: Set of strings to consider as null/missing values.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    if missing_tokens is None:
        missing_tokens = DEFAULT_MISSING_TOKENS

    with open(input_path, "r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError("CSV file has no header or is empty.")
        rows = list(reader)

    target_columns = columns if columns else list(fieldnames)

    # Validate target columns exist
    for col in target_columns:
        if col not in fieldnames:
            raise ValueError(f"Column '{col}' not found in CSV header.")

    filled_rows = [dict(row) for row in rows]

    for col in target_columns:
        if strategy == "constant":
            for row in filled_rows:
                if is_missing(row.get(col), missing_tokens):
                    row[col] = constant_value

        elif strategy in ("mean", "median"):
            # Extract valid numeric values
            numeric_vals = []
            for row in rows:
                val = row.get(col)
                if val is not None and not is_missing(val, missing_tokens):
                    try:
                        numeric_vals.append(float(val))
                    except ValueError:
                        pass
            if not numeric_vals:
                fill_val = constant_value
            else:
                calc_val = (
                    mean(numeric_vals) if strategy == "mean" else median(numeric_vals)
                )
                if calc_val.is_integer():
                    fill_val = str(int(calc_val))
                else:
                    fill_val = f"{calc_val:.4f}".rstrip("0").rstrip(".")

            for row in filled_rows:
                if is_missing(row.get(col), missing_tokens):
                    row[col] = fill_val

        elif strategy == "mode":
            valid_vals = [
                row.get(col)
                for row in rows
                if not is_missing(row.get(col), missing_tokens)
            ]
            if valid_vals:
                counts = Counter(valid_vals)
                fill_val = str(counts.most_common(1)[0][0])
            else:
                fill_val = constant_value

            for row in filled_rows:
                if is_missing(row.get(col), missing_tokens):
                    row[col] = fill_val

        elif strategy == "ffill":
            last_valid = None
            for row in filled_rows:
                if is_missing(row.get(col), missing_tokens):
                    if last_valid is not None:
                        row[col] = last_valid
                else:
                    last_valid = row.get(col)

        elif strategy == "bfill":
            next_valid = None
            for row in reversed(filled_rows):
                if is_missing(row.get(col), missing_tokens):
                    if next_valid is not None:
                        row[col] = next_valid
                else:
                    next_valid = row.get(col)

        else:
            raise ValueError(f"Unsupported strategy: '{strategy}'")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filled_rows)


def build_parser() -> argparse.ArgumentParser:
    """Build command-line interface parser."""
    desc = "Fill missing/null values in CSV files."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("input", help="Path to input CSV file")
    parser.add_argument("output", help="Path to output CSV file")
    parser.add_argument(
        "--strategy",
        "-s",
        choices=["constant", "mean", "median", "mode", "ffill", "bfill"],
        default="constant",
        help="Strategy to fill missing values (default: constant)",
    )
    parser.add_argument(
        "--columns",
        "-c",
        nargs="+",
        help="Specific columns to fill missing values for.",
    )
    parser.add_argument(
        "--value",
        "-v",
        default="",
        help="Constant fill value when using --strategy constant",
    )
    parser.add_argument(
        "--missing-tokens",
        nargs="+",
        help="Custom tokens to treat as null/missing (e.g. NA N/A null NaN)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for null-value-filler."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    missing_tokens = set(parsed.missing_tokens) if parsed.missing_tokens else None
    try:
        fill_null_values(
            input_path=parsed.input,
            output_path=parsed.output,
            strategy=parsed.strategy,
            columns=parsed.columns,
            constant_value=parsed.value,
            missing_tokens=missing_tokens,
        )
        msg = (
            f"Successfully processed '{parsed.input}' -> '{parsed.output}' "
            f"using strategy '{parsed.strategy}'."
        )
        print(msg)
    except (OSError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
