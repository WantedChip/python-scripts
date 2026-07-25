"""CSV Column Reorder & Mapping Tool.

Reorders, selects, or drops columns in CSV files based on a specified header
sequence or configuration file. Handles missing optional columns with defaults.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import json
import sys
from typing import Any, Dict, List, Optional, TextIO, Tuple


def inspect_headers(input_file: str, delimiter: str = ",") -> List[str]:
    """Reads the header row of a CSV file.

    :param input_file: Path to input CSV file.
    :param delimiter: CSV field delimiter.
    :return: List of column header names.
    """
    with open(input_file, mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader, [])
    return headers


def load_config(config_path: str) -> Tuple[List[str], Dict[str, Any]]:
    """Loads column ordering and defaults from a JSON configuration file.

    JSON layout example:
    {
        "order": ["id", "username", "email", "status"],
        "defaults": {
            "status": "active"
        }
    }

    :param config_path: Path to config JSON file.
    :return: Tuple of (column_order_list, column_defaults_dict).
    """
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    order = data.get("order", [])
    defaults = data.get("defaults", {})
    return order, defaults


def process_csv(
    input_file: str,
    output_file: Optional[str],
    target_columns: List[str],
    column_defaults: Optional[Dict[str, Any]] = None,
    default_value: str = "",
    keep_extra: bool = False,
    delimiter: str = ",",
) -> Tuple[int, List[str]]:
    """Processes CSV file, reordering and filling columns per specification.

    :param input_file: Input CSV file path.
    :param output_file: Output CSV file path or stdout if None.
    :param target_columns: List of desired column headers in output order.
    :param column_defaults: Dict mapping column names to default values.
    :param default_value: Default fallback value for missing columns.
    :param keep_extra: If True, append extra original columns at the end.
    :param delimiter: CSV delimiter.
    :return: Tuple of (processed_row_count, final_output_headers).
    """
    if column_defaults is None:
        column_defaults = {}

    headers = inspect_headers(input_file, delimiter=delimiter)

    # Determine final output columns
    final_headers = list(target_columns)
    if keep_extra:
        extra_cols = [col for col in headers if col not in final_headers]
        final_headers.extend(extra_cols)

    row_count = 0

    def write_rows(out_stream: TextIO) -> None:
        nonlocal row_count
        writer = csv.writer(out_stream, delimiter=delimiter)
        writer.writerow(final_headers)

        with open(input_file, mode="r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                new_row = []
                for col in final_headers:
                    if col in row and row[col] is not None:
                        new_row.append(row[col])
                    elif col in column_defaults:
                        new_row.append(str(column_defaults[col]))
                    else:
                        new_row.append(default_value)
                writer.writerow(new_row)
                row_count += 1

    if output_file:
        with open(output_file, mode="w", newline="", encoding="utf-8") as f_out:
            write_rows(f_out)
    else:
        write_rows(sys.stdout)

    return row_count, final_headers


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    desc = "Reorder, select, or drop CSV columns."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--input", "-i", required=True, help="Input CSV file path")
    parser.add_argument(
        "--output",
        "-o",
        help="Output CSV file path (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--columns",
        "-c",
        help="Comma-separated list of target columns in desired order",
    )
    parser.add_argument(
        "--config",
        help="JSON configuration file specifying 'order' and 'defaults'",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Inspect and print existing headers in the CSV",
    )
    parser.add_argument(
        "--default-value",
        default="",
        help="Default string value for missing optional columns",
    )
    parser.add_argument(
        "--keep-extra",
        action="store_true",
        help="Keep extra columns not listed in target order at the end",
    )
    parser.add_argument(
        "--delimiter", default=",", help="CSV field delimiter (default: ',')"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for csv-column-reorder."""
    parsed = parse_args(args)

    if parsed.inspect:
        try:
            headers = inspect_headers(parsed.input, delimiter=parsed.delimiter)
            print(f"Headers in '{parsed.input}':")
            for idx, h in enumerate(headers, 1):
                print(f"  {idx}. {h}")
            return 0
        except (OSError, csv.Error) as e:
            print(f"Error inspecting CSV: {e}", file=sys.stderr)
            return 1

    target_columns: List[str] = []
    defaults: Dict[str, Any] = {}

    if parsed.config:
        try:
            config_order, config_defaults = load_config(parsed.config)
            target_columns = config_order
            defaults = config_defaults
        except (OSError, json.JSONDecodeError) as e:
            msg = f"Error reading config file {parsed.config}: {e}"
            print(msg, file=sys.stderr)
            return 1

    if parsed.columns:
        cli_columns = [col.strip() for col in parsed.columns.split(",") if col.strip()]
        target_columns = cli_columns

    if not target_columns and not parsed.keep_extra:
        msg = (
            "Error: Must specify columns via --columns or --config, "
            "or set --keep-extra."
        )
        print(msg, file=sys.stderr)
        return 1

    try:
        count, _out_headers = process_csv(
            input_file=parsed.input,
            output_file=parsed.output,
            target_columns=target_columns,
            column_defaults=defaults,
            default_value=parsed.default_value,
            keep_extra=parsed.keep_extra,
            delimiter=parsed.delimiter,
        )
        if parsed.output:
            msg = (
                f"Successfully processed {count} rows. "
                f"Output written to {parsed.output}"
            )
            print(msg)
    except (OSError, csv.Error) as e:
        print(f"Error processing CSV: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
