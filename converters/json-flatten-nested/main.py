"""JSON Flatten Nested Tool.

Flattens deeply nested JSON structures and arrays into a single-level
flat dictionary format (e.g. user.address.city, items.0.name) and supports
JSON -> CSV export.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import csv
import json
import sys
from typing import Any, Dict, List, Optional, TextIO, Union


def flatten_dict(
    nested_obj: Any,
    parent_key: str = "",
    sep: str = ".",
    flatten_lists: bool = True,
    max_depth: Optional[int] = None,
    _current_depth: int = 0,
) -> Dict[str, Any]:
    """Recursively flattens a nested dictionary or array structure.

    :param nested_obj: Dict, list, or primitive JSON value to flatten.
    :param parent_key: Current prefix key path.
    :param sep: Separator character for nested key names (default '.').
    :param flatten_lists: Key array elements with index (e.g., items.0.name).
    :param max_depth: Maximum recursion depth to flatten (None for unlimited).
    :param _current_depth: Internal recursion tracker.
    :return: Flattened single-level dictionary.
    """
    items: Dict[str, Any] = {}

    if max_depth is not None and _current_depth >= max_depth:
        items[parent_key] = nested_obj
        return items

    if isinstance(nested_obj, dict):
        for k, v in nested_obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
            is_nestable = isinstance(v, (dict, list)) and (
                not isinstance(v, list) or flatten_lists
            )
            if is_nestable:
                items.update(
                    flatten_dict(
                        v,
                        parent_key=new_key,
                        sep=sep,
                        flatten_lists=flatten_lists,
                        max_depth=max_depth,
                        _current_depth=_current_depth + 1,
                    )
                )
            else:
                items[new_key] = v
    elif isinstance(nested_obj, list) and flatten_lists:
        for idx, element in enumerate(nested_obj):
            new_key = f"{parent_key}{sep}{idx}" if parent_key else str(idx)
            if isinstance(element, (dict, list)):
                items.update(
                    flatten_dict(
                        element,
                        parent_key=new_key,
                        sep=sep,
                        flatten_lists=flatten_lists,
                        max_depth=max_depth,
                        _current_depth=_current_depth + 1,
                    )
                )
            else:
                items[new_key] = element
    else:
        items[parent_key] = nested_obj

    return items


def flatten_json_data(
    data: Union[Dict[str, Any], List[Any]],
    sep: str = ".",
    flatten_lists: bool = True,
    max_depth: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Flattens top-level JSON structure (dict or list of dicts).

    :param data: Loaded JSON data (dict or list).
    :param sep: Separator string.
    :param flatten_lists: Whether to flatten arrays.
    :param max_depth: Maximum depth to flatten.
    :return: List of flattened dictionaries.
    """
    if isinstance(data, list):
        # Process each item in top-level array
        return [
            (
                flatten_dict(
                    item,
                    sep=sep,
                    flatten_lists=flatten_lists,
                    max_depth=max_depth,
                )
                if isinstance(item, (dict, list))
                else {"value": item}
            )
            for item in data
        ]
    if isinstance(data, dict):
        return [
            flatten_dict(
                data,
                sep=sep,
                flatten_lists=flatten_lists,
                max_depth=max_depth,
            )
        ]

    return [{"value": data}]


def export_to_csv(
    flat_records: List[Dict[str, Any]], output_file: Optional[str]
) -> None:
    """Writes a list of flattened dictionaries to a CSV file or stdout.

    :param flat_records: List of flattened single-level dictionaries.
    :param output_file: Path to output CSV file, or None for stdout.
    """
    # Collect all unique headers preserving order of appearance
    all_headers: List[str] = []
    for record in flat_records:
        for key in record.keys():
            if key not in all_headers:
                all_headers.append(key)

    def write_csv(f_out: TextIO) -> None:
        writer = csv.DictWriter(f_out, fieldnames=all_headers)
        writer.writeheader()
        for record in flat_records:
            # Replace list/dict primitives if any remain with JSON strings
            row = {}
            for k in all_headers:
                val = record.get(k)
                if isinstance(val, (dict, list)):
                    row[k] = json.dumps(val)
                elif val is None:
                    row[k] = ""
                else:
                    row[k] = str(val)
            writer.writerow(row)

    if output_file:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            write_csv(f)
    else:
        write_csv(sys.stdout)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    desc = "Flatten deeply nested JSON structures to JSON or CSV."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--input", "-i", required=True, help="Input JSON file path")
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="csv",
        help="Output format: csv or json (default: csv)",
    )
    parser.add_argument(
        "--sep", default=".", help="Nested key separator (default: '.')"
    )
    parser.add_argument(
        "--no-array-flatten",
        action="store_true",
        help="Do not flatten array indices",
    )
    parser.add_argument(
        "--max-depth", type=int, help="Maximum recursion depth to flatten"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for json-flatten-nested."""
    parsed = parse_args(args)

    try:
        with open(parsed.input, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error loading JSON from {parsed.input}: {e}", file=sys.stderr)
        return 1

    flatten_lists = not parsed.no_array_flatten
    flattened_records = flatten_json_data(
        raw_data,
        sep=parsed.sep,
        flatten_lists=flatten_lists,
        max_depth=parsed.max_depth,
    )

    if parsed.format == "json":
        output_data = (
            flattened_records if len(flattened_records) > 1 else flattened_records[0]
        )
        out_str = json.dumps(output_data, indent=2)
        if parsed.output:
            with open(parsed.output, "w", encoding="utf-8") as f:
                f.write(out_str + "\n")
            print(f"Flattened JSON written to {parsed.output}")
        else:
            print(out_str)
    else:
        try:
            export_to_csv(flattened_records, parsed.output)
            if parsed.output:
                print(f"Exported CSV written to {parsed.output}")
        except (OSError, csv.Error) as e:
            print(f"Error exporting CSV: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
